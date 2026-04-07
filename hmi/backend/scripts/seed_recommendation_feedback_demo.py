#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, select

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import AIRecommendation, Device, DeviceMetric, DeviceParameter
from app.services.ai.post_effect_evaluator import ObservedTelemetryPoint, PostEffectEvaluator
from app.services.ai.preview_simulator import PreviewSimulationConfig, RecommendationPreviewSimulator
from app.services.ai.recommendation_feedback_dataset import RecommendationFeedbackDatasetBuilder
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import (
    CurrentState,
    DeviceIdentity,
    HistoryPoint,
    HistoryWindow,
    PIDParams,
    RecommendationGenerateInput,
)
from app.services.tdengine_client import TdengineClient

DEMO_DEVICE_PREFIX = "RFD-DEMO"


@dataclass
class ScenarioDevice:
    key: str
    code: str
    name: str
    line: str
    location: str
    target_temp: float
    baseline_params: PIDParams


@dataclass
class RecommendationSeedRecord:
    recommendation_id: int
    device_id: int
    scenario: str
    history_state: str
    expected_status: str


@dataclass
class SignalProfile:
    base_offset: float
    amplitude: float
    noise: float
    pwm_base: float
    pwm_amp: float
    drift_per_point: float = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed recommendation feedback demo data into PostgreSQL + TDengine")
    parser.add_argument("--improved-count", type=int, default=12)
    parser.add_argument("--unchanged-count", type=int, default=8)
    parser.add_argument("--worse-count", type=int, default=8)
    parser.add_argument("--insufficient-count", type=int, default=6)
    parser.add_argument("--days-back", type=int, default=3)
    parser.add_argument("--observation-window-minutes", type=int, default=15)
    parser.add_argument("--step-seconds", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260407)
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return sql_quote(str(value))


def sanitize_identifier(value: str) -> str:
    out = re.sub(r"[^a-z0-9_]", "_", value.lower())
    out = out.strip("_") or "unknown"
    if out[0].isdigit():
        out = "t_" + out
    return out


def telemetry_table_name(device_code: str) -> str:
    return f"telemetry_{sanitize_identifier(device_code)}"


def td_query_safe(td: TdengineClient, sql: str) -> None:
    td.query(sql)


def ensure_td_schema(td: TdengineClient, db_name: str) -> None:
    td_query_safe(td, f"CREATE DATABASE IF NOT EXISTS {db_name} PRECISION 'ms'")
    td_query_safe(
        td,
        f"""
        CREATE STABLE IF NOT EXISTS {db_name}.telemetry (
          ts TIMESTAMP,
          uptime_ms BIGINT,
          target_temp_c DOUBLE,
          sim_temp_c DOUBLE,
          sensor_temp_c DOUBLE,
          error_c DOUBLE,
          integral_error DOUBLE,
          control_output DOUBLE,
          pwm_duty INT,
          pwm_norm DOUBLE,
          control_period_ms BIGINT,
          saturation_state VARCHAR(32),
          sensor_valid BOOL,
          run_id VARCHAR(128),
          control_mode VARCHAR(64),
          controller_version VARCHAR(64),
          kp DOUBLE,
          ki DOUBLE,
          kd DOUBLE,
          system_state VARCHAR(64),
          sensor_status VARCHAR(32),
          actual_dt_ms BIGINT,
          dt_error_ms BIGINT,
          wifi_connected BOOL,
          mqtt_connected BOOL,
          mqtt_reconnect_count BIGINT,
          mqtt_publish_fail_count BIGINT,
          safety_output_forced_off BOOL,
          fault_latched BOOL,
          fault_reason VARCHAR(255),
          software_max_safe_temp_c DOUBLE,
          has_pending_params BOOL,
          pending_params_age_ms BIGINT
        ) TAGS (
          device_id BINARY(128),
          mqtt_topic BINARY(255)
        )
        """.strip(),
    )


