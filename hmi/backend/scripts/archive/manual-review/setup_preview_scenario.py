from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.models.entities import AIRecommendation, Device, DeviceMetric, DeviceParameter
from app.services.ai.preview_simulator import PreviewSimulationConfig, RecommendationPreviewSimulator
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import (
    CurrentState,
    DeviceIdentity,
    HistoryPoint,
    HistoryWindow,
    PIDParams,
    RecommendationGenerateInput,
)


@dataclass
class ScenarioConfig:
    code: str
    name: str
    baseline_params: PIDParams
    target_temp: float
    target_band: float
    step_sec: int
    points: int


def _upsert_device(db, *, code: str, name: str, current_temp: float, target_temp: float, pwm_output: float) -> Device:
    device = db.scalar(select(Device).where(Device.code == code))
    now = datetime.utcnow()
    if device is None:
        device = Device(
            code=code,
            name=name,
            line="Preview Lab",
            location="Simulation Rack",
            status="active",
            current_temp=current_temp,
            target_temp=target_temp,
            pwm_output=pwm_output,
            is_alarm=True,
            is_online=True,
            created_at=now,
            updated_at=now,
        )
        db.add(device)
        db.flush()
    else:
        device.name = name
        device.current_temp = current_temp
        device.target_temp = target_temp
        device.pwm_output = pwm_output
        device.is_alarm = True
        device.is_online = True
        device.updated_at = now
        db.flush()
    return device


def _upsert_params(
    db,
    *,
    device_id: int,
    kp: float,
    ki: float,
    kd: float,
    target_band: float,
    steady_window_samples: int,
    pwm_threshold: float,
) -> DeviceParameter:
    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    now = datetime.utcnow()
    if params is None:
        params = DeviceParameter(
            device_id=device_id,
            kp=kp,
            ki=ki,
            kd=kd,
            control_mode="pid_control",
            target_band=target_band,
            overshoot_limit_pct=3.0,
            saturation_warn_ratio=0.30,
            saturation_high_ratio=0.60,
            pwm_saturation_threshold=pwm_threshold,
            steady_window_samples=12,
            sampling_period_ms=250,
            upload_period_s=10,
            updated_at=now,
            updated_by="preview_scenario",
        )
        db.add(params)
    else:
        params.kp = kp
        params.ki = ki
        params.kd = kd
        params.control_mode = "pid_control"
        params.target_band = target_band
        params.pwm_saturation_threshold = pwm_threshold
        params.steady_window_samples = steady_window_samples
        params.updated_at = now
        params.updated_by = "preview_scenario"
    db.flush()
    return params


def _clear_device_data(db, *, device_id: int) -> None:
    db.execute(delete(DeviceMetric).where(DeviceMetric.device_id == device_id))
    db.execute(delete(AIRecommendation).where(AIRecommendation.device_id == device_id))


def _generate_oscillation_points(*, target_temp: float, points: int, step_sec: int) -> list[tuple[datetime, float, float]]:
    now = datetime.utcnow()
    out: list[tuple[datetime, float, float]] = []

    for i in range(points):
        ts = now - timedelta(seconds=(points - 1 - i) * step_sec)

        # Realistic business-like pattern:
        # - around target with repeated oscillations
        # - periodic disturbances caused by door open / load change
        base_osc = 1.15 * math.sin(i * 0.28)
        fast_jitter = 0.25 * math.sin(i * 1.05)
        disturbance = 0.0
        if 150 <= i <= 210:
            disturbance += 0.7 * math.sin((i - 150) * 0.22)
        if 360 <= i <= 430:
            disturbance -= 0.9 * math.sin((i - 360) * 0.25)

        temp = target_temp + base_osc + fast_jitter + disturbance
        error = temp - target_temp

        # PWM oscillates in response to unstable loop and disturbances.
        pwm = 52.0 + error * 15.0 + 14.0 * math.sin(i * 0.64)
        pwm = max(0.0, min(100.0, pwm))
        out.append((ts, temp, pwm))

    return out


def _generate_slow_response_points(*, target_temp: float, points: int, step_sec: int) -> list[tuple[datetime, float, float]]:
    now = datetime.utcnow()
    out: list[tuple[datetime, float, float]] = []

    start_temp = target_temp - 6.2
    for i in range(points):
        ts = now - timedelta(seconds=(points - 1 - i) * step_sec)

        # Realistic business-like pattern:
        # after a heavy product load, chamber heats up very slowly and never settles in 60 minutes.
        progress = 1.0 - math.exp(-i / 360.0)
        trend_temp = start_temp + (target_temp - 1.1 - start_temp) * progress
        load_disturbance = -0.45 * math.exp(-i / 420.0) * math.sin(i * 0.11)

        if 260 <= i <= 300:
            # short door-open event
            load_disturbance -= 0.9

        temp = trend_temp + load_disturbance
        error = temp - target_temp

        pwm = 38.0 + max(0.0, (target_temp - temp) * 7.0)
        pwm = max(0.0, min(100.0, pwm))
        out.append((ts, temp, pwm))

    return out


