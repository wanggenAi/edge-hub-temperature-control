#!/usr/bin/env python3
"""Prepare stable HMI demo data for poster screenshots.

This script is intentionally poster-local. It refreshes one preview device with
clear before/after telemetry and marks an AI recommendation as applied/evaluated
so the HMI screenshots show meaningful content instead of empty panels.
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, select


POSTER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = POSTER_ROOT.parent
BACKEND_ROOT = REPO_ROOT / "hmi" / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.db.session import SessionLocal
from app.models.entities import AIRecommendation, Device, DeviceMetric, DeviceParameter, User, UserDevice
from app.services.ai.enums import ExpectedEffect, ProblemType, RiskLevel
from app.services.ai.post_effect_evaluator import ObservedTelemetryPoint, PostEffectEvaluator
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import PIDParams, PreviewMetrics, RecommendationGenerateOutput
from app.services.seed import seed_database


POSTER_DEVICE_CODE = "TC-PREVIEW-OSC-OVS"
POSTER_DEVICE_NAME = "Poster AI Validation Cell"


def _local_utc_offset() -> timedelta:
    now_local = datetime.now().astimezone()
    return now_local.utcoffset() or timedelta()


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _query_time_for_metadata(metadata_time: datetime) -> datetime:
    """Return the UTC row timestamp queried from a naive UI metadata time.

    The poster screenshot path runs through a real frontend/backend round trip.
    The frontend parses naive API datetimes as local browser time, while the
    backend converts returned epoch milliseconds back to UTC-naive database
    timestamps. This helper aligns seeded PostgreSQL telemetry rows with that
    behavior without changing production HMI code.
    """

    return metadata_time - _local_utc_offset()


def _metric_point(ts: datetime, target: float, error: float, pwm: float) -> tuple[DeviceMetric, ObservedTelemetryPoint]:
    temp = target + error
    metric = DeviceMetric(
        timestamp=ts,
        current_temp=round(temp, 3),
        target_temp=round(target, 3),
        error=round(error, 3),
        pwm_output=round(max(0.0, min(100.0, pwm)), 2),
        status="active",
        in_spec=abs(error) <= 0.5,
        is_alarm=abs(error) > 1.5,
    )
    observed = ObservedTelemetryPoint(
        ts_ms=int(ts.timestamp() * 1000),
        temp=float(metric.current_temp),
        target_temp=float(metric.target_temp),
        error=float(metric.error),
        pwm_output=float(metric.pwm_output),
        saturation_state="high" if metric.pwm_output >= 85.0 else "none",
    )
    return metric, observed


def _build_telemetry_series(device: Device, *, applied_at: datetime) -> tuple[list[DeviceMetric], list[ObservedTelemetryPoint], list[ObservedTelemetryPoint]]:
    target = float(device.target_temp)
    metrics: list[DeviceMetric] = []
    baseline_points: list[ObservedTelemetryPoint] = []
    actual_points: list[ObservedTelemetryPoint] = []

    start = applied_at - timedelta(minutes=90)
    for idx in range(180):
        ts = start + timedelta(seconds=60 * idx)
        minutes_from_apply = (ts - applied_at).total_seconds() / 60.0
        if minutes_from_apply < 0:
            progress = max(0.0, min(1.0, (minutes_from_apply + 90.0) / 90.0))
            oscillation = 1.18 * math.sin(idx * 0.48)
            drift = 1.18 - progress * 0.32
            error = drift + oscillation
            pwm = 63.0 + abs(error) * 14.0 + 10.0 * abs(math.sin(idx * 0.27))
        else:
            progress = max(0.0, min(1.0, minutes_from_apply / 89.0))
            oscillation = 0.40 * (1.0 - progress * 0.65) * math.sin(idx * 0.42)
            drift = 0.42 * (1.0 - progress)
            error = drift + oscillation
            pwm = 48.0 + abs(error) * 12.0 + 4.0 * abs(math.sin(idx * 0.31))

        metric, observed = _metric_point(ts, target, error, pwm)
        metric.device_id = int(device.id)
        metrics.append(metric)
        if ts < applied_at:
            baseline_points.append(observed)
        else:
            actual_points.append(observed)

    return metrics, baseline_points, actual_points


def _build_poster_preview_curve(
    *,
    target: float,
    baseline_points: list[ObservedTelemetryPoint],
    horizon_minutes: int = 30,
) -> tuple[list[dict[str, float | int]], PreviewMetrics]:
    """Create a restrained poster preview curve aligned to the real UI chart.

    The production simulator remains untouched. For the poster seed, the stored
    preview should visually communicate "damped after PID recommendation" rather
    than exaggerating thermal dynamics and stretching the chart scale.
    """

    evaluator = PostEffectEvaluator()
    points: list[ObservedTelemetryPoint] = []
    start_error = float(baseline_points[-1].temp - target) if baseline_points else 0.45
    for minute in range(0, horizon_minutes + 1):
        progress = minute / float(max(1, horizon_minutes))
        damping = math.exp(-2.4 * progress)
        error = (start_error * damping) + (0.34 * damping * math.sin(minute * 0.72))
        pwm = 50.0 + abs(error) * 10.0
        ts_ms = minute * 60 * 1000
        points.append(
            ObservedTelemetryPoint(
                ts_ms=ts_ms,
                temp=round(target + error, 3),
                target_temp=round(target, 3),
                error=round(error, 3),
                pwm_output=round(pwm, 2),
                saturation_state="none",
            )
        )

    metrics = evaluator.calc_metrics(points=points, target_band=0.5, pwm_saturation_threshold=85.0)
    if metrics is None:
        raise SystemExit("Failed to build poster preview metrics.")
    curve = [
        {
            "time_s": int(point.ts_ms / 1000),
            "temp": float(point.temp),
            "target_temp": float(point.target_temp),
            "pwm_output": float(point.pwm_output),
            "error": float(point.error),
        }
        for point in points
    ]
    return curve, metrics


def _metric_improvement(reference: PreviewMetrics, recommended: PreviewMetrics):
    from app.services.ai.schemas import PreviewImprovement

    def optional_delta(left: Optional[float], right: Optional[float]) -> float:
        if left is None or right is None:
            return 0.0
        return round(float(left) - float(right), 6)

    return PreviewImprovement(
        in_band_ratio_delta=round(recommended.in_band_ratio - reference.in_band_ratio, 6),
        overshoot_c_delta=round(reference.overshoot_c - recommended.overshoot_c, 6),
        settling_sec_delta=optional_delta(reference.settling_sec, recommended.settling_sec),
        temp_swing_delta=round(reference.temp_swing - recommended.temp_swing, 6),
        mean_abs_error_delta=round(reference.mean_abs_error - recommended.mean_abs_error, 6),
        saturation_ratio_delta=round(reference.saturation_ratio - recommended.saturation_ratio, 6),
    )


def _attach_all_users(db, device: Device) -> None:
    for user in db.scalars(select(User)).all():
        exists = db.scalar(select(UserDevice.id).where(UserDevice.user_id == user.id, UserDevice.device_id == device.id))
        if not exists:
            db.add(UserDevice(user_id=user.id, device_id=device.id))


def main() -> None:
    db = SessionLocal()
    try:
        seed_database(db, with_default_alarm_rules=True, with_demo_data=True, with_preview_ai_demo=True)

        device = db.scalar(select(Device).where(Device.code == POSTER_DEVICE_CODE))
        if device is None:
            raise SystemExit(f"Preview device not found after seed: {POSTER_DEVICE_CODE}")

        device.name = POSTER_DEVICE_NAME
        device.line = "AI Preview"
        device.location = "Poster Demo"
        device.status = "active"
        device.target_temp = 37.0
        device.current_temp = 37.18
        device.pwm_output = 52.0
        device.is_alarm = False
        device.is_online = True
        device.updated_at = _utc_now_naive()

        params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
        if params is None:
            params = DeviceParameter(device_id=device.id)
            db.add(params)
            db.flush()
        baseline_params = PIDParams(kp=2.9, ki=0.42, kd=0.12)
        recommended_params = PIDParams(kp=2.25, ki=0.31, kd=0.26)
        params.kp = baseline_params.kp
        params.ki = baseline_params.ki
        params.kd = baseline_params.kd
        params.control_mode = "pid_control"
        params.target_band = 0.5
        params.overshoot_limit_pct = 3.0
        params.saturation_warn_ratio = 0.3
        params.saturation_high_ratio = 0.6
        params.pwm_saturation_threshold = 85.0
        params.steady_window_samples = 12
        params.updated_by = "poster_demo"
        params.updated_at = _utc_now_naive()

        db.execute(delete(DeviceMetric).where(DeviceMetric.device_id == device.id))
        db.execute(delete(AIRecommendation).where(AIRecommendation.device_id == device.id))
        db.flush()

        # Keep the post-apply window mature enough for real screenshots. Metadata
        # uses the HMI-visible wall time; telemetry rows use the backend query
        # timestamp reached after the browser converts that wall time to epoch ms.
        applied_at_meta = _utc_now_naive() - timedelta(minutes=62)
        telemetry_applied_at = _query_time_for_metadata(applied_at_meta)
        metrics, baseline_points, actual_points = _build_telemetry_series(device, applied_at=telemetry_applied_at)
        for metric in metrics:
            db.add(metric)

        evaluator = PostEffectEvaluator()
        baseline_metrics = evaluator.calc_metrics(
            points=baseline_points,
            target_band=float(params.target_band),
            pwm_saturation_threshold=float(params.pwm_saturation_threshold),
        )
        actual_metrics = evaluator.calc_metrics(
            points=actual_points,
            target_band=float(params.target_band),
            pwm_saturation_threshold=float(params.pwm_saturation_threshold),
        )
        if baseline_metrics is None or actual_metrics is None:
            raise SystemExit("Failed to build poster telemetry metrics.")

        preview_curve, preview_metrics = _build_poster_preview_curve(target=float(device.target_temp), baseline_points=baseline_points)
        preview_improvement = _metric_improvement(baseline_metrics, preview_metrics)

        actual_summary = evaluator.build_actual_summary(points=actual_points, metrics=actual_metrics)
        comparison_before = evaluator.compare(reference=baseline_metrics, actual=actual_metrics)
        comparison_preview = evaluator.compare(reference=preview_metrics, actual=actual_metrics)

        delta = PIDParams(
            kp=round(recommended_params.kp - baseline_params.kp, 4),
            ki=round(recommended_params.ki - baseline_params.ki, 4),
            kd=round(recommended_params.kd - baseline_params.kd, 4),
        )
        output = RecommendationGenerateOutput(
            problem_type=ProblemType.OSCILLATION,
            primary_problem_type=ProblemType.OSCILLATION,
            secondary_problem_types=[ProblemType.OVERSHOOT_HIGH],
            problem_flags={
                "oscillation": True,
                "overshoot_high": True,
                "saturation_limited": False,
                "slow_response": False,
                "steady_state_error": False,
            },
            confidence=0.88,
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=True,
            current_params=baseline_params,
            recommended_params=recommended_params,
            delta=delta,
            expected_effect=ExpectedEffect.REDUCE_OSCILLATION,
            evidence={
                "mean_abs_error": round(baseline_metrics.mean_abs_error, 4),
                "in_band_ratio": round(baseline_metrics.in_band_ratio, 4),
                "overshoot_c": round(baseline_metrics.overshoot_c, 4),
                "saturation_ratio": round(baseline_metrics.saturation_ratio, 4),
                "temp_swing": round(baseline_metrics.temp_swing, 4),
                "settling_sec": baseline_metrics.settling_sec,
                "zero_crossings": 9,
            },
            generated_at=applied_at_meta - timedelta(minutes=4),
            ai_decision={
                "runtime_source": "local_backend",
                "fallback_used": False,
                "ranking_used": True,
                "selected_candidate_id": "oscillation_damping",
                "candidate_count": 4,
                "evaluated_candidate_count": 4,
                "configured_candidate_limit": 6,
                "ranked_candidates": [
                    {
                        "rank": 1,
                        "candidate_id": "oscillation_damping",
                        "strategy_note": "Reduce Kp/Ki and add derivative damping.",
                        "total_score": 0.86,
                    },
                    {
                        "rank": 2,
                        "candidate_id": "conservative_pi",
                        "strategy_note": "Milder PI adjustment for lower risk.",
                        "total_score": 0.72,
                    },
                ],
            },
        )

        service = RecommendationService()
        reason, suggestion, risk = service.to_storage_fields(
            output,
            history_state="generated",
            runtime_decision=output.ai_decision,
        )
        preview_compact = {
            "baseline_metrics": baseline_metrics.model_dump(mode="json"),
            "recommended_metrics": preview_metrics.model_dump(mode="json"),
            "improvement": preview_improvement.model_dump(mode="json"),
            "recommended_curve": preview_curve,
        }

        suggestion = service.update_storage_metadata(
            suggestion,
            history_state="applied",
            last_accessed_at=applied_at_meta,
            applied_at=applied_at_meta,
            preview_summary=preview_compact,
            post_effect_summary=actual_summary.model_dump(mode="json"),
            post_effect_comparison_before=comparison_before.model_dump(mode="json"),
            post_effect_comparison_preview=comparison_preview.model_dump(mode="json"),
            actual_effect_evaluated=True,
            observation_window_minutes=30,
            evaluated_at=_utc_now_naive() - timedelta(minutes=2),
        )
        db.add(
            AIRecommendation(
                device_id=device.id,
                reason=reason,
                suggestion=suggestion,
                confidence=output.confidence,
                risk=risk,
                last_run_at=applied_at_meta - timedelta(minutes=4),
            )
        )

        _attach_all_users(db, device)
        db.commit()
        print(f"Prepared poster HMI demo data for {device.code} (id={device.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