def reset_td_demo_data(td: TdengineClient, db_name: str) -> None:
    try:
        td_query_safe(td, f"DELETE FROM {db_name}.telemetry WHERE device_id LIKE '{DEMO_DEVICE_PREFIX}-%'")
    except Exception:
        # Fallback for environments where tag filtering on DELETE is restricted.
        pass

    try:
        result = td.query(f"SHOW TABLES FROM {db_name}")
    except Exception:
        return
    for row in result.rows:
        if not row:
            continue
        table_name = str(row[0])
        if table_name.startswith("telemetry_" + sanitize_identifier(DEMO_DEVICE_PREFIX + "-")):
            try:
                td_query_safe(td, f"DROP TABLE IF EXISTS {db_name}.{table_name}")
            except Exception:
                continue


def reset_postgres_demo_data(db) -> None:
    demo_devices = db.scalars(select(Device).where(Device.code.like(f"{DEMO_DEVICE_PREFIX}-%"))).all()
    if not demo_devices:
        return
    device_ids = [d.id for d in demo_devices]
    db.execute(delete(AIRecommendation).where(AIRecommendation.device_id.in_(device_ids)))
    db.execute(delete(DeviceMetric).where(DeviceMetric.device_id.in_(device_ids)))
    db.execute(delete(DeviceParameter).where(DeviceParameter.device_id.in_(device_ids)))
    db.execute(delete(Device).where(Device.id.in_(device_ids)))
    db.commit()


def upsert_device_and_params(db, *, definition: ScenarioDevice) -> tuple[Device, DeviceParameter]:
    now = datetime.utcnow()
    device = db.scalar(select(Device).where(Device.code == definition.code))
    if device is None:
        device = Device(
            code=definition.code,
            name=definition.name,
            line=definition.line,
            location=definition.location,
            status="active",
            current_temp=definition.target_temp - 1.2,
            target_temp=definition.target_temp,
            pwm_output=52.0,
            is_alarm=False,
            is_online=True,
            created_at=now,
            updated_at=now,
        )
        db.add(device)
        db.flush()
    else:
        device.name = definition.name
        device.line = definition.line
        device.location = definition.location
        device.target_temp = definition.target_temp
        device.updated_at = now

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
    if params is None:
        params = DeviceParameter(
            device_id=device.id,
            kp=definition.baseline_params.kp,
            ki=definition.baseline_params.ki,
            kd=definition.baseline_params.kd,
            control_mode="pid_control",
            target_band=0.5,
            overshoot_limit_pct=3.0,
            saturation_warn_ratio=0.3,
            saturation_high_ratio=0.6,
            pwm_saturation_threshold=85.0,
            steady_window_samples=12,
            sampling_period_ms=250,
            upload_period_s=10,
            updated_at=now,
            updated_by="seed_recommendation_feedback_demo",
        )
        db.add(params)
    else:
        params.kp = definition.baseline_params.kp
        params.ki = definition.baseline_params.ki
        params.kd = definition.baseline_params.kd
        params.control_mode = "pid_control"
        params.target_band = 0.5
        params.pwm_saturation_threshold = 85.0
        params.updated_at = now
        params.updated_by = "seed_recommendation_feedback_demo"

    db.flush()
    return device, params


def build_observed_points(
    *,
    start: datetime,
    minutes: int,
    step_seconds: int,
    target_temp: float,
    params: PIDParams,
    profile: SignalProfile,
    rng: random.Random,
    run_id: str,
) -> tuple[list[ObservedTelemetryPoint], list[dict[str, Any]]]:
    points: list[ObservedTelemetryPoint] = []
    telemetry_rows: list[dict[str, Any]] = []

    total_points = max(2, int((minutes * 60) / max(1, step_seconds)))
    for idx in range(total_points):
        ts = start + timedelta(seconds=idx * step_seconds)
        wave = profile.amplitude * math.sin(idx * 0.42)
        noise = rng.uniform(-profile.noise, profile.noise)
        drift = profile.drift_per_point * idx
        temp = target_temp + profile.base_offset + wave + noise + drift
        error = target_temp - temp

        pwm = profile.pwm_base + abs(error) * 18.0 + profile.pwm_amp * math.sin(idx * 0.33) + rng.uniform(-2.5, 2.5)
        pwm = max(0.0, min(100.0, pwm))
        saturation_state = "high" if pwm >= 85.0 else "none"

        points.append(
            ObservedTelemetryPoint(
                ts_ms=int(ts.timestamp() * 1000),
                temp=round(temp, 6),
                target_temp=round(target_temp, 6),
                error=round(error, 6),
                pwm_output=round(pwm, 6),
                saturation_state=saturation_state,
            )
        )

        telemetry_rows.append(
            {
                "ts_ms": int(ts.timestamp() * 1000),
                "target_temp_c": round(target_temp, 6),
                "sim_temp_c": round(temp, 6),
                "sensor_temp_c": round(temp, 6),
                "error_c": round(error, 6),
                "control_output": round(pwm, 6),
                "pwm_duty": int(round(pwm)),
                "pwm_norm": round(pwm / 100.0, 6),
                "saturation_state": saturation_state,
                "sensor_valid": True,
                "run_id": run_id,
                "control_mode": "pid_control",
                "kp": round(params.kp, 6),
                "ki": round(params.ki, 6),
                "kd": round(params.kd, 6),
            }
        )

    return points, telemetry_rows


