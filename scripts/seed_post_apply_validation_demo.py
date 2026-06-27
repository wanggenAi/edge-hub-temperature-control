#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, select, text

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "hmi" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.db.session import SessionLocal
from app.models.entities import AIRecommendation, Device, DeviceParameter, User, UserDevice
from app.services.ai.post_effect_evaluator import ObservedTelemetryPoint, PostEffectEvaluator
from app.services.ai.schemas import PreviewMetrics
from app.services.tdengine_client import TdengineClient
from app.core.config import settings


TARGET_BAND = 0.5
PWM_SAT_THRESHOLD = 85.0
OBS_WINDOW_MINUTES = 30
STEP_SECONDS = 30
POINTS_PER_WINDOW = 60
DEMO_REASON_PREFIX = "PAV_DEMO"
DEMO_RUN_PREFIX = "pavdemo"
DEFAULT_SCENARIOS = ["success", "partial", "preview_mismatch", "insufficient_data"]


def calc_error_c(target_temp_c: float, sensor_temp_c: float) -> float:
    return float(target_temp_c) - float(sensor_temp_c)


@dataclass(frozen=True)
class ScenarioDef:
    key: str
    title: str
    device_code: str
    device_name: str
    line: str
    location: str
    target_temp: float
    apply_minutes_ago: int
    current_params: tuple[float, float, float]
    recommended_params: tuple[float, float, float]
    problem_type: str
    expected_effect: str
    risk_level: str
    before_profile: str
    after_profile: str
    completed: bool
    insufficient_data: bool


SCENARIOS: dict[str, ScenarioDef] = {
    "success": ScenarioDef(
        key="success",
        title="A - Clear Improvement",
        device_code="PAV-401",
        device_name="Post-Apply Validation A",
        line="Line 4",
        location="Demo Zone A",
        target_temp=37.0,
        apply_minutes_ago=150,
        current_params=(2.20, 0.31, 0.06),
        recommended_params=(2.85, 0.42, 0.10),
        problem_type="slow_response",
        expected_effect="speed_up_response",
        risk_level="Medium",
        before_profile="success_before",
        after_profile="success_after",
        completed=True,
        insufficient_data=False,
    ),
    "partial": ScenarioDef(
        key="partial",
        title="B - Limited Improvement",
        device_code="PAV-402",
        device_name="Post-Apply Validation B",
        line="Line 4",
        location="Demo Zone B",
        target_temp=36.5,
        apply_minutes_ago=120,
        current_params=(2.45, 0.36, 0.08),
        recommended_params=(2.55, 0.39, 0.08),
        problem_type="steady_state_error",
        expected_effect="reduce_steady_state_error",
        risk_level="Low",
        before_profile="partial_before",
        after_profile="partial_after",
        completed=True,
        insufficient_data=False,
    ),
    "preview_mismatch": ScenarioDef(
        key="preview_mismatch",
        title="C - Preview Mismatch",
        device_code="PAV-403",
        device_name="Post-Apply Validation C",
        line="Line 4",
        location="Demo Zone C",
        target_temp=37.2,
        apply_minutes_ago=90,
        current_params=(2.60, 0.40, 0.08),
        recommended_params=(3.20, 0.50, 0.11),
        problem_type="overshoot_high",
        expected_effect="reduce_overshoot",
        risk_level="High",
        before_profile="mismatch_before",
        after_profile="mismatch_after",
        completed=True,
        insufficient_data=False,
    ),
    "insufficient_data": ScenarioDef(
        key="insufficient_data",
        title="D - Insufficient Telemetry",
        device_code="PAV-404",
        device_name="Post-Apply Validation D",
        line="Line 4",
        location="Demo Zone D",
        target_temp=36.8,
        apply_minutes_ago=25,
        current_params=(2.35, 0.34, 0.07),
        recommended_params=(2.70, 0.41, 0.09),
        problem_type="saturation_limited",
        expected_effect="limited_gain_expected",
        risk_level="Medium",
        before_profile="insufficient_before",
        after_profile="insufficient_after",
        completed=False,
        insufficient_data=True,
    ),
}