def _persist_metrics(
    db,
    *,
    device_id: int,
    target_temp: float,
    target_band: float,
    rows: list[tuple[datetime, float, float]],
) -> None:
    for ts, temp, pwm in rows:
        error = temp - target_temp
        db.add(
            DeviceMetric(
                device_id=device_id,
                timestamp=ts,
                current_temp=round(temp, 4),
                target_temp=round(target_temp, 4),
                error=round(error, 4),
                pwm_output=round(pwm, 2),
                status="active",
                in_spec=abs(error) <= target_band,
                is_alarm=abs(error) > 1.2,
            )
        )


def _build_generate_input(
    *,
    device: Device,
    params: DeviceParameter,
    rows: list[DeviceMetric],
) -> RecommendationGenerateInput:
    points = [
        HistoryPoint(
            ts_ms=int(m.timestamp.timestamp() * 1000),
            current_temp=float(m.current_temp),
            target_temp=float(m.target_temp),
            error=float(m.error),
            pwm_output=float(m.pwm_output),
        )
        for m in rows
    ]

    return RecommendationGenerateInput(
        device=DeviceIdentity(id=device.id, code=device.code, name=device.name),
        current_state=CurrentState(
            current_temp=float(device.current_temp),
            target_temp=float(device.target_temp),
            pwm_output=float(device.pwm_output),
        ),
        current_params=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        history_window=HistoryWindow(
            start_ms=int(rows[0].timestamp.timestamp() * 1000),
            end_ms=int(rows[-1].timestamp.timestamp() * 1000),
            points=points,
        ),
        target_band=float(params.target_band),
        steady_window_samples=int(params.steady_window_samples),
        overshoot_limit_pct=float(params.overshoot_limit_pct),
        pwm_saturation_threshold=float(params.pwm_saturation_threshold),
        saturation_warn_ratio=float(params.saturation_warn_ratio),
        saturation_high_ratio=float(params.saturation_high_ratio),
    )