def write_td_telemetry_rows(
    *,
    td: TdengineClient,
    db_name: str,
    device_code: str,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    table = telemetry_table_name(device_code)
    topic = f"seed/recommendation-feedback/{device_code}/telemetry"

    statements: list[str] = []
    for row in rows:
        sql = (
            f"INSERT INTO {db_name}.{table} USING {db_name}.telemetry "
            f"TAGS ({sql_quote(device_code)}, {sql_quote(topic)}) "
            f"(ts, uptime_ms, target_temp_c, sim_temp_c, sensor_temp_c, error_c, integral_error, control_output, "
            f"pwm_duty, pwm_norm, control_period_ms, saturation_state, sensor_valid, run_id, control_mode, "
            f"controller_version, kp, ki, kd, system_state, sensor_status, actual_dt_ms, dt_error_ms, wifi_connected, "
            f"mqtt_connected, mqtt_reconnect_count, mqtt_publish_fail_count, safety_output_forced_off, fault_latched, "
            f"fault_reason, software_max_safe_temp_c, has_pending_params, pending_params_age_ms) "
            f"VALUES ("
            f"{row['ts_ms']}, {row['ts_ms']}, {sql_value(row['target_temp_c'])}, {sql_value(row['sim_temp_c'])}, "
            f"{sql_value(row['sensor_temp_c'])}, {sql_value(row['error_c'])}, 0.0, {sql_value(row['control_output'])}, "
            f"{sql_value(row['pwm_duty'])}, {sql_value(row['pwm_norm'])}, 250, {sql_value(row['saturation_state'])}, "
            f"true, {sql_value(row['run_id'])}, {sql_value(row['control_mode'])}, 'seed-v1', {sql_value(row['kp'])}, "
            f"{sql_value(row['ki'])}, {sql_value(row['kd'])}, 'running', 'ok', 250, 0, true, true, 0, 0, false, false, "
            f"NULL, 95.0, false, 0)"
        )
        statements.append(sql)

    for start in range(0, len(statements), 120):
        batch_sql = "; ".join(statements[start : start + 120])
        td_query_safe(td, batch_sql)


def compact_metrics(metrics: dict[str, Optional[float]]) -> list[Optional[float]]:
    # Compact list format: [ib, ov, st, ma, sr, sw]
    return [
        None if metrics.get("in_band_ratio") is None else round(float(metrics.get("in_band_ratio") or 0.0), 3),
        None if metrics.get("overshoot_c") is None else round(float(metrics.get("overshoot_c") or 0.0), 3),
        None if metrics.get("settling_sec") is None else round(float(metrics.get("settling_sec") or 0.0), 3),
        None if metrics.get("mean_abs_error") is None else round(float(metrics.get("mean_abs_error") or 0.0), 3),
        None if metrics.get("saturation_ratio") is None else round(float(metrics.get("saturation_ratio") or 0.0), 3),
        None if metrics.get("temp_swing") is None else round(float(metrics.get("temp_swing") or 0.0), 3),
    ]


def compact_comparison(comparison: dict[str, Optional[float]]) -> list[Optional[float]]:
    # Compact list format: [ib, ov, st, ma, sr, sw]
    return [
        None if comparison.get("in_band_ratio_delta") is None else round(float(comparison.get("in_band_ratio_delta") or 0.0), 3),
        None if comparison.get("overshoot_c_delta") is None else round(float(comparison.get("overshoot_c_delta") or 0.0), 3),
        None if comparison.get("settling_sec_delta") is None else round(float(comparison.get("settling_sec_delta") or 0.0), 3),
        None if comparison.get("mean_abs_error_delta") is None else round(float(comparison.get("mean_abs_error_delta") or 0.0), 3),
        None if comparison.get("saturation_ratio_delta") is None else round(float(comparison.get("saturation_ratio_delta") or 0.0), 3),
        None if comparison.get("temp_swing_delta") is None else round(float(comparison.get("temp_swing_delta") or 0.0), 3),
    ]


def build_history_input(
    *,
    device: Device,
    params: DeviceParameter,
    baseline_points: list[ObservedTelemetryPoint],
) -> RecommendationGenerateInput:
    history_points = [
        HistoryPoint(
            ts_ms=p.ts_ms,
            current_temp=float(p.temp),
            target_temp=float(p.target_temp),
            error=float(p.error),
            pwm_output=float(p.pwm_output),
        )
        for p in baseline_points
    ]
    return RecommendationGenerateInput(
        device=DeviceIdentity(id=device.id, code=device.code, name=device.name),
        current_state=CurrentState(
            current_temp=float(baseline_points[-1].temp),
            target_temp=float(baseline_points[-1].target_temp),
            pwm_output=float(baseline_points[-1].pwm_output),
        ),
        current_params=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        history_window=HistoryWindow(
            start_ms=baseline_points[0].ts_ms,
            end_ms=baseline_points[-1].ts_ms,
            points=history_points,
        ),
        target_band=float(params.target_band),
        steady_window_samples=int(params.steady_window_samples),
        overshoot_limit_pct=float(params.overshoot_limit_pct),
        pwm_saturation_threshold=float(params.pwm_saturation_threshold),
        saturation_warn_ratio=float(params.saturation_warn_ratio),
        saturation_high_ratio=float(params.saturation_high_ratio),
    )


def build_compact_suggestion(
    *,
    current: PIDParams,
    recommended: PIDParams,
    evidence: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    ev_values = [
        None if evidence.get("mean_error") is None else round(float(evidence.get("mean_error") or 0.0), 3),
        None if evidence.get("mean_abs_error") is None else round(float(evidence.get("mean_abs_error") or 0.0), 3),
        None if evidence.get("error_std") is None else round(float(evidence.get("error_std") or 0.0), 3),
        None if evidence.get("temp_swing") is None else round(float(evidence.get("temp_swing") or 0.0), 3),
        None if evidence.get("pwm_mean") is None else round(float(evidence.get("pwm_mean") or 0.0), 3),
        None if evidence.get("pwm_max") is None else round(float(evidence.get("pwm_max") or 0.0), 3),
        None if evidence.get("zero_crossings") is None else int(evidence.get("zero_crossings") or 0),
        None if evidence.get("in_band_ratio") is None else round(float(evidence.get("in_band_ratio") or 0.0), 3),
        None if evidence.get("overshoot_pct") is None else round(float(evidence.get("overshoot_pct") or 0.0), 3),
        None if evidence.get("settling_sec") is None else round(float(evidence.get("settling_sec") or 0.0), 3),
        None if evidence.get("saturation_ratio") is None else round(float(evidence.get("saturation_ratio") or 0.0), 3),
    ]

    payload = {
        "f": "ai_rec",
        "p": {
            # Compact params format to preserve recommendation context under varchar(255).
            "cp": [round(float(current.kp), 3), round(float(current.ki), 3), round(float(current.kd), 3)],
            "rp": [round(float(recommended.kp), 3), round(float(recommended.ki), 3), round(float(recommended.kd), 3)],
            # Compact evidence format:
            # [mean_error, mean_abs_error, error_std, temp_swing, pwm_mean, pwm_max,
            #  zero_crossings, in_band_ratio, overshoot_pct, settling_sec, saturation_ratio]
            "ev": ev_values,
            "m": metadata,
        },
    }
    text = json.dumps(payload, separators=(",", ":"))
    if len(text) > 255:
        # Keep core evidence first; trim less critical tail to satisfy varchar(255).
        # Order retained: mean_error, mean_abs_error, error_std, temp_swing, pwm_mean,
        # in_band_ratio, settling_sec, saturation_ratio.
        trim_order = [5, 6, 8, 9]  # pwm_max, zero_crossings, overshoot_pct, settling_sec(last resort)
        compact = list(ev_values)
        for idx in trim_order:
            if idx < len(compact):
                compact[idx] = None
                payload["p"]["ev"] = compact
                text = json.dumps(payload, separators=(",", ":"))
                if len(text) <= 255:
                    break
    if len(text) > 255:
        raise ValueError(f"Seed suggestion exceeds varchar(255): len={len(text)}")
    return text


def choose_recommended_params(*, base: PIDParams, scenario: str, rng: random.Random) -> PIDParams:
    if scenario == "improved":
        return PIDParams(
            kp=round(base.kp * (1.08 + rng.uniform(0.0, 0.08)), 4),
            ki=round(base.ki * (1.12 + rng.uniform(0.0, 0.08)), 4),
            kd=round(base.kd * (0.95 + rng.uniform(-0.05, 0.05)), 4),
        )
    if scenario == "unchanged":
        return PIDParams(
            kp=round(base.kp * (1.0 + rng.uniform(-0.03, 0.03)), 4),
            ki=round(base.ki * (1.0 + rng.uniform(-0.03, 0.03)), 4),
            kd=round(base.kd * (1.0 + rng.uniform(-0.03, 0.03)), 4),
        )
    if scenario == "worse":
        return PIDParams(
            kp=round(base.kp * (1.20 + rng.uniform(0.0, 0.15)), 4),
            ki=round(base.ki * (1.25 + rng.uniform(0.0, 0.20)), 4),
            kd=round(max(0.0, base.kd * (0.75 + rng.uniform(-0.10, 0.0))), 4),
        )
    return PIDParams(
        kp=round(base.kp * (1.02 + rng.uniform(-0.02, 0.02)), 4),
        ki=round(base.ki * (1.02 + rng.uniform(-0.02, 0.02)), 4),
        kd=round(base.kd * (1.0 + rng.uniform(-0.02, 0.02)), 4),
    )


def scenario_profiles(scenario: str) -> tuple[SignalProfile, SignalProfile]:
    if scenario == "improved":
        return (
            SignalProfile(base_offset=-1.05, amplitude=1.05, noise=0.22, pwm_base=78.0, pwm_amp=13.0),
            SignalProfile(base_offset=-0.18, amplitude=0.28, noise=0.08, pwm_base=54.0, pwm_amp=6.0),
        )
    if scenario == "unchanged":
        return (
            SignalProfile(base_offset=-0.42, amplitude=0.55, noise=0.12, pwm_base=60.0, pwm_amp=8.0),
            SignalProfile(base_offset=-0.40, amplitude=0.52, noise=0.12, pwm_base=60.5, pwm_amp=8.0),
        )
    if scenario == "worse":
        return (
            SignalProfile(base_offset=-0.35, amplitude=0.45, noise=0.10, pwm_base=58.0, pwm_amp=7.0),
            SignalProfile(base_offset=-1.30, amplitude=1.35, noise=0.26, pwm_base=82.0, pwm_amp=15.0),
        )
    return (
        SignalProfile(base_offset=-0.65, amplitude=0.65, noise=0.14, pwm_base=64.0, pwm_amp=8.5),
        SignalProfile(base_offset=-0.60, amplitude=0.68, noise=0.14, pwm_base=64.0, pwm_amp=8.0),
    )


def build_demo_devices() -> dict[str, ScenarioDevice]:
    return {
        "improved": ScenarioDevice(
            key="improved",
            code=f"{DEMO_DEVICE_PREFIX}-IMP-01",
            name="Feedback Demo Improved",
            line="Feedback Lab",
            location="Zone A",
            target_temp=37.0,
            baseline_params=PIDParams(kp=1.9, ki=0.16, kd=0.06),
        ),
        "unchanged": ScenarioDevice(
            key="unchanged",
            code=f"{DEMO_DEVICE_PREFIX}-UNC-01",
            name="Feedback Demo Unchanged",
            line="Feedback Lab",
            location="Zone B",
            target_temp=37.0,
            baseline_params=PIDParams(kp=2.15, ki=0.19, kd=0.07),
        ),
        "worse": ScenarioDevice(
            key="worse",
            code=f"{DEMO_DEVICE_PREFIX}-WOR-01",
            name="Feedback Demo Worse",
            line="Feedback Lab",
            location="Zone C",
            target_temp=37.0,
            baseline_params=PIDParams(kp=1.75, ki=0.14, kd=0.05),
        ),
        "insufficient": ScenarioDevice(
            key="insufficient",
            code=f"{DEMO_DEVICE_PREFIX}-INS-01",
            name="Feedback Demo Insufficient",
            line="Feedback Lab",
            location="Zone D",
            target_temp=37.0,
            baseline_params=PIDParams(kp=2.0, ki=0.17, kd=0.06),
        ),
    }


def compact_iso_seconds(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def seed_one_recommendation(
    *,
    db,
    td: TdengineClient,
    td_db: str,
    device: Device,
    params: DeviceParameter,
    scenario: str,
    applied_at: datetime,
    observation_window_minutes: int,
    step_seconds: int,
    rng: random.Random,
    recommendation_service: RecommendationService,
    preview_simulator: RecommendationPreviewSimulator,
    evaluator: PostEffectEvaluator,
) -> RecommendationSeedRecord:
    before_profile, after_profile = scenario_profiles(scenario)

    run_id = f"seed-{scenario}-{device.code.lower()}-{int(applied_at.timestamp())}"
    baseline_start = applied_at - timedelta(minutes=observation_window_minutes)
    baseline_points, baseline_rows = build_observed_points(
        start=baseline_start,
        minutes=observation_window_minutes,
        step_seconds=step_seconds,
        target_temp=float(device.target_temp),
        params=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        profile=before_profile,
        rng=rng,
        run_id=run_id,
    )

    recommended_params = choose_recommended_params(
        base=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        scenario=scenario,
        rng=rng,
    )

    preview_output = preview_simulator.run(
        current_temp=float(baseline_points[-1].temp),
        target_temp=float(device.target_temp),
        baseline_params=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        recommended_params=recommended_params,
        config=PreviewSimulationConfig(
            horizon_sec=max(180, observation_window_minutes * 60),
            step_sec=max(1, step_seconds),
            target_band=float(params.target_band),
            pwm_saturation_threshold=float(params.pwm_saturation_threshold),
            control_mode="pid_control",
        ),
    )

    history_input = build_history_input(device=device, params=params, baseline_points=baseline_points)
    generated = recommendation_service.generate(history_input)

    actual_points: list[ObservedTelemetryPoint] = []
    actual_rows: list[dict[str, Any]] = []
    actual_status = "completed"

    if scenario == "insufficient":
        if rng.random() < 0.6:
            # insufficient_data: applied but too few points for reliable evaluation
            actual_points, actual_rows = build_observed_points(
                start=applied_at + timedelta(seconds=step_seconds),
                minutes=2,
                step_seconds=step_seconds,
                target_temp=float(device.target_temp),
                params=recommended_params,
                profile=after_profile,
                rng=rng,
                run_id=run_id,
            )
            actual_rows = actual_rows[:3]
            actual_points = actual_points[:3]
            actual_status = "insufficient_data"
        else:
            # pending: applied but not evaluated yet
            actual_points, actual_rows = build_observed_points(
                start=applied_at + timedelta(seconds=step_seconds),
                minutes=observation_window_minutes,
                step_seconds=step_seconds,
                target_temp=float(device.target_temp),
                params=recommended_params,
                profile=after_profile,
                rng=rng,
                run_id=run_id,
            )
            actual_status = "pending"
    else:
        actual_points, actual_rows = build_observed_points(
            start=applied_at + timedelta(seconds=step_seconds),
            minutes=observation_window_minutes,
            step_seconds=step_seconds,
            target_temp=float(device.target_temp),
            params=recommended_params,
            profile=after_profile,
            rng=rng,
            run_id=run_id,
        )

    write_td_telemetry_rows(td=td, db_name=td_db, device_code=device.code, rows=baseline_rows + actual_rows)

    reason = f"{generated.problem_type.value}; effect={generated.expected_effect.value}; demo_seed=true; scenario={scenario}"
    risk = f"{generated.risk_level.value}; requires_confirmation={generated.requires_confirmation}"

    metadata: dict[str, Any] = {
        # Compact metadata keys to keep suggestion varchar(255)-safe.
        "h": "a",  # applied
        "w": int(observation_window_minutes),
    }

    expected_status = "not_applied"
    if actual_status == "completed":
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
            raise RuntimeError("unexpected None metrics in completed scenario")

        comparison_before = evaluator.compare(reference=baseline_metrics, actual=actual_metrics)
        comparison_preview = evaluator.compare(reference=preview_output.recommended_metrics, actual=actual_metrics)
        actual_summary = evaluator.build_actual_summary(points=actual_points, metrics=actual_metrics)

        metadata["a"] = 1
        metadata["i"] = 0
        metadata["cb"] = compact_comparison(comparison_before.model_dump(mode="json"))
        metadata["pv"] = compact_metrics(preview_output.recommended_metrics.model_dump(mode="json"))
        # Compact actual summary list format: [ib, ov, st, ma, sr, sw, pc]
        metadata["pe"] = compact_metrics(
            {
                "in_band_ratio": actual_summary.in_band_ratio_after,
                "overshoot_c": actual_summary.overshoot_c_after,
                "settling_sec": actual_summary.settling_sec_after,
                "mean_abs_error": actual_summary.mean_abs_error_after,
                "saturation_ratio": actual_summary.saturation_ratio_after,
                "temp_swing": actual_summary.temp_swing_after,
            }
        ) + [int(actual_summary.point_count)]
        expected_status = "completed"
    elif actual_status == "insufficient_data":
        metadata["a"] = 0
        metadata["i"] = 1
        metadata["pv"] = compact_metrics(preview_output.recommended_metrics.model_dump(mode="json"))
        expected_status = "insufficient_data"
    else:
        metadata["a"] = 0
        metadata["i"] = 0
        metadata["pv"] = compact_metrics(preview_output.recommended_metrics.model_dump(mode="json"))
        expected_status = "pending"

    suggestion = build_compact_suggestion(
        current=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        recommended=recommended_params,
        evidence=generated.evidence if isinstance(generated.evidence, dict) else {},
        metadata=metadata,
    )

    rec = AIRecommendation(
        device_id=device.id,
        reason=reason,
        suggestion=suggestion,
        confidence=float(generated.confidence),
        risk=risk,
        last_run_at=applied_at - timedelta(minutes=5),
    )
    db.add(rec)
    db.flush()

    device.current_temp = float(actual_points[-1].temp) if actual_points else float(baseline_points[-1].temp)
    device.pwm_output = float(actual_points[-1].pwm_output) if actual_points else float(baseline_points[-1].pwm_output)
    device.target_temp = float(device.target_temp)
    device.updated_at = max(applied_at, rec.last_run_at)

    return RecommendationSeedRecord(
        recommendation_id=rec.id,
        device_id=device.id,
        scenario=scenario,
        history_state="applied",
        expected_status=expected_status,
    )


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    if args.improved_count < 0 or args.unchanged_count < 0 or args.worse_count < 0 or args.insufficient_count < 0:
        raise SystemExit("counts must be >= 0")

    td = TdengineClient()
    if not td.enabled():
        raise SystemExit("TDengine is disabled. Please enable tdengine before seeding recommendation feedback demo data.")

    td_db = settings.tdengine_database
    ensure_td_schema(td, td_db)

    db = SessionLocal()
    recommendation_service = RecommendationService()
    preview_simulator = RecommendationPreviewSimulator()
    evaluator = PostEffectEvaluator()
    dataset_builder = RecommendationFeedbackDatasetBuilder()

    try:
        if args.reset:
            reset_postgres_demo_data(db)
            reset_td_demo_data(td, td_db)

        definitions = build_demo_devices()
        devices: dict[str, tuple[Device, DeviceParameter]] = {}
        for scenario, definition in definitions.items():
            devices[scenario] = upsert_device_and_params(db, definition=definition)

        now = datetime.utcnow().replace(microsecond=0)
        earliest = now - timedelta(days=max(1, args.days_back))

        scenario_plan = (
            ["improved"] * int(args.improved_count)
            + ["unchanged"] * int(args.unchanged_count)
            + ["worse"] * int(args.worse_count)
            + ["insufficient"] * int(args.insufficient_count)
        )
        rng.shuffle(scenario_plan)

        records: list[RecommendationSeedRecord] = []
        for idx, scenario in enumerate(scenario_plan):
            device, params = devices[scenario]
            span_seconds = max(3600, int((now - earliest).total_seconds()))
            offset = rng.randint(0, span_seconds)
            applied_at = earliest + timedelta(seconds=offset)
            # Keep enough room for post-apply observation points.
            latest_allowed = now - timedelta(minutes=max(20, args.observation_window_minutes + 5))
            if applied_at > latest_allowed:
                applied_at = latest_allowed - timedelta(minutes=idx % 13)

            rec_record = seed_one_recommendation(
                db=db,
                td=td,
                td_db=td_db,
                device=device,
                params=params,
                scenario=scenario,
                applied_at=applied_at,
                observation_window_minutes=int(args.observation_window_minutes),
                step_seconds=int(args.step_seconds),
                rng=rng,
                recommendation_service=recommendation_service,
                preview_simulator=preview_simulator,
                evaluator=evaluator,
            )
            records.append(rec_record)

        db.commit()

        demo_rows: list[dict[str, Any]] = []
        demo_device_ids = sorted({record.device_id for record in records})
        for device_id in demo_device_ids:
            demo_rows.extend(dataset_builder.build_feedback_dataset(db=db, device_id=device_id, only_usable=False))
        dataset_builder.validate_feedback_dataset(demo_rows)
        summary = dataset_builder.summarize_feedback_dataset(demo_rows)

        expected_completed = sum(1 for r in records if r.expected_status == "completed")
        expected_insufficient = sum(1 for r in records if r.expected_status == "insufficient_data")
        expected_pending = sum(1 for r in records if r.expected_status == "pending")

        print("[seed-feedback] done")
        print(f"[seed-feedback] total_recommendation_records={len(records)}")
        print(f"[seed-feedback] devices={len(demo_device_ids)}")
        print(f"[seed-feedback] expected_completed={expected_completed}")
        print(f"[seed-feedback] expected_insufficient_data={expected_insufficient}")
        print(f"[seed-feedback] expected_pending={expected_pending}")
        print(
            "[seed-feedback] expected_by_scenario="
            f"improved={args.improved_count}, unchanged={args.unchanged_count}, "
            f"worse={args.worse_count}, insufficient={args.insufficient_count}"
        )

        print("[seed-feedback] dataset_summary")
        print(f"  total recommendation records: {summary.total_recommendation_records}")
        print(f"  unique recommendation ids: {summary.unique_recommendation_ids}")
        print(f"  duplicate recommendation ids count: {summary.duplicate_recommendation_ids_count}")
        print(f"  applied recommendation records: {summary.applied_recommendation_records}")
        print(f"  evaluated recommendation records: {summary.evaluated_recommendation_records}")
        print(f"  insufficient_data count: {summary.insufficient_data_count}")
        print(f"  trainable samples count: {summary.trainable_samples_count}")
        print(
            "  effect outcome counts: "
            f"improved={summary.improved_count}, "
            f"unchanged={summary.unchanged_count}, "
            f"worse={summary.worse_count}, "
            f"pending={summary.pending_count}"
        )
        print(
            "  preview gap levels: "
            f"low={summary.preview_gap_low_count}, "
            f"medium={summary.preview_gap_medium_count}, "
            f"high={summary.preview_gap_high_count}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