SCENARIO_ALIASES: dict[str, str] = {
    "success": "success",
    "clear_improvement": "success",
    "a": "success",
    "partial": "partial",
    "limited_improvement": "partial",
    "limited": "partial",
    "b": "partial",
    "preview_mismatch": "preview_mismatch",
    "mismatch": "preview_mismatch",
    "c": "preview_mismatch",
    "insufficient_data": "insufficient_data",
    "insufficient": "insufficient_data",
    "d": "insufficient_data",
}

SCENARIO_CHOICES = sorted(SCENARIO_ALIASES.keys())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Post-Apply Validation demo scenarios into PostgreSQL + TDengine")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=SCENARIO_CHOICES,
        help="Scenario key/alias. Can be used multiple times. Default seeds all scenarios.",
    )
    parser.add_argument("--device-id", type=int, default=None, help="Optional target device id (only valid when seeding one scenario)")
    parser.add_argument("--reset", action="store_true", help="Clear existing Post-Apply Validation demo records first")
    parser.add_argument("--drop-demo-devices", action="store_true", help="When used with --reset, also delete demo devices PAV-40x")
    parser.add_argument("--seed", type=int, default=42, help="Reserved deterministic seed id (for future profile variants)")
    return parser.parse_args()


def q(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def safe_table_suffix(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", value).strip("_")
    if not cleaned:
        cleaned = "unknown"
    if cleaned[0].isdigit():
        cleaned = f"d_{cleaned}"
    return cleaned.lower()


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def ensure_td_telemetry_schema(td: TdengineClient, database: str) -> None:
    td.query(f"CREATE DATABASE IF NOT EXISTS {database} PRECISION 'ms'")
    td.query(
        f"CREATE STABLE IF NOT EXISTS {database}.telemetry ("
        "ts TIMESTAMP,"
        "uptime_ms BIGINT,"
        "target_temp_c DOUBLE,"
        "sim_temp_c DOUBLE,"
        "sensor_temp_c DOUBLE,"
        "error_c DOUBLE,"
        "integral_error DOUBLE,"
        "control_output DOUBLE,"
        "pwm_duty INT,"
        "pwm_norm DOUBLE,"
        "control_period_ms BIGINT,"
        "saturation_state VARCHAR(32),"
        "sensor_valid BOOL,"
        "run_id VARCHAR(128),"
        "control_mode VARCHAR(64),"
        "controller_version VARCHAR(64),"
        "kp DOUBLE,"
        "ki DOUBLE,"
        "kd DOUBLE,"
        "system_state VARCHAR(64),"
        "sensor_status VARCHAR(32),"
        "actual_dt_ms BIGINT,"
        "dt_error_ms BIGINT,"
        "wifi_connected BOOL,"
        "mqtt_connected BOOL,"
        "mqtt_reconnect_count BIGINT,"
        "mqtt_publish_fail_count BIGINT,"
        "safety_output_forced_off BOOL,"
        "fault_latched BOOL,"
        "fault_reason VARCHAR(255),"
        "software_max_safe_temp_c DOUBLE,"
        "has_pending_params BOOL,"
        "pending_params_age_ms BIGINT"
        ") TAGS ("
        "device_id BINARY(128),"
        "mqtt_topic BINARY(255)"
        ")"
    )


def clear_td_for_devices(td: TdengineClient, database: str, device_codes: Iterable[str]) -> None:
    for code in device_codes:
        td.query(f"DELETE FROM {database}.telemetry WHERE device_id={q(code)}")


def clear_td_demo_runs(td: TdengineClient, database: str, *, device_code: str, scenario_key: str | None = None) -> None:
    if scenario_key:
        run_pattern = f"{DEMO_RUN_PREFIX}_{scenario_key}_%"
    else:
        run_pattern = f"{DEMO_RUN_PREFIX}_%"
    td.query(
        f"DELETE FROM {database}.telemetry "
        f"WHERE device_id={q(device_code)} AND run_id LIKE {q(run_pattern)}"
    )


def ensure_device_and_params(db, scenario: ScenarioDef, forced_device_id: int | None = None) -> tuple[Device, DeviceParameter]:
    if forced_device_id is not None:
        device = db.scalar(select(Device).where(Device.id == forced_device_id))
        if not device:
            raise RuntimeError(f"Device id={forced_device_id} not found")
        device.name = scenario.device_name
        device.line = scenario.line
        device.location = scenario.location
        device.code = device.code
        device.target_temp = scenario.target_temp
        device.current_temp = scenario.target_temp
        device.pwm_output = 48.0
        device.is_online = True
        device.is_alarm = False
    else:
        device = db.scalar(select(Device).where(Device.code == scenario.device_code))
        if not device:
            device = Device(
                code=scenario.device_code,
                name=scenario.device_name,
                line=scenario.line,
                location=scenario.location,
                status="active",
                target_temp=scenario.target_temp,
                current_temp=scenario.target_temp,
                pwm_output=48.0,
                is_alarm=False,
                is_online=True,
            )
            db.add(device)
            db.flush()
        else:
            device.name = scenario.device_name
            device.line = scenario.line
            device.location = scenario.location
            device.target_temp = scenario.target_temp
            device.current_temp = scenario.target_temp
            device.is_online = True

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
    if not params:
        params = DeviceParameter(
            device_id=device.id,
            kp=scenario.current_params[0],
            ki=scenario.current_params[1],
            kd=scenario.current_params[2],
            control_mode="pid_control",
            target_band=TARGET_BAND,
            overshoot_limit_pct=3.0,
            saturation_warn_ratio=0.3,
            saturation_high_ratio=0.6,
            pwm_saturation_threshold=PWM_SAT_THRESHOLD,
            steady_window_samples=12,
            sampling_period_ms=250,
            upload_period_s=10,
            updated_by="pav-demo-seed",
        )
        db.add(params)
        db.flush()
    else:
        params.kp = scenario.current_params[0]
        params.ki = scenario.current_params[1]
        params.kd = scenario.current_params[2]
        params.control_mode = "pid_control"
        params.target_band = TARGET_BAND
        params.pwm_saturation_threshold = PWM_SAT_THRESHOLD
        params.updated_by = "pav-demo-seed"

    return device, params


def ensure_user_access(db, device_id: int) -> None:
    all_users = db.scalars(select(User)).all()
    existing = {
        int(row[0])
        for row in db.execute(select(UserDevice.user_id).where(UserDevice.device_id == device_id)).all()
    }
    for user in all_users:
        if user.id not in existing:
            db.add(UserDevice(user_id=user.id, device_id=device_id))


def profile_error(profile: str, i: int) -> float:
    if profile == "success_before":
        return 1.40 * math.exp(-i / 60.0) + 0.55 * math.sin(i / 3.5)
    if profile == "success_after":
        return 0.36 * math.exp(-i / 35.0) + 0.15 * math.sin(i / 6.0)
    if profile == "partial_before":
        return 0.88 * math.exp(-i / 55.0) + 0.30 * math.sin(i / 4.5)
    if profile == "partial_after":
        return 0.78 * math.exp(-i / 55.0) + 0.25 * math.sin(i / 4.8)
    if profile == "mismatch_before":
        return 1.05 * math.exp(-i / 50.0) + 0.35 * math.sin(i / 4.0)
    if profile == "mismatch_after":
        bump = 0.55 if 8 <= i <= 22 else 0.0
        return 0.92 * math.exp(-i / 60.0) + 0.50 * math.sin(i / 3.8) + bump
    if profile == "insufficient_before":
        return 0.95 * math.exp(-i / 45.0) + 0.35 * math.sin(i / 4.2)
    if profile == "insufficient_after":
        return 0.70 + 0.20 * math.sin(i / 2.0)
    if profile == "success_preview":
        return 0.30 * math.exp(-i / 34.0) + 0.12 * math.sin(i / 6.3)
    if profile == "partial_preview":
        return 0.62 * math.exp(-i / 58.0) + 0.20 * math.sin(i / 5.2)
    if profile == "mismatch_preview":
        return 0.30 * math.exp(-i / 34.0) + 0.14 * math.sin(i / 6.4)
    if profile == "insufficient_preview":
        return 0.55 * math.exp(-i / 44.0) + 0.17 * math.sin(i / 4.3)
    return 0.0


def generate_window(
    *,
    profile: str,
    target_temp: float,
    start_ms: int,
    point_count: int,
    step_ms: int,
    run_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    integral = 0.0
    for i in range(point_count):
        ts_ms = start_ms + i * step_ms
        error = profile_error(profile, i)
        sensor = target_temp - error
        error_c = calc_error_c(target_temp, sensor)
        integral += error * (step_ms / 1000.0)
        pwm = max(8, min(99, int(round(46 + abs(error) * 28 + max(0.0, error) * 9 + 4 * math.sin(i / 4.0)))))
        saturation_state = "high" if pwm >= 85 else ("medium" if pwm >= 70 else "normal")
        rows.append(
            {
                "ts_ms": ts_ms,
                "target_temp_c": round(target_temp, 4),
                "sensor_temp_c": round(sensor, 4),
                "sim_temp_c": round(sensor + error_c * 0.05, 4),
                "error_c": round(error_c, 4),
                "integral_error": round(integral, 4),
                "control_output": round(pwm * 2.05, 4),
                "pwm_duty": int(pwm),
                "pwm_norm": round(pwm / 255.0, 6),
                "saturation_state": saturation_state,
                "run_id": run_id,
            }
        )
    return rows


def rows_to_points(rows: list[dict[str, Any]]) -> list[ObservedTelemetryPoint]:
    return [
        ObservedTelemetryPoint(
            ts_ms=int(r["ts_ms"]),
            temp=float(r["sensor_temp_c"]),
            target_temp=float(r["target_temp_c"]),
            error=float(r["error_c"]),
            pwm_output=float(r["pwm_duty"]),
            saturation_state=str(r["saturation_state"]),
        )
        for r in rows
    ]


def preview_profile_for_scenario(scenario_key: str) -> str:
    if scenario_key == "success":
        return "success_preview"
    if scenario_key == "partial":
        return "partial_preview"
    if scenario_key == "preview_mismatch":
        return "mismatch_preview"
    return "insufficient_preview"


def rows_to_preview_curve(*, rows: list[dict[str, Any]], anchor_ms: int) -> list[dict[str, Any]]:
    curve: list[dict[str, Any]] = []
    for row in rows:
        rel_sec = max(0.0, (int(row["ts_ms"]) - int(anchor_ms)) / 1000.0)
        curve.append(
            {
                "time_s": round(rel_sec, 3),
                "temp": round(float(row["sensor_temp_c"]), 4),
                "target_temp": round(float(row["target_temp_c"]), 4),
            }
        )
    return curve


def build_suggestion(
    *,
    scenario: ScenarioDef,
    applied_at: datetime,
    current_params: tuple[float, float, float],
    recommended_params: tuple[float, float, float],
    baseline: PreviewMetrics | None,
    actual: PreviewMetrics | None,
    comparison_before: dict[str, Any] | None,
    comparison_preview: dict[str, Any] | None,
    actual_summary: dict[str, Any] | None,
    preview_metrics: PreviewMetrics | None,
    preview_curve: list[dict[str, Any]],
    insufficient_data: bool,
) -> tuple[str, str, str]:
    delta = {
        "kp": round(recommended_params[0] - current_params[0], 4),
        "ki": round(recommended_params[1] - current_params[1], 4),
        "kd": round(recommended_params[2] - current_params[2], 4),
    }

    reason = f"{DEMO_REASON_PREFIX}:{scenario.key}; effect={scenario.expected_effect}"
    risk = f"{scenario.risk_level}; requires_confirmation=false"

    payload: dict[str, Any] = {
        "t": scenario.problem_type,
        "e": scenario.expected_effect,
        "r": scenario.risk_level,
        "rc": False,
        "cp": {"kp": current_params[0], "ki": current_params[1], "kd": current_params[2]},
        "rp": {"kp": recommended_params[0], "ki": recommended_params[1], "kd": recommended_params[2]},
        "d": delta,
        "evidence": {
            "in_band_ratio": None if baseline is None else round(float(baseline.in_band_ratio), 6),
            "overshoot_c": None if baseline is None else round(float(baseline.overshoot_c), 6),
            "settling_sec": None if baseline is None or baseline.settling_sec is None else round(float(baseline.settling_sec), 6),
            "mean_abs_error": None if baseline is None else round(float(baseline.mean_abs_error), 6),
            "saturation_ratio": None if baseline is None else round(float(baseline.saturation_ratio), 6),
            "temp_swing": None if baseline is None else round(float(baseline.temp_swing), 6),
        },
    }

    meta: dict[str, Any] = {
        "fp": f"pav_demo_{scenario.key}_{applied_at.strftime('%Y%m%d%H%M%S')}",
        "hs": "applied",
        "la": iso_utc(applied_at),
        "apa": iso_utc(applied_at),
        "pew": OBS_WINDOW_MINUTES,
    }

    if insufficient_data:
        meta.update(
            {
                "pei": True,
                "aee": False,
                "pvs": {
                    "recommended_curve": preview_curve,
                    "recommended_metrics": None
                    if preview_metrics is None
                    else {
                        "in_band_ratio": round(float(preview_metrics.in_band_ratio), 6),
                        "overshoot_c": round(float(preview_metrics.overshoot_c), 6),
                        "settling_sec": None if preview_metrics.settling_sec is None else round(float(preview_metrics.settling_sec), 6),
                        "mean_abs_error": round(float(preview_metrics.mean_abs_error), 6),
                        "saturation_ratio": round(float(preview_metrics.saturation_ratio), 6),
                        "temp_swing": round(float(preview_metrics.temp_swing), 6),
                    },
                },
            }
        )
    elif actual is not None and actual_summary is not None:
        evaluated_at = applied_at + timedelta(minutes=OBS_WINDOW_MINUTES, seconds=90)
        meta.update(
            {
                "aee": True,
                "pei": False,
                "pea": iso_utc(evaluated_at),
                "pe": actual_summary,
                "pecb": comparison_before,
                "pecp": comparison_preview,
                "pvs": {
                    "recommended_curve": preview_curve,
                    "recommended_metrics": None
                    if preview_metrics is None
                    else {
                        "in_band_ratio": round(float(preview_metrics.in_band_ratio), 6),
                        "overshoot_c": round(float(preview_metrics.overshoot_c), 6),
                        "settling_sec": None if preview_metrics.settling_sec is None else round(float(preview_metrics.settling_sec), 6),
                        "mean_abs_error": round(float(preview_metrics.mean_abs_error), 6),
                        "saturation_ratio": round(float(preview_metrics.saturation_ratio), 6),
                        "temp_swing": round(float(preview_metrics.temp_swing), 6),
                    },
                },
            }
        )
    else:
        meta["pvs"] = {"recommended_curve": preview_curve}

    payload["m"] = meta
    suggestion = json.dumps({"f": "ai_rec", "v": "1", "p": payload}, separators=(",", ":"), ensure_ascii=True)
    return reason, risk, suggestion


def insert_td_rows(
    td: TdengineClient,
    *,
    database: str,
    device_code: str,
    rows: list[dict[str, Any]],
    control_mode: str,
    kp: float,
    ki: float,
    kd: float,
    stage_suffix: str,
) -> None:
    subtable = f"{database}.telemetry_{safe_table_suffix(device_code)}_{stage_suffix}"
    topic = f"edge/temperature/{device_code}/telemetry"
    for idx, row in enumerate(rows):
        sql = (
            f"INSERT INTO {subtable} USING {database}.telemetry TAGS ({q(device_code)}, {q(topic)}) "
            "(ts,uptime_ms,target_temp_c,sim_temp_c,sensor_temp_c,error_c,integral_error,control_output,pwm_duty,pwm_norm,"
            "control_period_ms,saturation_state,sensor_valid,run_id,control_mode,controller_version,kp,ki,kd,system_state,"
            "sensor_status,actual_dt_ms,dt_error_ms,wifi_connected,mqtt_connected,mqtt_reconnect_count,mqtt_publish_fail_count,"
            "safety_output_forced_off,fault_latched,fault_reason,software_max_safe_temp_c,has_pending_params,pending_params_age_ms) VALUES ("
            f"{int(row['ts_ms'])},{5_000_000 + idx * STEP_SECONDS * 1000},{float(row['target_temp_c']):.4f},{float(row['sim_temp_c']):.4f},"
            f"{float(row['sensor_temp_c']):.4f},{float(row['error_c']):.4f},{float(row['integral_error']):.4f},{float(row['control_output']):.4f},"
            f"{int(row['pwm_duty'])},{float(row['pwm_norm']):.6f},{STEP_SECONDS * 1000},{q(str(row['saturation_state']))},true,{q(str(row['run_id']))},"
            f"{q(control_mode)},{q('demo-seed-v1')},{kp:.4f},{ki:.4f},{kd:.4f},{q('running')},{q('ok')},{STEP_SECONDS * 1000},0,true,true,0,0,false,false,{q('')},65.0,false,0)"
        )
        td.query(sql)


def resolve_selected_scenarios(requested: list[str] | None) -> list[str]:
    if not requested:
        return list(DEFAULT_SCENARIOS)
    selected: list[str] = []
    for raw in requested:
        key = SCENARIO_ALIASES[raw]
        if key not in selected:
            selected.append(key)
    return selected


def reset_demo_data(db, td: TdengineClient, *, drop_demo_devices: bool) -> None:
    demo_codes = [s.device_code for s in SCENARIOS.values()]
    db.execute(delete(AIRecommendation).where(AIRecommendation.reason.like(f"{DEMO_REASON_PREFIX}:%")))
    if drop_demo_devices:
        for code in demo_codes:
            device = db.scalar(select(Device).where(Device.code == code))
            if device:
                db.delete(device)
    db.commit()

    clear_td_for_devices(td, settings.tdengine_database, demo_codes)


def seed_scenario(db, td: TdengineClient, scenario: ScenarioDef, forced_device_id: int | None = None) -> None:
    device, params = ensure_device_and_params(db, scenario, forced_device_id=forced_device_id)
    ensure_user_access(db, device.id)
    if forced_device_id is None and device.code == scenario.device_code:
        clear_td_for_devices(td, settings.tdengine_database, [device.code])
    else:
        clear_td_demo_runs(td, settings.tdengine_database, device_code=device.code, scenario_key=scenario.key)
    db.execute(
        delete(AIRecommendation).where(
            AIRecommendation.device_id == device.id,
            AIRecommendation.reason.like(f"{DEMO_REASON_PREFIX}:%"),
        )
    )

    now = datetime.utcnow().replace(microsecond=0)
    applied_at = now - timedelta(minutes=scenario.apply_minutes_ago)
    step_ms = STEP_SECONDS * 1000

    before_start_ms = int((applied_at - timedelta(minutes=OBS_WINDOW_MINUTES)).timestamp() * 1000)
    before_rows = generate_window(
        profile=scenario.before_profile,
        target_temp=scenario.target_temp,
        start_ms=before_start_ms,
        point_count=POINTS_PER_WINDOW,
        step_ms=step_ms,
        run_id=f"{DEMO_RUN_PREFIX}_{scenario.key}_baseline",
    )

    after_points = 2 if scenario.insufficient_data else POINTS_PER_WINDOW
    after_start_ms = int((applied_at + timedelta(seconds=STEP_SECONDS)).timestamp() * 1000)
    after_rows = generate_window(
        profile=scenario.after_profile,
        target_temp=scenario.target_temp,
        start_ms=after_start_ms,
        point_count=after_points,
        step_ms=step_ms,
        run_id=f"{DEMO_RUN_PREFIX}_{scenario.key}_actual",
    )

    preview_start_ms = int(applied_at.timestamp() * 1000)
    preview_rows = generate_window(
        profile=preview_profile_for_scenario(scenario.key),
        target_temp=scenario.target_temp,
        start_ms=preview_start_ms,
        point_count=POINTS_PER_WINDOW,
        step_ms=step_ms,
        run_id=f"{DEMO_RUN_PREFIX}_{scenario.key}_preview",
    )

    insert_td_rows(
        td,
        database=settings.tdengine_database,
        device_code=device.code,
        rows=before_rows,
        control_mode=params.control_mode,
        kp=scenario.current_params[0],
        ki=scenario.current_params[1],
        kd=scenario.current_params[2],
        stage_suffix=f"{scenario.key}_before",
    )
    insert_td_rows(
        td,
        database=settings.tdengine_database,
        device_code=device.code,
        rows=after_rows,
        control_mode=params.control_mode,
        kp=scenario.recommended_params[0],
        ki=scenario.recommended_params[1],
        kd=scenario.recommended_params[2],
        stage_suffix=f"{scenario.key}_after",
    )

    evaluator = PostEffectEvaluator()
    baseline_metrics = evaluator.calc_metrics(points=rows_to_points(before_rows), target_band=TARGET_BAND, pwm_saturation_threshold=PWM_SAT_THRESHOLD)
    actual_metrics = evaluator.calc_metrics(points=rows_to_points(after_rows), target_band=TARGET_BAND, pwm_saturation_threshold=PWM_SAT_THRESHOLD)
    preview_metrics = evaluator.calc_metrics(
        points=rows_to_points(preview_rows),
        target_band=TARGET_BAND,
        pwm_saturation_threshold=PWM_SAT_THRESHOLD,
    )
    preview_curve = rows_to_preview_curve(rows=preview_rows, anchor_ms=int(applied_at.timestamp() * 1000))

    comparison_before: dict[str, Any] | None = None
    comparison_preview: dict[str, Any] | None = None
    actual_summary: dict[str, Any] | None = None

    if scenario.completed and baseline_metrics is not None and actual_metrics is not None:
        comparison_before = evaluator.compare(reference=baseline_metrics, actual=actual_metrics).model_dump(mode="json")
        if preview_metrics is not None:
            comparison_preview = evaluator.compare(reference=preview_metrics, actual=actual_metrics).model_dump(mode="json")
        actual_summary = evaluator.build_actual_summary(points=rows_to_points(after_rows), metrics=actual_metrics).model_dump(mode="json")

    reason, risk, suggestion = build_suggestion(
        scenario=scenario,
        applied_at=applied_at,
        current_params=scenario.current_params,
        recommended_params=scenario.recommended_params,
        baseline=baseline_metrics,
        actual=actual_metrics,
        comparison_before=comparison_before,
        comparison_preview=comparison_preview,
        actual_summary=actual_summary,
        preview_metrics=preview_metrics,
        preview_curve=preview_curve,
        insufficient_data=scenario.insufficient_data,
    )

    recommendation = AIRecommendation(
        device_id=device.id,
        reason=reason,
        suggestion=suggestion,
        confidence=0.92 if scenario.key == "success" else (0.74 if scenario.key == "preview_mismatch" else 0.80),
        risk=risk,
        last_run_at=applied_at,
    )
    db.add(recommendation)

    device.current_temp = float(after_rows[-1]["sensor_temp_c"]) if after_rows else device.current_temp
    device.target_temp = scenario.target_temp
    device.pwm_output = float(after_rows[-1]["pwm_duty"]) if after_rows else device.pwm_output
    device.updated_at = now

    db.commit()

    print(f"[seed] {scenario.title}: device={device.code} recommendation_id={recommendation.id} applied_at={iso_utc(applied_at)}")


def main() -> None:
    args = parse_args()
    selected = resolve_selected_scenarios(args.scenario)

    if args.device_id is not None and len(selected) != 1:
        raise SystemExit("--device-id can only be used when exactly one --scenario is provided")

    db = SessionLocal()
    td = TdengineClient()

    try:
        db.execute(text("ALTER TABLE ai_recommendations ALTER COLUMN suggestion TYPE TEXT"))
        db.commit()

        ensure_td_telemetry_schema(td, settings.tdengine_database)

        if args.reset:
            reset_demo_data(db, td, drop_demo_devices=args.drop_demo_devices)
            print("[reset] Existing Post-Apply Validation demo data removed.")

        for key in selected:
            seed_scenario(db, td, SCENARIOS[key], forced_device_id=args.device_id)

        print("\nDemo seed complete.")
        print("Open Post-Apply Validation page and switch devices:")
        for key in selected:
            scenario = SCENARIOS[key]
            print(f"  - {scenario.device_code}: {scenario.title}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