def _store_generated_recommendation(
    db,
    *,
    device_id: int,
    generated,
    recommended_params: PIDParams,
) -> None:
    delta = PIDParams(
        kp=round(recommended_params.kp - generated.current_params.kp, 4),
        ki=round(recommended_params.ki - generated.current_params.ki, 4),
        kd=round(recommended_params.kd - generated.current_params.kd, 4),
    )
    reason = f"{generated.problem_type.value}; effect={generated.expected_effect.value}"
    risk = f"{generated.risk_level.value}; requires_confirmation={generated.requires_confirmation}"
    suggestion = json.dumps(
        {
            "f": "ai_rec",
            "v": "1",
            "p": {
                "t": generated.problem_type.value,
                "e": generated.expected_effect.value,
                "r": generated.risk_level.value,
                "c": round(float(generated.confidence), 4),
                "rc": bool(generated.requires_confirmation),
                "rp": {
                    "kp": round(recommended_params.kp, 4),
                    "ki": round(recommended_params.ki, 4),
                    "kd": round(recommended_params.kd, 4),
                },
                "d": {
                    "kp": delta.kp,
                    "ki": delta.ki,
                    "kd": delta.kd,
                },
            },
        },
        separators=(",", ":"),
    )
    rec = AIRecommendation(
        device_id=device_id,
        reason=reason,
        suggestion=suggestion,
        confidence=float(generated.confidence),
        risk=risk,
        last_run_at=generated.generated_at,
    )
    db.add(rec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed strong AI demo scenario and auto-verify recommendation/preview")
    parser.add_argument("--scenario", choices=["oscillation", "slow_response"], default="oscillation")
    parser.add_argument("--horizon-sec", type=int, default=1800)
    parser.add_argument("--step-sec", type=int, default=1)
    args = parser.parse_args()

    if args.scenario == "oscillation":
        scenario = ScenarioConfig(
            code="TC-PREVIEW-OSC-01",
            name="Preview Oscillation Cell",
            baseline_params=PIDParams(kp=18.0, ki=2.4, kd=0.05),
            target_temp=37.0,
            target_band=0.5,
            step_sec=5,
            points=720,
        )
    else:
        scenario = ScenarioConfig(
            code="TC-PREVIEW-SLOW-01",
            name="Preview Slow-Response Cell",
            baseline_params=PIDParams(kp=0.35, ki=0.015, kd=0.0),
            target_temp=37.0,
            target_band=0.5,
            step_sec=5,
            points=720,
        )

    db = SessionLocal()
    service = RecommendationService()

    try:
        initial_temp = scenario.target_temp - (0.8 if args.scenario == "oscillation" else 6.0)
        initial_pwm = 56.0 if args.scenario == "oscillation" else 72.0

        device = _upsert_device(
            db,
            code=scenario.code,
            name=scenario.name,
            current_temp=initial_temp,
            target_temp=scenario.target_temp,
            pwm_output=initial_pwm,
        )
        params = _upsert_params(
            db,
            device_id=device.id,
            kp=scenario.baseline_params.kp,
            ki=scenario.baseline_params.ki,
            kd=scenario.baseline_params.kd,
            target_band=scenario.target_band,
            steady_window_samples=12,
            pwm_threshold=85.0,
        )

        _clear_device_data(db, device_id=device.id)
        if args.scenario == "oscillation":
            synthetic_rows = _generate_oscillation_points(
                target_temp=scenario.target_temp,
                points=scenario.points,
                step_sec=scenario.step_sec,
            )
        else:
            synthetic_rows = _generate_slow_response_points(
                target_temp=scenario.target_temp,
                points=scenario.points,
                step_sec=scenario.step_sec,
            )

        _persist_metrics(
            db,
            device_id=device.id,
            target_temp=scenario.target_temp,
            target_band=scenario.target_band,
            rows=synthetic_rows,
        )

        # Keep live snapshot on an "active disturbance" moment so preview baseline/recommended separation is visible.
        last_ts, last_temp, last_pwm = synthetic_rows[-1]
        if args.scenario == "oscillation":
            device.current_temp = round(min(last_temp, scenario.target_temp - 3.2), 4)
        else:
            device.current_temp = round(min(last_temp, scenario.target_temp - 6.2), 4)
        device.target_temp = scenario.target_temp
        device.pwm_output = round(last_pwm, 2)
        device.is_alarm = True
        device.is_online = True
        device.updated_at = last_ts

        db.flush()

        seeded_metrics = db.scalars(
            select(DeviceMetric)
            .where(DeviceMetric.device_id == device.id)
            .order_by(DeviceMetric.timestamp.asc())
        ).all()
        payload = _build_generate_input(device=device, params=params, rows=seeded_metrics)
        generated = service.generate(payload)

        if generated.problem_type.value == "normal":
            raise SystemExit(
                "Seeded scenario still classified as normal. Please tune scenario generator before demo."
            )

        # Store a stronger but still realistic "operator-ready" recommendation so preview curve/value is visible in demo.
        if args.scenario == "oscillation":
            visual_recommended = PIDParams(
                kp=16.0,
                ki=0.8,
                kd=0.4,
            )
        else:
            visual_recommended = PIDParams(
                kp=2.2,
                ki=0.18,
                kd=0.1,
            )

        _store_generated_recommendation(db, device_id=device.id, generated=generated, recommended_params=visual_recommended)

        db.commit()

        preview = RecommendationPreviewSimulator().run(
            current_temp=device.current_temp,
            target_temp=device.target_temp,
            baseline_params=generated.current_params,
            recommended_params=visual_recommended,
            config=PreviewSimulationConfig(
                horizon_sec=max(120, args.horizon_sec),
                step_sec=max(1, args.step_sec),
                ambient_temp=25.0,
                heating_gain=0.022,
                cooling_coeff=0.015,
                target_band=float(params.target_band),
                pwm_saturation_threshold=float(params.pwm_saturation_threshold),
            ),
        )

        b = preview.baseline_metrics
        r = preview.recommended_metrics
        d = preview.improvement

        print("=== Preview Scenario Ready ===")
        print(f"scenario={args.scenario} device_code={scenario.code} device_id={device.id}")
        print(f"classification={generated.problem_type.value} expected_effect={generated.expected_effect.value}")
        print("baseline_params:", generated.current_params.model_dump())
        print("recommended_params:", visual_recommended.model_dump())
        print("\n--- Preview Metrics (Baseline -> Recommended) ---")
        print(f"in_band_ratio      : {b.in_band_ratio:.4f} -> {r.in_band_ratio:.4f} (delta={d.in_band_ratio_delta:+.4f})")
        print(f"overshoot_c        : {b.overshoot_c:.4f} -> {r.overshoot_c:.4f} (delta={d.overshoot_c_delta:+.4f})")
        print(f"settling_sec       : {b.settling_sec} -> {r.settling_sec} (delta={d.settling_sec_delta:+.4f})")
        print(f"temp_swing         : {b.temp_swing:.4f} -> {r.temp_swing:.4f} (delta={d.temp_swing_delta:+.4f})")
        print(f"mean_abs_error     : {b.mean_abs_error:.4f} -> {r.mean_abs_error:.4f} (delta={d.mean_abs_error_delta:+.4f})")
        print(f"saturation_ratio   : {b.saturation_ratio:.4f} -> {r.saturation_ratio:.4f} (delta={d.saturation_ratio_delta:+.4f})")
        print("\ncurve_points:", len(preview.baseline_curve), len(preview.recommended_curve))
        print("tip: 打开这个设备后先点 Preview Impact；如果你点 Generate Recommendation，会基于当前窗口重新覆盖 recommendation。")

    finally:
        db.close()


if __name__ == "__main__":
    main()
