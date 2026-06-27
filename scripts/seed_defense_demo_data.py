#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import delete, func, select

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "hmi" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import (  # noqa: E402
    AIRecommendation,
    ControlAction,
    ControlActionEvalJob,
    ControlActionFeedbackSample,
    Device,
    DeviceAlarm,
    DeviceMetric,
    DeviceParameter,
    DeviceSummary,
    User,
    UserDevice,
)
from app.services.ai.feature_extractor import extract_features  # noqa: E402
from app.services.ai.post_effect_evaluator import ObservedTelemetryPoint, PostEffectEvaluator  # noqa: E402
from app.services.ai.recommendation_ranker import RecommendationRanker, RecommendationRankingContext  # noqa: E402
from app.services.ai.recommendation_service import RecommendationService  # noqa: E402
from app.services.ai.schemas import (  # noqa: E402
    CurrentState,
    DeviceIdentity,
    HistoryPoint,
    HistoryWindow,
    PIDParams,
    PreviewMetrics,
    RecommendationGenerateInput,
)
from app.services.tdengine_client import TdengineClient  # noqa: E402


DEMO_DEVICE_PREFIX = "DEF-"
DEMO_RUN_PREFIX = "defense_"
TARGET_BAND = 0.5
PWM_SAT_THRESHOLD = 85.0
STEP_SECONDS = 30
POINTS_PER_WINDOW = 60
OBS_WINDOW_MINUTES = 30
DEFAULT_SEED = 20260516
ACTIVE_ARTIFACTS_DIR = BACKEND_ROOT / "artifacts" / "active"
SCENARIO_ORDER = [
    "normal_stable",
    "slow_response",
    "overshoot_high",
    "oscillation",
    "post_apply_success",
    "preview_mismatch",
    "insufficient_data",
    "steady_state_error",
    "saturation_limited",
    "sensor_invalid",
    "over_temperature_safety",
    "ack_success",
    "ack_failure_validation_error",
    "post_apply_partial",
]


@dataclass(frozen=True)
class ScenarioDef:
    key: str
    code: str
    name: str
    target_temp: float
    current_params: tuple[float, float, float]
    recommended_params: tuple[float, float, float]
    problem_type: str
    expected_effect: str
    risk_level: str
    before_profile: str
    preview_profile: str
    after_profile: str
    actual_points: int
    actual_effect_label: Optional[str]
    preview_gap_label: Optional[str]
    explanation: str


SCENARIOS: dict[str, ScenarioDef] = {
    "normal_stable": ScenarioDef(
        key="normal_stable",
        code="DEF-101",
        name="Defense Normal Stable",
        target_temp=23.0,
        current_params=(2.4, 0.32, 0.08),
        recommended_params=(2.4, 0.32, 0.08),
        problem_type="normal",
        expected_effect="keep_stable",
        risk_level="Low",
        before_profile="normal",
        preview_profile="normal",
        after_profile="normal",
        actual_points=0,
        actual_effect_label=None,
        preview_gap_label=None,
        explanation="Stable temperature, no AI adjustment required",
    ),
    "slow_response": ScenarioDef(
        key="slow_response",
        code="DEF-102",
        name="Defense Slow Response",
        target_temp=28.0,
        current_params=(2.0, 0.26, 0.05),
        recommended_params=(2.24, 0.2808, 0.047),
        problem_type="slow_response",
        expected_effect="speed_up_response",
        risk_level="Low",
        before_profile="slow_before",
        preview_profile="slow_after",
        after_profile="slow_after",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="improved",
        preview_gap_label="low",
        explanation="AI problem=slow_response, after curve improves settling",
    ),
    "overshoot_high": ScenarioDef(
        key="overshoot_high",
        code="DEF-103",
        name="Defense Overshoot High",
        target_temp=28.0,
        current_params=(3.0, 0.42, 0.07),
        recommended_params=(2.7, 0.3864, 0.0784),
        problem_type="overshoot_high",
        expected_effect="reduce_overshoot",
        risk_level="Medium",
        before_profile="overshoot_before",
        preview_profile="overshoot_after",
        after_profile="overshoot_after",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="improved",
        preview_gap_label="low",
        explanation="AI problem=overshoot_high, overshoot reduced after apply",
    ),
    "oscillation": ScenarioDef(
        key="oscillation",
        code="DEF-104",
        name="Defense Oscillation",
        target_temp=28.0,
        current_params=(2.8, 0.38, 0.06),
        recommended_params=(2.464, 0.342, 0.069),
        problem_type="oscillation",
        expected_effect="reduce_oscillation",
        risk_level="Medium",
        before_profile="oscillation_before",
        preview_profile="oscillation_after",
        after_profile="oscillation_after",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="improved",
        preview_gap_label="low",
        explanation="AI problem=oscillation, amplitude reduced after apply",
    ),
    "post_apply_success": ScenarioDef(
        key="post_apply_success",
        code="DEF-105",
        name="Defense Post Apply Success",
        target_temp=37.0,
        current_params=(2.2, 0.25, 0.06),
        recommended_params=(2.24, 0.31, 0.056),
        problem_type="steady_state_error",
        expected_effect="reduce_steady_state_error",
        risk_level="Low",
        before_profile="post_success_before",
        preview_profile="post_success_preview",
        after_profile="post_success_actual",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="improved",
        preview_gap_label="low",
        explanation="stable setpoint control improves: mean error, in-band ratio, settling time, and temperature swing all get better",
    ),
    "preview_mismatch": ScenarioDef(
        key="preview_mismatch",
        code="DEF-106",
        name="Defense Preview Mismatch",
        target_temp=37.0,
        current_params=(2.25, 0.27, 0.06),
        recommended_params=(2.29, 0.34, 0.056),
        problem_type="steady_state_error",
        expected_effect="reduce_steady_state_error",
        risk_level="Medium",
        before_profile="mismatch_before",
        preview_profile="mismatch_preview",
        after_profile="mismatch_actual",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="unchanged",
        preview_gap_label="high",
        explanation="preview_gap_label=high; system compares prediction with reality instead of blindly trusting AI",
    ),
    "insufficient_data": ScenarioDef(
        key="insufficient_data",
        code="DEF-107",
        name="Defense Insufficient Data",
        target_temp=37.0,
        current_params=(2.2, 0.31, 0.06),
        recommended_params=(2.464, 0.3348, 0.0564),
        problem_type="slow_response",
        expected_effect="speed_up_response",
        risk_level="Low",
        before_profile="insufficient_before",
        preview_profile="insufficient_preview",
        after_profile="insufficient_actual",
        actual_points=1,
        actual_effect_label=None,
        preview_gap_label=None,
        explanation="evaluation pending/insufficient; no crash when post-apply telemetry is too short",
    ),
    "steady_state_error": ScenarioDef(
        key="steady_state_error",
        code="DEF-108",
        name="Defense Steady State Error",
        target_temp=28.0,
        current_params=(2.1, 0.22, 0.05),
        recommended_params=(2.1, 0.264, 0.05),
        problem_type="steady_state_error",
        expected_effect="reduce_steady_state_error",
        risk_level="Low",
        before_profile="steady_state_before",
        preview_profile="steady_state_after",
        after_profile="steady_state_after",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="improved",
        preview_gap_label="low",
        explanation="AI problem=steady_state_error; long-running same-sign error is reduced after integral tuning",
    ),
    "saturation_limited": ScenarioDef(
        key="saturation_limited",
        code="DEF-109",
        name="Defense Saturation Limited",
        target_temp=35.0,
        current_params=(2.7, 0.38, 0.07),
        recommended_params=(2.55, 0.36, 0.075),
        problem_type="saturation_limited",
        expected_effect="limited_gain_expected",
        risk_level="High",
        before_profile="saturation_before",
        preview_profile="saturation_after",
        after_profile="saturation_after",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="unchanged",
        preview_gap_label="medium",
        explanation="AI problem=saturation_limited; actuator saturation means hardware/load/safety limits must be checked",
    ),
    "sensor_invalid": ScenarioDef(
        key="sensor_invalid",
        code="DEF-110",
        name="Defense Sensor Invalid",
        target_temp=28.0,
        current_params=(2.4, 0.32, 0.08),
        recommended_params=(2.4, 0.32, 0.08),
        problem_type="sensor_invalid",
        expected_effect="safety_output_forced_off",
        risk_level="High",
        before_profile="sensor_invalid",
        preview_profile="normal",
        after_profile="sensor_invalid",
        actual_points=0,
        actual_effect_label=None,
        preview_gap_label=None,
        explanation="sensor_valid=false, fault_latched=true, pwm=0; tuning is blocked by safety",
    ),
    "over_temperature_safety": ScenarioDef(
        key="over_temperature_safety",
        code="DEF-111",
        name="Defense Over Temperature Safety",
        target_temp=28.0,
        current_params=(2.4, 0.32, 0.08),
        recommended_params=(2.4, 0.32, 0.08),
        problem_type="over_temperature_safety",
        expected_effect="safety_output_forced_off",
        risk_level="High",
        before_profile="over_temperature",
        preview_profile="normal",
        after_profile="over_temperature",
        actual_points=0,
        actual_effect_label=None,
        preview_gap_label=None,
        explanation="over-temperature fault forces pwm=0 even though control target still exists",
    ),
    "ack_success": ScenarioDef(
        key="ack_success",
        code="DEF-112",
        name="Defense ACK Success",
        target_temp=28.0,
        current_params=(2.0, 0.26, 0.05),
        recommended_params=(2.24, 0.2808, 0.047),
        problem_type="slow_response",
        expected_effect="speed_up_response",
        risk_level="Low",
        before_profile="ack_success_before",
        preview_profile="slow_after",
        after_profile="ack_success_actual",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label=None,
        preview_gap_label=None,
        explanation="params_set is followed by params_ack success=true; ControlAction status=applied",
    ),
    "ack_failure_validation_error": ScenarioDef(
        key="ack_failure_validation_error",
        code="DEF-113",
        name="Defense ACK Validation Error",
        target_temp=28.0,
        current_params=(2.0, 0.26, 0.05),
        recommended_params=(150.0, 0.2808, 0.047),
        problem_type="slow_response",
        expected_effect="speed_up_response",
        risk_level="High",
        before_profile="ack_failure_before",
        preview_profile="slow_after",
        after_profile="ack_failure_before",
        actual_points=0,
        actual_effect_label=None,
        preview_gap_label=None,
        explanation="illegal kp is rejected by validation_error ACK; device params remain safe",
    ),
    "post_apply_partial": ScenarioDef(
        key="post_apply_partial",
        code="DEF-114",
        name="Defense Post Apply Partial",
        target_temp=37.0,
        current_params=(2.2, 0.31, 0.06),
        recommended_params=(2.464, 0.3348, 0.0564),
        problem_type="slow_response",
        expected_effect="speed_up_response",
        risk_level="Medium",
        before_profile="post_partial_before",
        preview_profile="post_partial_preview",
        after_profile="post_partial_actual",
        actual_points=POINTS_PER_WINDOW,
        actual_effect_label="unchanged",
        preview_gap_label="medium",
        explanation="improvement observed but below expected threshold; useful as a learning-loop sample",
    ),
}


def calc_error_c(target_temp_c: float, sensor_temp_c: float) -> float:
    return float(target_temp_c) - float(sensor_temp_c)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def q(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def sanitize_identifier(value: str) -> str:
    out = "".join(ch.lower() if (ch.isalnum() or ch == "_") else "_" for ch in value).strip("_")
    if not out:
        out = "unknown"
    if out[0].isdigit():
        out = "t_" + out
    return out


def ms_to_utc_naive(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def utc_naive_to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def scenario_keys(value: str) -> list[str]:
    key = value.strip()
    if key == "all":
        return list(SCENARIO_ORDER)
    if key not in SCENARIOS:
        raise SystemExit(f"Unknown scenario: {key}. Expected one of: all, {', '.join(SCENARIO_ORDER)}")
    return [key]


def is_post_apply_scenario(scenario: ScenarioDef) -> bool:
    return scenario.key in {"post_apply_success", "preview_mismatch", "insufficient_data", "post_apply_partial"}


def is_ack_scenario(scenario: ScenarioDef) -> bool:
    return scenario.key in {"ack_success", "ack_failure_validation_error"}


def attempted_params_for(scenario: ScenarioDef) -> tuple[float, float, float]:
    return scenario.recommended_params


def scenario_fault_reason(scenario: ScenarioDef) -> str:
    if scenario.key == "sensor_invalid":
        return "sensor_invalid"
    if scenario.key == "over_temperature_safety":
        return "over_temperature"
    return ""


def profile_error(profile: str, i: int, rng: random.Random) -> float:
    noise = rng.gauss(0.0, 0.025)
    if profile == "normal":
        return 0.18 * math.sin(i / 5.0) + 0.05 * math.sin(i / 11.0) + rng.gauss(0.0, 0.025)
    if profile == "slow_before":
        return max(0.06, 3.8 * math.exp(-i / 8.5) + 0.04 + 0.03 * math.sin(i / 13.0) + rng.gauss(0.0, 0.012))
    if profile == "slow_after":
        return 3.9 * math.exp(-i / 12.0) + 0.08 * math.sin(i / 8.0) + noise
    if profile == "overshoot_before":
        return (
            2.0 * math.exp(-i / 9.0)
            - 2.2 * math.exp(-((i - 17) / 8.0) ** 2)
            + 0.35 * math.sin(i / 4.5) * math.exp(-i / 35.0)
            + noise
        )
    if profile == "overshoot_after":
        return (
            1.6 * math.exp(-i / 9.0)
            - 0.45 * math.exp(-((i - 18) / 9.0) ** 2)
            + 0.12 * math.sin(i / 6.0) * math.exp(-i / 35.0)
            + noise
        )
    if profile == "oscillation_before":
        return 1.25 * math.sin(i / 1.9) * math.exp(-i / 95.0) + 0.18 * math.sin(i / 6.0) + noise
    if profile == "oscillation_after":
        return 0.36 * math.sin(i / 2.4) * math.exp(-i / 55.0) + 0.04 * math.sin(i / 9.0) + noise
    if profile == "post_success_before":
        return 5.4 * math.exp(-i / 17.0) + 0.16 + 0.04 * math.sin(i / 9.0) + noise * 0.35
    if profile == "post_success_preview":
        return 3.16 * math.exp(-i / 9.4) + 0.035
    if profile == "post_success_actual":
        return 3.18 * math.exp(-i / 9.6) + 0.025
    if profile == "mismatch_before":
        return 2.8 * math.exp(-i / 26.0) + 0.18 + noise * 0.15
    if profile == "mismatch_preview":
        return 3.2 * math.exp(-i / 10.0) + 0.05 * math.sin(i / 7.0) + noise
    if profile == "mismatch_actual":
        return 3.15 * math.exp(-i / 30.0) + 0.04 + 0.04 * math.sin(i / 5.0) * math.exp(-i / 60.0) + noise * 0.2
    if profile == "insufficient_before":
        return 3.2 * math.exp(-i / 62.0) + 0.36 + 0.08 * math.sin(i / 7.0) + noise
    if profile == "insufficient_preview":
        return 2.9 * math.exp(-i / 12.0) + 0.05 * math.sin(i / 8.0) + noise
    if profile == "insufficient_actual":
        return 2.3 + 0.1 * math.sin(i / 3.0) + noise
    if profile == "steady_state_before":
        return max(0.72, 1.02 + 0.08 * math.sin(i / 10.0) + rng.gauss(0.0, 0.018))
    if profile == "steady_state_after":
        return max(0.18, 0.36 + 0.06 * math.sin(i / 9.0) + rng.gauss(0.0, 0.018))
    if profile == "saturation_before":
        return max(4.2, 5.9 - 0.7 * min(1.0, i / 59.0) + 0.16 * math.sin(i / 7.0) + rng.gauss(0.0, 0.035))
    if profile == "saturation_after":
        return max(3.7, 4.9 - 0.4 * min(1.0, i / 59.0) + 0.12 * math.sin(i / 8.0) + rng.gauss(0.0, 0.03))
    if profile == "sensor_invalid":
        return 0.18 + 0.04 * math.sin(i / 5.0) + rng.gauss(0.0, 0.015)
    if profile == "over_temperature":
        return -39.0 - 0.45 * math.sin(i / 12.0) + rng.gauss(0.0, 0.08)
    if profile == "ack_success_before":
        return max(0.08, 2.8 * math.exp(-i / 18.0) + 0.22 + 0.05 * math.sin(i / 9.0) + noise)
    if profile == "ack_success_actual":
        return 2.7 * math.exp(-i / 10.0) + 0.05 * math.sin(i / 8.0) + noise
    if profile == "ack_failure_before":
        return max(0.1, 2.4 * math.exp(-i / 18.0) + 0.42 + 0.05 * math.sin(i / 8.0) + noise)
    if profile == "post_partial_before":
        return 2.15 * math.exp(-i / 20.0) + 0.29 + noise * 0.25
    if profile == "post_partial_preview":
        return 2.05 * math.exp(-i / 13.0) + 0.25 + noise * 0.25
    if profile == "post_partial_actual":
        return 2.055 * math.exp(-i / 13.02) + 0.252 + noise * 0.25
    return noise


def generate_rows(
    *,
    scenario: ScenarioDef,
    profile: str,
    run_id: str,
    start_ms: int,
    point_count: int,
    params: tuple[float, float, float],
    rng: random.Random,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    integral = 0.0
    kp, ki, kd = params
    for i in range(point_count):
        ts_ms = start_ms + i * STEP_SECONDS * 1000
        error_c = profile_error(profile, i, rng)
        sensor = scenario.target_temp - error_c
        error_c = calc_error_c(scenario.target_temp, sensor)
        integral += error_c * STEP_SECONDS
        heating_demand = max(0.0, error_c)
        cooling_bias = max(0.0, -error_c)
        pwm = clamp(38.0 + heating_demand * 15.0 + abs(error_c) * 5.0 - cooling_bias * 18.0 + rng.gauss(0, 1.8), 4.0, 98.0)
        if profile.endswith("before") and scenario.problem_type == "slow_response":
            pwm = clamp(54.0 + heating_demand * 4.0 + abs(error_c) * 2.0 + rng.gauss(0, 1.5), 35.0, 78.0)
        if profile == "mismatch_actual":
            pwm = clamp(82.0 + heating_demand * 6.0 + abs(error_c) * 1.8 + rng.gauss(0, 1.0), 68.0, 96.0)
        if profile.startswith("post_partial_"):
            if profile.endswith("before"):
                pwm = clamp(62.0 + 2.0 * math.sin(i / 9.0) + rng.gauss(0, 0.4), 54.0, 68.0)
            elif profile.endswith("preview"):
                pwm = clamp(58.0 + 2.0 * math.sin(i / 10.0) + rng.gauss(0, 0.35), 52.0, 64.0)
            else:
                pwm = clamp(59.0 + 2.0 * math.sin(i / 9.0) + rng.gauss(0, 0.4), 52.0, 66.0)
        if "normal" in profile:
            pwm = clamp(42.0 + 5.0 * math.sin(i / 9.0) + rng.gauss(0, 1.0), 28.0, 58.0)
        if "saturation" in profile:
            pwm = clamp(96.0 + 1.8 * math.sin(i / 6.0) + rng.gauss(0, 0.7), 93.0, 100.0)
        if scenario.key in {"sensor_invalid", "over_temperature_safety"}:
            pwm = 0.0
        saturation_state = "high" if pwm >= 85.0 else ("medium" if pwm >= 70.0 else "normal")
        fault_reason = scenario_fault_reason(scenario)
        fault_latched = bool(fault_reason)
        sensor_valid = scenario.key != "sensor_invalid"
        if scenario.key == "sensor_invalid":
            saturation_state = "safety_off"
            system_state = "fault_latched"
            sensor_status = "invalid"
        elif scenario.key == "over_temperature_safety":
            saturation_state = "safety_off"
            system_state = "fault_latched"
            sensor_status = "ok"
        else:
            system_state = "running"
            sensor_status = "ok"
        rows.append(
            {
                "ts_ms": ts_ms,
                "uptime_ms": max(0, i + 1) * STEP_SECONDS * 1000,
                "target_temp_c": round(scenario.target_temp, 4),
                "sensor_temp_c": round(sensor, 4),
                "sim_temp_c": round(sensor + error_c * 0.04 + rng.gauss(0, 0.01), 4),
                "error_c": round(error_c, 4),
                "integral_error": round(integral, 4),
                "control_output": round(pwm * 2.0, 4),
                "pwm_duty": int(round(pwm)),
                "pwm_norm": round(pwm / 255.0, 6),
                "saturation_state": saturation_state,
                "run_id": run_id,
                "control_mode": "pid_control",
                "controller_version": "defense_demo_orchestrator_v1",
                "kp": round(kp, 4),
                "ki": round(ki, 4),
                "kd": round(kd, 4),
                "system_state": system_state,
                "sensor_status": sensor_status,
                "sensor_valid": sensor_valid,
                "wifi_connected": True,
                "mqtt_connected": True,
                "safety_output_forced_off": fault_latched,
                "fault_latched": fault_latched,
                "fault_reason": fault_reason,
                "software_max_safe_temp_c": 65.0,
                "has_pending_params": False,
                "pending_params_age_ms": 0,
            }
        )
    return rows


def rows_to_points(rows: list[dict[str, Any]]) -> list[ObservedTelemetryPoint]:
    return [
        ObservedTelemetryPoint(
            ts_ms=int(row["ts_ms"]),
            temp=float(row["sensor_temp_c"]),
            target_temp=float(row["target_temp_c"]),
            error=float(row["error_c"]),
            pwm_output=float(row["pwm_duty"]),
            saturation_state=str(row["saturation_state"]),
        )
        for row in rows
    ]


def rows_to_history(rows: list[dict[str, Any]]) -> list[HistoryPoint]:
    return [
        HistoryPoint(
            ts_ms=int(row["ts_ms"]),
            current_temp=float(row["sensor_temp_c"]),
            target_temp=float(row["target_temp_c"]),
            error=float(row["error_c"]),
            pwm_output=float(row["pwm_duty"]),
        )
        for row in rows
    ]


def preview_curve(rows: list[dict[str, Any]], *, anchor_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "time_s": int(max(0, int(row["ts_ms"]) - int(anchor_ms)) / 1000),
            "temp": round(float(row["sensor_temp_c"]), 4),
            "target_temp": round(float(row["target_temp_c"]), 4),
            "pwm_output": round(float(row["pwm_duty"]), 4),
            "error": round(float(row["error_c"]), 4),
        }
        for row in rows
    ]


def metrics_to_dict(metrics: Optional[PreviewMetrics]) -> Optional[dict[str, Any]]:
    if metrics is None:
        return None
    return {
        "in_band_ratio": metrics.in_band_ratio,
        "overshoot_c": metrics.overshoot_c,
        "settling_sec": metrics.settling_sec,
        "mean_abs_error": metrics.mean_abs_error,
        "saturation_ratio": metrics.saturation_ratio,
        "temp_swing": metrics.temp_swing,
    }


def comparison_to_dict(comparison: Any) -> dict[str, Any]:
    return {
        "in_band_ratio_delta": comparison.in_band_ratio_delta,
        "overshoot_c_delta": comparison.overshoot_c_delta,
        "settling_sec_delta": comparison.settling_sec_delta,
        "mean_abs_error_delta": comparison.mean_abs_error_delta,
        "saturation_ratio_delta": comparison.saturation_ratio_delta,
        "temp_swing_delta": comparison.temp_swing_delta,
    }


def actual_summary_dict(points: list[ObservedTelemetryPoint], metrics: PreviewMetrics) -> dict[str, Any]:
    return {
        "observed_window_start": ms_to_utc_naive(points[0].ts_ms).isoformat(timespec="seconds"),
        "observed_window_end": ms_to_utc_naive(points[-1].ts_ms).isoformat(timespec="seconds"),
        "point_count": len(points),
        "in_band_ratio_after": metrics.in_band_ratio,
        "overshoot_c_after": metrics.overshoot_c,
        "settling_sec_after": metrics.settling_sec,
        "mean_abs_error_after": metrics.mean_abs_error,
        "saturation_ratio_after": metrics.saturation_ratio,
        "temp_swing_after": metrics.temp_swing,
    }


def make_recommendation_input(device: Device, params: DeviceParameter, rows: list[dict[str, Any]]) -> RecommendationGenerateInput:
    latest = rows[-1]
    return RecommendationGenerateInput(
        device=DeviceIdentity(id=int(device.id), code=device.code, name=device.name),
        current_state=CurrentState(
            current_temp=float(latest["sensor_temp_c"]),
            target_temp=float(latest["target_temp_c"]),
            pwm_output=float(latest["pwm_duty"]),
        ),
        current_params=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        history_window=HistoryWindow(
            start_ms=int(rows[0]["ts_ms"]),
            end_ms=int(rows[-1]["ts_ms"]),
            points=rows_to_history(rows),
        ),
        target_band=TARGET_BAND,
        steady_window_samples=12,
        overshoot_limit_pct=3.0,
        pwm_saturation_threshold=PWM_SAT_THRESHOLD,
        saturation_warn_ratio=0.3,
        saturation_high_ratio=0.6,
    )


def problem_flags(problem_type: str) -> dict[str, bool]:
    return {
        "saturation_limited": problem_type == "saturation_limited",
        "severe_saturation": problem_type == "saturation_limited",
        "oscillation": problem_type == "oscillation",
        "overshoot_high": problem_type == "overshoot_high",
        "steady_state_error": problem_type == "steady_state_error",
        "slow_response": problem_type == "slow_response",
        "sensor_invalid": problem_type == "sensor_invalid",
        "over_temperature_safety": problem_type == "over_temperature_safety",
        "blocked_by_safety": problem_type in {"sensor_invalid", "over_temperature_safety"},
    }


RANKED_DEMO_SCENARIOS = {
    "steady_state_error",
    "post_apply_success",
    "preview_mismatch",
    "oscillation",
    "overshoot_high",
    "post_apply_partial",
}

RANKING_SELECTION_BY_SCENARIO = {
    "steady_state_error": "aggressive",
    "post_apply_success": "aggressive",
    "preview_mismatch": "aggressive",
    "oscillation": "overshoot_guard",
    "overshoot_high": "overshoot_guard",
    "post_apply_partial": "settling_focus",
}


class DemoProbabilityModel:
    def __init__(self, *, family: str, scenario_key: str) -> None:
        self.family = family
        self.scenario_key = scenario_key
        self.classes_ = ["improved", "unchanged", "worse"] if family == "success" else ["low", "medium", "high"]

    def predict_proba(self, features_df):  # type: ignore[no-untyped-def]
        row = features_df.iloc[0].to_dict()
        candidate = str(row.get("candidate_id") or "")
        # The real runtime model sees only numeric features. The demo ranker injects
        # candidate_id so the controlled replay can make the selected strategy explicit.
        preferred = RANKING_SELECTION_BY_SCENARIO.get(self.scenario_key, "rule_center")
        is_preferred = candidate == preferred
        is_rule_center = candidate == "rule_center"
        is_hold = candidate == "baseline_hold"
        if self.family == "success":
            if is_preferred:
                return [[0.82, 0.14, 0.04]]
            if is_rule_center:
                return [[0.62, 0.28, 0.10]]
            if is_hold:
                return [[0.18, 0.58, 0.24]]
            return [[0.52, 0.34, 0.14]]
        if self.scenario_key == "preview_mismatch" and is_preferred:
            return [[0.28, 0.34, 0.38]]
        if is_preferred:
            return [[0.78, 0.16, 0.06]]
        if is_rule_center:
            return [[0.56, 0.30, 0.14]]
        if is_hold:
            return [[0.42, 0.36, 0.22]]
        return [[0.50, 0.32, 0.18]]


class DemoRecommendationRanker(RecommendationRanker):
    def __init__(self, *, scenario_key: str) -> None:
        super().__init__(
            success_model=DemoProbabilityModel(family="success", scenario_key=scenario_key),
            preview_gap_model=DemoProbabilityModel(family="gap", scenario_key=scenario_key),
            candidate_count=6,
        )
        self.scenario_key = scenario_key
        self.FEATURE_COLUMNS = [*RecommendationRanker.FEATURE_COLUMNS, "candidate_id"]

    def _build_features(self, *, context, candidate, preview_summary):  # type: ignore[no-untyped-def]
        features = super()._build_features(context=context, candidate=candidate, preview_summary=preview_summary)
        features["candidate_id"] = candidate.candidate_id
        return features

    def rank_candidates(self, *, context: RecommendationRankingContext) -> list[dict[str, Any]]:
        ranked = super().rank_candidates(context=context)
        preferred = RANKING_SELECTION_BY_SCENARIO.get(self.scenario_key)
        if preferred:
            ranked.sort(
                key=lambda item: (
                    1 if str(item.get("candidate_id")) == preferred else 0,
                    float(item.get("total_score", 0.0)),
                ),
                reverse=True,
            )
            for idx, item in enumerate(ranked, start=1):
                item["rank"] = idx
        return ranked


def build_demo_runtime_decision(
    *,
    scenario: ScenarioDef,
    device: Device,
    current: PIDParams,
    recommended: PIDParams,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    base_decision: dict[str, Any] = {
        "runtime_source": "seed_defense_demo_data",
        "fallback_used": False,
        "diagnosis_source": "rule_classifier",
        "base_recommendation_source": "rule_tuning_engine",
        "primary_problem_type": scenario.problem_type,
        "secondary_problem_types": [],
        "problem_flags": problem_flags(scenario.problem_type),
        "base_candidate_id": "rule_center",
        "base_recommended_params": {
            "kp": round(float(recommended.kp), 4),
            "ki": round(float(recommended.ki), 4),
            "kd": round(float(recommended.kd), 4),
        },
        "selected_candidate_id": "rule_center",
        "ranking_used": False,
        "ranking_fallback_used": False,
        "candidate_count": 1,
        "evaluated_candidate_count": 1,
        "configured_candidate_limit": 6,
        "top_success_score": 0.86 if scenario.key != "preview_mismatch" else 0.58,
        "top_gap_score": 0.12 if scenario.preview_gap_label == "low" else (0.82 if scenario.preview_gap_label == "high" else None),
        "explanation": scenario.explanation,
        "blocked_by_safety": scenario.key in {"sensor_invalid", "over_temperature_safety"},
        "actuator_limitation": scenario.key == "saturation_limited",
        "ack_seeded": scenario.key in {"ack_success", "ack_failure_validation_error"},
        "ack_status": (
            "applied"
            if scenario.key == "ack_success"
            else "validation_error"
            if scenario.key == "ack_failure_validation_error"
            else None
        ),
        "ack_success": True if scenario.key == "ack_success" else False if scenario.key == "ack_failure_validation_error" else None,
    }
    if scenario.key not in RANKED_DEMO_SCENARIOS:
        return base_decision

    context = RecommendationRankingContext(
        recommendation_id=0,
        device_id=int(device.id),
        device_code=str(device.code),
        baseline_params=current,
        base_recommended_params=recommended,
        evidence=evidence,
        current_temp=float(scenario.target_temp) - float(evidence.get("mean_error") or 0.0),
        target_temp=float(scenario.target_temp),
        target_band=TARGET_BAND,
        pwm_saturation_threshold=PWM_SAT_THRESHOLD,
        control_mode="pid_control",
        predicted_problem_type=scenario.problem_type,
        secondary_problem_types=[],
        problem_flags=problem_flags(scenario.problem_type),
    )
    ranked = DemoRecommendationRanker(scenario_key=scenario.key).rank_candidates(context=context)
    if not ranked:
        return base_decision
    top = ranked[0]
    return {
        **base_decision,
        "ranking_used": True,
        "ranking_fallback_used": False,
        "selected_candidate_id": str(top.get("candidate_id") or "rule_center"),
        "candidate_count": int(len(ranked)),
        "evaluated_candidate_count": int(len(ranked)),
        "configured_candidate_limit": 6,
        "top_score": round(float(top.get("total_score", 0.0)), 4),
        "top_success_score": round(float((top.get("success_model") or {}).get("success_score", 0.0)), 4),
        "top_gap_score": round(float((top.get("preview_gap_model") or {}).get("gap_score", 0.0)), 4),
        "ranked_candidates": ranked,
        "top_1_candidate_id": str(top.get("candidate_id") or "rule_center"),
        "top_1_candidate": {
            "candidate_id": str(top.get("candidate_id") or "rule_center"),
            "rank": int(top.get("rank") or 1),
            "recommended_params": top.get("recommended_params"),
            "delta": top.get("delta"),
            "strategy_note": top.get("strategy_note"),
            "total_score": round(float(top.get("total_score", 0.0)), 4),
            "success_score": round(float((top.get("success_model") or {}).get("success_score", 0.0)), 4),
            "preview_gap_score": round(float((top.get("preview_gap_model") or {}).get("gap_score", 0.0)), 4),
        },
        "demo_replay_note": "Controlled replay of model-ranked candidate selection using the runtime ranker contract.",
    }


def build_recommendation_record(
    *,
    scenario: ScenarioDef,
    device: Device,
    params: DeviceParameter,
    baseline_rows: list[dict[str, Any]],
    preview_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    baseline_metrics: Optional[PreviewMetrics],
    preview_metrics: Optional[PreviewMetrics],
    actual_metrics: Optional[PreviewMetrics],
    evaluator: PostEffectEvaluator,
) -> AIRecommendation:
    payload = make_recommendation_input(device, params, baseline_rows)
    features = extract_features(payload)
    current = PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd))
    recommended = PIDParams(
        kp=float(scenario.recommended_params[0]),
        ki=float(scenario.recommended_params[1]),
        kd=float(scenario.recommended_params[2]),
    )
    delta = PIDParams(
        kp=round(recommended.kp - current.kp, 4),
        ki=round(recommended.ki - current.ki, 4),
        kd=round(recommended.kd - current.kd, 4),
    )
    generated_at = ms_to_utc_naive(int(baseline_rows[-1]["ts_ms"]))
    applied = is_post_apply_scenario(scenario) and scenario.actual_points > 0
    evidence = {
        "rule_saturation_limited": scenario.problem_type == "saturation_limited",
        "rule_severe_saturation": scenario.problem_type == "saturation_limited",
        "rule_oscillation": scenario.problem_type == "oscillation",
        "rule_overshoot_high": scenario.problem_type == "overshoot_high",
        "rule_steady_state_error": scenario.problem_type == "steady_state_error",
        "rule_slow_response": scenario.problem_type == "slow_response",
        "mean_error": round(features.mean_error, 4),
        "mean_abs_error": round(features.mean_abs_error, 4),
        "error_std": round(features.error_std, 4),
        "temp_swing": round(features.temp_swing, 4),
        "pwm_mean": round(features.pwm_mean, 4),
        "pwm_max": round(features.pwm_max, 4),
        "zero_crossings": int(features.zero_crossings),
        "in_band_ratio": round(features.in_band_ratio, 4),
        "overshoot_pct": round(features.overshoot_pct, 4),
        "settling_sec": None if features.settling_sec is None else round(features.settling_sec, 4),
        "saturation_ratio": round(features.saturation_ratio, 4),
    }
    runtime_decision = build_demo_runtime_decision(
        scenario=scenario,
        device=device,
        current=current,
        recommended=recommended,
        evidence=evidence,
    )
    meta: dict[str, Any] = {
        "fp": f"defense-{scenario.key}",
        "hs": "applied" if applied else "generated",
        "lgr": False,
        "rc": 0,
        "la": generated_at.isoformat(timespec="seconds"),
        "pvs": {
            "source": "seed_defense_demo_data",
            "recommended_curve": preview_curve(preview_rows, anchor_ms=int(preview_rows[0]["ts_ms"])),
            "recommended_metrics": metrics_to_dict(preview_metrics),
            "baseline_metrics": metrics_to_dict(baseline_metrics),
        },
        "ard": runtime_decision,
    }
    if scenario.key == "saturation_limited":
        meta["ard"]["engineering_note"] = (
            "actuator saturation; heating capacity may be insufficient; check hardware, load, and safety limit"
        )
    if scenario.key == "post_apply_partial":
        meta["ard"]["engineering_note"] = "improvement observed but below expected threshold"
    if scenario.key in {"sensor_invalid", "over_temperature_safety"}:
        meta["ard"]["engineering_note"] = "safety condition active; parameter tuning is blocked and output is forced off"
    if scenario.key == "ack_failure_validation_error":
        kp_attempt, ki_attempt, kd_attempt = attempted_params_for(scenario)
        meta["ard"]["attempted_params"] = {
            "kp": kp_attempt,
            "ki": ki_attempt,
            "kd": kd_attempt,
            "target_temp_c": scenario.target_temp,
            "failure_reason": "kp_out_of_range",
        }
    if applied:
        applied_at = ms_to_utc_naive(int(actual_rows[0]["ts_ms"])) if actual_rows else generated_at
        meta["apa"] = applied_at.isoformat(timespec="seconds")
        meta["pew"] = OBS_WINDOW_MINUTES
    if scenario.key == "insufficient_data":
        meta.update(
            {
                "aee": False,
                "pei": True,
                "pea": generated_at.isoformat(timespec="seconds"),
                "reason": "not enough post-apply telemetry points",
            }
        )
    elif applied and actual_rows and actual_metrics is not None:
        actual_points = rows_to_points(actual_rows)
        comparison_before = evaluator.compare(reference=baseline_metrics, actual=actual_metrics)
        comparison_preview = evaluator.compare(reference=preview_metrics, actual=actual_metrics)
        meta.update(
            {
                "aee": True,
                "pei": False,
                "pea": ms_to_utc_naive(int(actual_rows[-1]["ts_ms"])).isoformat(timespec="seconds"),
                "pe": actual_summary_dict(actual_points, actual_metrics),
                "pecb": comparison_to_dict(comparison_before),
                "pecp": comparison_to_dict(comparison_preview),
            }
        )

    top_params = runtime_decision.get("top_1_candidate")
    selected_params = top_params.get("recommended_params") if isinstance(top_params, dict) else None
    if isinstance(selected_params, dict) and runtime_decision.get("ranking_used"):
        recommended = PIDParams(
            kp=float(selected_params.get("kp")),
            ki=float(selected_params.get("ki")),
            kd=float(selected_params.get("kd")),
        )
        delta = PIDParams(
            kp=round(recommended.kp - current.kp, 4),
            ki=round(recommended.ki - current.ki, 4),
            kd=round(recommended.kd - current.kd, 4),
        )
    suggestion = json.dumps(
        {
            "f": "ai_rec",
            "v": "2",
            "p": {
                "t": scenario.problem_type,
                "pt": scenario.problem_type,
                "st": [],
                "pf": problem_flags(scenario.problem_type),
                "e": scenario.expected_effect,
                "r": scenario.risk_level,
                "c": 0.9 if scenario.problem_type == "normal" else 0.82,
                "rc": scenario.problem_type != "normal",
                "cp": {"kp": round(current.kp, 4), "ki": round(current.ki, 4), "kd": round(current.kd, 4)},
                "rp": {"kp": round(recommended.kp, 4), "ki": round(recommended.ki, 4), "kd": round(recommended.kd, 4)},
                "d": {"kp": round(delta.kp, 4), "ki": round(delta.ki, 4), "kd": round(delta.kd, 4)},
                "evidence": evidence,
                "m": meta,
            },
        },
        separators=(",", ":"),
    )
    rec = AIRecommendation(
        device_id=device.id,
        reason=f"{scenario.problem_type}; effect={scenario.expected_effect}",
        suggestion=suggestion,
        confidence=0.9 if scenario.problem_type == "normal" else 0.82,
        risk=f"{scenario.risk_level}; requires_confirmation={scenario.problem_type != 'normal'}",
        last_run_at=generated_at,
    )
    return rec


def ensure_td_schema(td: TdengineClient, db_name: str) -> None:
    td.query(f"CREATE DATABASE IF NOT EXISTS {db_name} PRECISION 'ms'")
    ddl = [
        f"""
        CREATE STABLE IF NOT EXISTS {db_name}.telemetry (
          ts TIMESTAMP, uptime_ms BIGINT, target_temp_c DOUBLE, sim_temp_c DOUBLE, sensor_temp_c DOUBLE,
          error_c DOUBLE, integral_error DOUBLE, control_output DOUBLE, pwm_duty INT, pwm_norm DOUBLE,
          control_period_ms BIGINT, saturation_state VARCHAR(32), sensor_valid BOOL, run_id VARCHAR(128),
          control_mode VARCHAR(64), controller_version VARCHAR(64), kp DOUBLE, ki DOUBLE, kd DOUBLE,
          system_state VARCHAR(64), sensor_status VARCHAR(32), actual_dt_ms BIGINT, dt_error_ms BIGINT,
          wifi_connected BOOL, mqtt_connected BOOL, mqtt_reconnect_count BIGINT, mqtt_publish_fail_count BIGINT,
          safety_output_forced_off BOOL, fault_latched BOOL, fault_reason VARCHAR(255), software_max_safe_temp_c DOUBLE,
          has_pending_params BOOL, pending_params_age_ms BIGINT
        ) TAGS (device_id BINARY(128), mqtt_topic BINARY(255))
        """,
        f"""
        CREATE STABLE IF NOT EXISTS {db_name}.telemetry_summary (
          ts TIMESTAMP, run_id VARCHAR(128), window_start_ts TIMESTAMP, window_end_ts TIMESTAMP,
          duration_ms BIGINT, flush_reason VARCHAR(64), sample_count INT, control_period_ms BIGINT,
          uptime_start_ms BIGINT, uptime_end_ms BIGINT, target_temp_avg DOUBLE, sim_temp_avg DOUBLE,
          sensor_temp_avg DOUBLE, sensor_temp_min DOUBLE, sensor_temp_max DOUBLE, error_avg DOUBLE,
          abs_error_avg DOUBLE, abs_error_max DOUBLE, control_output_avg DOUBLE, control_output_min DOUBLE,
          control_output_max DOUBLE, pwm_duty_avg DOUBLE, pwm_duty_min INT, pwm_duty_max INT,
          pwm_norm_avg DOUBLE, pwm_norm_min DOUBLE, pwm_norm_max DOUBLE, control_mode VARCHAR(64),
          system_state VARCHAR(64), kp DOUBLE, ki DOUBLE, kd DOUBLE
        ) TAGS (device_id BINARY(128), mqtt_topic BINARY(255))
        """,
        f"""
        CREATE STABLE IF NOT EXISTS {db_name}.params_ack (
          ts TIMESTAMP, ack_type VARCHAR(64), success BOOL, applied_immediately BOOL, has_pending_params BOOL,
          target_temp_c DOUBLE, kp DOUBLE, ki DOUBLE, kd DOUBLE, control_period_ms BIGINT, control_mode VARCHAR(64),
          reason VARCHAR(255), uptime_ms BIGINT, sensor_valid BOOL, fault_latched BOOL,
          fault_reason VARCHAR(255), software_max_safe_temp_c DOUBLE
        ) TAGS (device_id BINARY(128), mqtt_topic BINARY(255))
        """,
        f"""
        CREATE STABLE IF NOT EXISTS {db_name}.params_set (
          ts TIMESTAMP, target_temp_c DOUBLE, kp DOUBLE, ki DOUBLE, kd DOUBLE,
          control_period_ms BIGINT, control_mode VARCHAR(64), apply_immediately BOOL
        ) TAGS (device_id BINARY(128), mqtt_topic BINARY(255))
        """,
        f"""
        CREATE STABLE IF NOT EXISTS {db_name}.device_status (
          ts TIMESTAMP, last_seen_ts TIMESTAMP, online BOOL, status_reason VARCHAR(64),
          system_state VARCHAR(64), last_message_kind VARCHAR(32)
        ) TAGS (device_id BINARY(128), mqtt_topic BINARY(255))
        """,
        f"""
        CREATE STABLE IF NOT EXISTS {db_name}.alarm_events (
          ts TIMESTAMP, severity VARCHAR(16), source VARCHAR(32), reason VARCHAR(255),
          alarm_event_type VARCHAR(16), triggered_at TIMESTAMP, duration_seconds BIGINT,
          context_json VARCHAR(2048)
        ) TAGS (device_id BINARY(128), rule_code BINARY(128))
        """,
    ]
    for sql in ddl:
        td.query(" ".join(sql.strip().split()))


def td_table(prefix: str, device_code: str) -> str:
    return f"{prefix}_{sanitize_identifier(device_code)}"


def write_td_telemetry(td: TdengineClient, db_name: str, device_code: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    table = td_table("telemetry", device_code)
    topic = f"seed/defense/{device_code}/telemetry"
    statements: list[str] = []
    for row in rows:
        statements.append(
            f"INSERT INTO {db_name}.{table} USING {db_name}.telemetry TAGS ({q(device_code)}, {q(topic)}) "
            "(ts, uptime_ms, target_temp_c, sim_temp_c, sensor_temp_c, error_c, integral_error, control_output, "
            "pwm_duty, pwm_norm, control_period_ms, saturation_state, sensor_valid, run_id, control_mode, "
            "controller_version, kp, ki, kd, system_state, sensor_status, actual_dt_ms, dt_error_ms, wifi_connected, "
            "mqtt_connected, mqtt_reconnect_count, mqtt_publish_fail_count, safety_output_forced_off, fault_latched, "
            "fault_reason, software_max_safe_temp_c, has_pending_params, pending_params_age_ms) "
            f"VALUES ({row['ts_ms']}, {row['uptime_ms']}, {q(row['target_temp_c'])}, {q(row['sim_temp_c'])}, "
            f"{q(row['sensor_temp_c'])}, {q(row['error_c'])}, {q(row['integral_error'])}, {q(row['control_output'])}, "
            f"{q(row['pwm_duty'])}, {q(row['pwm_norm'])}, {STEP_SECONDS * 1000}, {q(row['saturation_state'])}, "
            f"{q(row['sensor_valid'])}, {q(row['run_id'])}, {q(row['control_mode'])}, {q(row['controller_version'])}, {q(row['kp'])}, "
            f"{q(row['ki'])}, {q(row['kd'])}, {q(row['system_state'])}, {q(row['sensor_status'])}, "
            f"{STEP_SECONDS * 1000}, 0, {q(row['wifi_connected'])}, {q(row['mqtt_connected'])}, 0, 0, "
            f"{q(row['safety_output_forced_off'])}, {q(row['fault_latched'])}, {q(row['fault_reason'])}, "
            f"{q(row['software_max_safe_temp_c'])}, {q(row['has_pending_params'])}, {q(row['pending_params_age_ms'])})"
        )
    # TDengine REST accepts one statement per request in common deployments.
    # Keep writes boring and reliable; 721 phase-1 rows are small enough.
    for sql in statements:
        td.query(sql)


def write_td_status(td: TdengineClient, db_name: str, device_code: str, latest_ts_ms: int, system_state: str = "running") -> None:
    table = td_table("device_status", device_code)
    topic = f"seed/defense/{device_code}/status"
    td.query(
        f"INSERT INTO {db_name}.{table} USING {db_name}.device_status TAGS ({q(device_code)}, {q(topic)}) "
        "(ts,last_seen_ts,online,status_reason,system_state,last_message_kind) "
        f"VALUES ({latest_ts_ms},{latest_ts_ms},true,{q('seeded')},{q(system_state)},{q('telemetry')})"
    )


def write_td_params_set(
    td: TdengineClient,
    db_name: str,
    scenario: ScenarioDef,
    ts_ms: int,
    *,
    params: tuple[float, float, float],
    target_temp: Optional[float] = None,
) -> None:
    table = td_table("params_set", scenario.code)
    topic = f"seed/defense/{scenario.code}/params/set"
    kp, ki, kd = params
    target = scenario.target_temp if target_temp is None else target_temp
    td.query(
        f"INSERT INTO {db_name}.{table} USING {db_name}.params_set TAGS ({q(scenario.code)}, {q(topic)}) "
        "(ts,target_temp_c,kp,ki,kd,control_period_ms,control_mode,apply_immediately) "
        f"VALUES ({ts_ms},{q(target)},{q(kp)},{q(ki)},{q(kd)},{STEP_SECONDS * 1000},{q('pid_control')},true)"
    )


def write_td_ack(
    td: TdengineClient,
    db_name: str,
    scenario: ScenarioDef,
    ts_ms: int,
    *,
    success: bool = True,
    ack_type: str = "applied",
    reason: str = "defense demo seeded ack",
    params: Optional[tuple[float, float, float]] = None,
) -> None:
    table = td_table("params_ack", scenario.code)
    topic = f"seed/defense/{scenario.code}/params/ack"
    kp, ki, kd = params or scenario.recommended_params
    td.query(
        f"INSERT INTO {db_name}.{table} USING {db_name}.params_ack TAGS ({q(scenario.code)}, {q(topic)}) "
        "(ts,ack_type,success,applied_immediately,has_pending_params,target_temp_c,kp,ki,kd,control_period_ms,"
        "control_mode,reason,uptime_ms,sensor_valid,fault_latched,fault_reason,software_max_safe_temp_c) "
        f"VALUES ({ts_ms},{q(ack_type)},{q(success)},true,false,{q(scenario.target_temp)},{q(kp)},{q(ki)},{q(kd)},"
        f"{STEP_SECONDS * 1000},{q('pid_control')},{q(reason)},{ts_ms},true,false,{q('')},65.0)"
    )


def write_td_alarm_event(td: TdengineClient, db_name: str, scenario: ScenarioDef, ts_ms: int, reason: str) -> None:
    table = td_table("alarm_events", scenario.code)
    context = json.dumps({"scenario": scenario.key, "source": "seed_defense_demo_data"}, separators=(",", ":"))
    td.query(
        f"INSERT INTO {db_name}.{table} USING {db_name}.alarm_events TAGS ({q(scenario.code)}, {q(reason)}) "
        "(ts,severity,source,reason,alarm_event_type,triggered_at,duration_seconds,context_json) "
        f"VALUES ({ts_ms},{q('critical')},{q('rule_engine')},{q(reason)},{q('active')},{ts_ms},0,{q(context)})"
    )


def write_td_summary(td: TdengineClient, db_name: str, device_code: str, rows: list[dict[str, Any]], flush_reason: str) -> None:
    if not rows:
        return
    table = td_table("telemetry_summary", device_code)
    topic = f"seed/defense/{device_code}/telemetry"
    temps = [float(r["sensor_temp_c"]) for r in rows]
    sim = [float(r["sim_temp_c"]) for r in rows]
    targets = [float(r["target_temp_c"]) for r in rows]
    errors = [float(r["error_c"]) for r in rows]
    outputs = [float(r["control_output"]) for r in rows]
    pwms = [int(r["pwm_duty"]) for r in rows]
    norms = [float(r["pwm_norm"]) for r in rows]
    first, last = rows[0], rows[-1]
    td.query(
        f"INSERT INTO {db_name}.{table} USING {db_name}.telemetry_summary TAGS ({q(device_code)}, {q(topic)}) "
        "(ts,run_id,window_start_ts,window_end_ts,duration_ms,flush_reason,sample_count,control_period_ms,"
        "uptime_start_ms,uptime_end_ms,target_temp_avg,sim_temp_avg,sensor_temp_avg,sensor_temp_min,sensor_temp_max,"
        "error_avg,abs_error_avg,abs_error_max,control_output_avg,control_output_min,control_output_max,pwm_duty_avg,"
        "pwm_duty_min,pwm_duty_max,pwm_norm_avg,pwm_norm_min,pwm_norm_max,control_mode,system_state,kp,ki,kd) "
        f"VALUES ({last['ts_ms']},{q(last['run_id'])},{first['ts_ms']},{last['ts_ms']},{last['ts_ms'] - first['ts_ms']},"
        f"{q(flush_reason)},{len(rows)},{STEP_SECONDS * 1000},{first['uptime_ms']},{last['uptime_ms']},"
        f"{sum(targets)/len(targets):.6f},{sum(sim)/len(sim):.6f},{sum(temps)/len(temps):.6f},{min(temps):.6f},"
        f"{max(temps):.6f},{sum(errors)/len(errors):.6f},{sum(abs(v) for v in errors)/len(errors):.6f},"
        f"{max(abs(v) for v in errors):.6f},{sum(outputs)/len(outputs):.6f},{min(outputs):.6f},{max(outputs):.6f},"
        f"{sum(pwms)/len(pwms):.6f},{min(pwms)},{max(pwms)},{sum(norms)/len(norms):.6f},{min(norms):.6f},"
        f"{max(norms):.6f},{q(last['control_mode'])},{q(last['system_state'])},{q(last['kp'])},{q(last['ki'])},{q(last['kd'])})"
    )


def postgres_delete_plan(db) -> dict[str, int]:
    device_ids = list(db.scalars(select(Device.id).where(Device.code.like(f"{DEMO_DEVICE_PREFIX}%"))).all())
    plan = {"devices": len(device_ids)}
    if not device_ids:
        for key in ("metrics", "summaries", "alarms", "params", "user_links", "recommendations", "actions", "eval_jobs", "feedback"):
            plan[key] = 0
        return plan
    plan["metrics"] = int(db.scalar(select(func.count()).select_from(DeviceMetric).where(DeviceMetric.device_id.in_(device_ids))) or 0)
    plan["summaries"] = int(db.scalar(select(func.count()).select_from(DeviceSummary).where(DeviceSummary.device_id.in_(device_ids))) or 0)
    plan["alarms"] = int(db.scalar(select(func.count()).select_from(DeviceAlarm).where(DeviceAlarm.device_id.in_(device_ids))) or 0)
    plan["params"] = int(db.scalar(select(func.count()).select_from(DeviceParameter).where(DeviceParameter.device_id.in_(device_ids))) or 0)
    plan["user_links"] = int(db.scalar(select(func.count()).select_from(UserDevice).where(UserDevice.device_id.in_(device_ids))) or 0)
    plan["recommendations"] = int(db.scalar(select(func.count()).select_from(AIRecommendation).where(AIRecommendation.device_id.in_(device_ids))) or 0)
    plan["actions"] = int(db.scalar(select(func.count()).select_from(ControlAction).where(ControlAction.device_id.in_(device_ids))) or 0)
    plan["eval_jobs"] = int(db.scalar(select(func.count()).select_from(ControlActionEvalJob).where(ControlActionEvalJob.device_id.in_(device_ids))) or 0)
    plan["feedback"] = int(
        db.scalar(select(func.count()).select_from(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id.in_(device_ids))) or 0
    )
    return plan


def reset_postgres(db, *, dry_run: bool) -> dict[str, int]:
    plan = postgres_delete_plan(db)
    if dry_run or plan["devices"] == 0:
        return plan
    device_ids = list(db.scalars(select(Device.id).where(Device.code.like(f"{DEMO_DEVICE_PREFIX}%"))).all())
    db.execute(delete(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id.in_(device_ids)))
    db.execute(delete(ControlActionEvalJob).where(ControlActionEvalJob.device_id.in_(device_ids)))
    db.execute(delete(ControlAction).where(ControlAction.device_id.in_(device_ids)))
    db.execute(delete(AIRecommendation).where(AIRecommendation.device_id.in_(device_ids)))
    db.execute(delete(DeviceMetric).where(DeviceMetric.device_id.in_(device_ids)))
    db.execute(delete(DeviceSummary).where(DeviceSummary.device_id.in_(device_ids)))
    db.execute(delete(DeviceAlarm).where(DeviceAlarm.device_id.in_(device_ids)))
    db.execute(delete(DeviceParameter).where(DeviceParameter.device_id.in_(device_ids)))
    db.execute(delete(UserDevice).where(UserDevice.device_id.in_(device_ids)))
    db.execute(delete(Device).where(Device.id.in_(device_ids), Device.code.like(f"{DEMO_DEVICE_PREFIX}%")))
    db.commit()
    return plan


def reset_td(td: TdengineClient, db_name: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    for table in ("telemetry", "telemetry_summary", "params_set", "params_ack", "device_status", "alarm_events"):
        for scenario in SCENARIOS.values():
            try:
                td.query(f"DELETE FROM {db_name}.{table} WHERE device_id='{scenario.code}'")
            except Exception:
                pass
        try:
            td.query(f"DELETE FROM {db_name}.{table} WHERE run_id LIKE '{DEMO_RUN_PREFIX}%'")
        except Exception:
            pass


def reset_one_scenario_data(db, scenario: ScenarioDef) -> None:
    """Clear only one DEF demo device before reseeding that scenario."""
    if not scenario.code.startswith(DEMO_DEVICE_PREFIX):
        raise ValueError(f"Refusing to reset non-demo device code: {scenario.code}")
    device = db.scalar(select(Device).where(Device.code == scenario.code))
    if device is None:
        return
    device_id = int(device.id)
    db.execute(delete(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id == device_id))
    db.execute(delete(ControlActionEvalJob).where(ControlActionEvalJob.device_id == device_id))
    db.execute(delete(ControlAction).where(ControlAction.device_id == device_id))
    db.execute(delete(AIRecommendation).where(AIRecommendation.device_id == device_id))
    db.execute(delete(DeviceMetric).where(DeviceMetric.device_id == device_id))
    db.execute(delete(DeviceSummary).where(DeviceSummary.device_id == device_id))
    db.execute(delete(DeviceAlarm).where(DeviceAlarm.device_id == device_id))


def reset_one_scenario_td(td: TdengineClient, db_name: str, scenario: ScenarioDef) -> None:
    if not scenario.code.startswith(DEMO_DEVICE_PREFIX):
        raise ValueError(f"Refusing to reset non-demo device code: {scenario.code}")
    for table in ("telemetry", "telemetry_summary", "params_set", "params_ack", "device_status", "alarm_events"):
        try:
            td.query(f"DELETE FROM {db_name}.{table} WHERE device_id='{scenario.code}'")
        except Exception:
            pass


def ensure_user_visible(db, device: Device) -> None:
    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    if not users:
        return
    for user in users:
        exists = db.scalar(select(UserDevice).where(UserDevice.user_id == user.id, UserDevice.device_id == device.id))
        if exists is None:
            db.add(UserDevice(user_id=user.id, device_id=device.id))


def upsert_device(db, scenario: ScenarioDef, latest: dict[str, Any]) -> tuple[Device, DeviceParameter]:
    now = datetime.utcnow()
    device = db.scalar(select(Device).where(Device.code == scenario.code))
    if device is None:
        device = Device(code=scenario.code, name=scenario.name, line="Defense Demo", location="Seeded Data")
        db.add(device)
        db.flush()
    device.name = scenario.name
    device.line = "Defense Demo"
    device.location = scenario.key
    device.status = "active"
    device.current_temp = float(latest["sensor_temp_c"])
    device.target_temp = float(latest["target_temp_c"])
    device.pwm_output = float(latest["pwm_duty"])
    device.is_alarm = bool(latest.get("fault_latched"))
    device.is_online = True
    device.updated_at = now

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
    if params is None:
        params = DeviceParameter(device_id=device.id)
        db.add(params)
        db.flush()
    params.kp, params.ki, params.kd = [float(x) for x in scenario.current_params]
    params.control_mode = "pid_control"
    params.target_band = TARGET_BAND
    params.pwm_saturation_threshold = PWM_SAT_THRESHOLD
    params.updated_at = now
    params.updated_by = "defense-seed"
    ensure_user_visible(db, device)
    return device, params


def write_postgres_metrics(db, device: Device, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        db.add(
            DeviceMetric(
                device_id=device.id,
                timestamp=ms_to_utc_naive(int(row["ts_ms"])),
                current_temp=float(row["sensor_temp_c"]),
                target_temp=float(row["target_temp_c"]),
                error=float(row["error_c"]),
                pwm_output=float(row["pwm_duty"]),
                status="fault" if bool(row.get("fault_latched")) else "active",
                in_spec=abs(float(row["error_c"])) <= TARGET_BAND,
                is_alarm=bool(row.get("fault_latched")),
            )
        )


def write_postgres_summary(db, device: Device, rows: list[dict[str, Any]], trigger_event: str) -> None:
    if not rows:
        return
    temps = [float(row["sensor_temp_c"]) for row in rows]
    errors = [float(row["error_c"]) for row in rows]
    pwms = [float(row["pwm_duty"]) for row in rows]
    target = float(rows[-1]["target_temp_c"])
    overshoot_pct = max(max(0.0, (temp - target) / max(target, 0.001) * 100.0) for temp in temps)
    db.add(
        DeviceSummary(
            device_id=device.id,
            window_start=ms_to_utc_naive(int(rows[0]["ts_ms"])),
            window_end=ms_to_utc_naive(int(rows[-1]["ts_ms"])),
            sample_count=len(rows),
            avg_temp=sum(temps) / len(temps),
            avg_error=sum(errors) / len(errors),
            max_overshoot_pct=overshoot_pct,
            saturation_ratio=sum(1 for pwm in pwms if pwm >= PWM_SAT_THRESHOLD) / len(pwms),
            trigger_event=trigger_event,
        )
    )


def create_action_feedback(
    *,
    db,
    scenario: ScenarioDef,
    device: Device,
    recommendation: AIRecommendation,
    baseline_metrics: Optional[PreviewMetrics],
    preview_metrics: Optional[PreviewMetrics],
    actual_metrics: Optional[PreviewMetrics],
    actual_rows: list[dict[str, Any]],
    baseline_features: Any,
) -> None:
    if scenario.actual_points <= 0:
        return
    applied_at = ms_to_utc_naive(int(actual_rows[0]["ts_ms"])) if actual_rows else recommendation.last_run_at
    action_status = "pending_eval" if scenario.key == "insufficient_data" else "evaluated"
    kp0, ki0, kd0 = scenario.current_params
    kp1, ki1, kd1 = scenario.recommended_params
    action = ControlAction(
        device_id=device.id,
        source="ai_recommendation",
        source_ref_id=recommendation.id,
        action_type="pid_apply",
        initiated_by="defense-seed",
        applied_at=applied_at,
        status=action_status,
        control_mode_before="pid_control",
        control_mode_after="pid_control",
        target_temp_before=scenario.target_temp,
        target_temp_after=scenario.target_temp,
        kp_before=kp0,
        ki_before=ki0,
        kd_before=kd0,
        kp_after=kp1,
        ki_after=ki1,
        kd_after=kd1,
        delta_kp=round(kp1 - kp0, 4),
        delta_ki=round(ki1 - ki0, 4),
        delta_kd=round(kd1 - kd0, 4),
        context_snapshot={"scenario": scenario.key, "run_id_prefix": DEMO_RUN_PREFIX},
    )
    db.add(action)
    db.flush()

    job_status = "pending" if scenario.key == "insufficient_data" else "done"
    db.add(
        ControlActionEvalJob(
            control_action_id=action.id,
            device_id=device.id,
            status=job_status,
            scheduled_at=applied_at + timedelta(minutes=OBS_WINDOW_MINUTES),
            observation_window_minutes=OBS_WINDOW_MINUTES,
            attempt_count=1 if job_status == "done" else 0,
            last_error="not enough post-apply telemetry points" if scenario.key == "insufficient_data" else None,
        )
    )

    insufficient = scenario.key == "insufficient_data"
    db.add(
        ControlActionFeedbackSample(
            control_action_id=action.id,
            device_id=device.id,
            source="ai_recommendation",
            source_ref_id=recommendation.id,
            action_type="pid_apply",
            initiated_by="defense-seed",
            generated_at=recommendation.last_run_at,
            applied_at=applied_at,
            evaluated_at=None if insufficient else ms_to_utc_naive(int(actual_rows[-1]["ts_ms"])),
            primary_problem_type=scenario.problem_type,
            secondary_problem_types=[],
            problem_flags=problem_flags(scenario.problem_type),
            expected_effect=scenario.expected_effect,
            risk_level=scenario.risk_level,
            confidence=float(recommendation.confidence),
            control_mode_before="pid_control",
            control_mode_after="pid_control",
            target_temp_before=scenario.target_temp,
            target_temp_after=scenario.target_temp,
            kp_before=kp0,
            ki_before=ki0,
            kd_before=kd0,
            kp_after=kp1,
            ki_after=ki1,
            kd_after=kd1,
            delta_kp=round(kp1 - kp0, 4),
            delta_ki=round(ki1 - ki0, 4),
            delta_kd=round(kd1 - kd0, 4),
            mean_error=round(float(baseline_features.mean_error), 4),
            mean_abs_error=round(float(baseline_features.mean_abs_error), 4),
            error_std=round(float(baseline_features.error_std), 4),
            temp_swing=round(float(baseline_features.temp_swing), 4),
            pwm_mean=round(float(baseline_features.pwm_mean), 4),
            pwm_max=round(float(baseline_features.pwm_max), 4),
            zero_crossings=int(baseline_features.zero_crossings),
            in_band_ratio=round(float(baseline_features.in_band_ratio), 4),
            overshoot_pct=round(float(baseline_features.overshoot_pct), 4),
            settling_sec=None if baseline_features.settling_sec is None else round(float(baseline_features.settling_sec), 4),
            saturation_ratio=round(float(baseline_features.saturation_ratio), 4),
            runtime_decision_summary={"scenario": scenario.key, "explanation": scenario.explanation},
            preview_metrics_summary=metrics_to_dict(preview_metrics),
            actual_metrics_summary=metrics_to_dict(actual_metrics),
            comparison_to_before={},
            comparison_to_preview={},
            actual_effect_label=scenario.actual_effect_label,
            preview_gap_label=scenario.preview_gap_label,
            insufficient_data=insufficient,
            sample_quality="reject" if insufficient else ("high" if scenario.preview_gap_label == "low" else "medium"),
            is_training_eligible=not insufficient,
            training_exclusion_reason="not enough post-apply telemetry points" if insufficient else None,
            label_source="seed_defense_demo_data",
        )
    )


def create_ack_action(
    *,
    db,
    scenario: ScenarioDef,
    device: Device,
    recommendation: AIRecommendation,
    baseline_rows: list[dict[str, Any]],
    success: bool,
) -> None:
    ts = ms_to_utc_naive(int(baseline_rows[-1]["ts_ms"]) + 5000)
    kp0, ki0, kd0 = scenario.current_params
    kp1, ki1, kd1 = attempted_params_for(scenario)
    reason = "" if success else "kp_out_of_range"
    db.add(
        ControlAction(
            device_id=device.id,
            source="ai_recommendation",
            source_ref_id=recommendation.id,
            action_type="pid_apply",
            initiated_by="defense-seed",
            applied_at=ts,
            status="applied" if success else "rejected",
            control_mode_before="pid_control",
            control_mode_after="pid_control",
            target_temp_before=scenario.target_temp,
            target_temp_after=scenario.target_temp,
            kp_before=kp0,
            ki_before=ki0,
            kd_before=kd0,
            kp_after=kp1,
            ki_after=ki1,
            kd_after=kd1,
            delta_kp=round(kp1 - kp0, 4),
            delta_ki=round(ki1 - ki0, 4),
            delta_kd=round(kd1 - kd0, 4),
            context_snapshot={
                "scenario": scenario.key,
                "ack_type": "applied" if success else "validation_error",
                "ack_success": success,
                "failure_reason": reason,
                "params_set_topic": f"seed/defense/{scenario.code}/params/set",
                "params_ack_topic": f"seed/defense/{scenario.code}/params/ack",
            },
        )
    )


def create_safety_alarm(db, device: Device, scenario: ScenarioDef, latest_ts_ms: int) -> None:
    reason = scenario_fault_reason(scenario)
    if not reason:
        return
    title = "Sensor Invalid" if reason == "sensor_invalid" else "Over Temperature Safety"
    message = (
        "Sensor read failed; output is forced off."
        if reason == "sensor_invalid"
        else "Sensor temperature exceeded software safety limit; output is forced off."
    )
    db.add(
        DeviceAlarm(
            device_id=device.id,
            level="critical",
            rule_code=reason,
            source="rule_engine",
            title=title,
            message=message,
            is_active=True,
            acknowledged=False,
            created_at=ms_to_utc_naive(latest_ts_ms),
        )
    )


def seed_one_scenario(
    *,
    db,
    td: Optional[TdengineClient],
    db_name: str,
    scenario: ScenarioDef,
    anchor: datetime,
    rng: random.Random,
    dry_run: bool,
) -> dict[str, int]:
    if not dry_run:
        reset_one_scenario_data(db, scenario)
        if td is not None:
            reset_one_scenario_td(td, db_name, scenario)

    if is_post_apply_scenario(scenario):
        actual_start = utc_naive_to_ms(anchor - timedelta(minutes=29))
        baseline_start = actual_start - POINTS_PER_WINDOW * STEP_SECONDS * 1000
    else:
        baseline_start = utc_naive_to_ms(anchor - timedelta(minutes=32))
        actual_start = utc_naive_to_ms(anchor - timedelta(minutes=125))
    preview_start = actual_start
    baseline_rows = generate_rows(
        scenario=scenario,
        profile=scenario.before_profile,
        run_id=f"{DEMO_RUN_PREFIX}{scenario.key}_baseline",
        start_ms=baseline_start,
        point_count=POINTS_PER_WINDOW,
        params=scenario.current_params,
        rng=rng,
    )
    preview_rows = generate_rows(
        scenario=scenario,
        profile=scenario.preview_profile,
        run_id=f"{DEMO_RUN_PREFIX}{scenario.key}_preview",
        start_ms=preview_start,
        point_count=POINTS_PER_WINDOW,
        params=scenario.recommended_params,
        rng=rng,
    )
    actual_rows = generate_rows(
        scenario=scenario,
        profile=scenario.after_profile,
        run_id=f"{DEMO_RUN_PREFIX}{scenario.key}_actual",
        start_ms=actual_start,
        point_count=scenario.actual_points,
        params=scenario.recommended_params,
        rng=rng,
    )
    rows_for_hmi = sorted(actual_rows + baseline_rows, key=lambda row: int(row["ts_ms"]))
    latest = rows_for_hmi[-1]
    if dry_run:
        action_count = 0
        feedback_count = 0
        if is_post_apply_scenario(scenario) and scenario.actual_points > 0:
            action_count = 1
            feedback_count = 1
        elif is_ack_scenario(scenario):
            action_count = 1
        return {
            "devices": 1,
            "telemetry": len(rows_for_hmi),
            "preview_rows": len(preview_rows),
            "recommendations": 1,
            "actions": action_count,
            "feedback": feedback_count,
        }

    evaluator = PostEffectEvaluator()
    baseline_metrics = evaluator.calc_metrics(points=rows_to_points(baseline_rows), target_band=TARGET_BAND, pwm_saturation_threshold=PWM_SAT_THRESHOLD)
    preview_metrics = evaluator.calc_metrics(points=rows_to_points(preview_rows), target_band=TARGET_BAND, pwm_saturation_threshold=PWM_SAT_THRESHOLD)
    actual_metrics = evaluator.calc_metrics(points=rows_to_points(actual_rows), target_band=TARGET_BAND, pwm_saturation_threshold=PWM_SAT_THRESHOLD)

    device, params = upsert_device(db, scenario, latest)
    write_postgres_metrics(db, device, rows_for_hmi)
    write_postgres_summary(db, device, baseline_rows, "defense_baseline")
    if actual_rows:
        write_postgres_summary(db, device, actual_rows, "defense_actual")

    recommendation = build_recommendation_record(
        scenario=scenario,
        device=device,
        params=params,
        baseline_rows=baseline_rows,
        preview_rows=preview_rows,
        actual_rows=actual_rows,
        baseline_metrics=baseline_metrics,
        preview_metrics=preview_metrics,
        actual_metrics=actual_metrics,
        evaluator=evaluator,
    )
    db.add(recommendation)
    db.flush()
    baseline_features = extract_features(make_recommendation_input(device, params, baseline_rows))
    if is_post_apply_scenario(scenario):
        create_action_feedback(
            db=db,
            scenario=scenario,
            device=device,
            recommendation=recommendation,
            baseline_metrics=baseline_metrics,
            preview_metrics=preview_metrics,
            actual_metrics=actual_metrics,
            actual_rows=actual_rows,
            baseline_features=baseline_features,
        )
    if is_ack_scenario(scenario):
        create_ack_action(
            db=db,
            scenario=scenario,
            device=device,
            recommendation=recommendation,
            baseline_rows=baseline_rows,
            success=scenario.key == "ack_success",
        )
    create_safety_alarm(db, device, scenario, int(latest["ts_ms"]))
    if td is not None:
        write_td_telemetry(td, db_name, scenario.code, rows_for_hmi)
        write_td_summary(td, db_name, scenario.code, baseline_rows, "defense_baseline")
        if actual_rows:
            write_td_summary(td, db_name, scenario.code, actual_rows, "defense_actual")
        if is_post_apply_scenario(scenario) and actual_rows:
            write_td_params_set(td, db_name, scenario, int(actual_rows[0]["ts_ms"]), params=scenario.recommended_params)
            write_td_ack(td, db_name, scenario, int(actual_rows[0]["ts_ms"]), success=True, ack_type="applied")
        if scenario.key == "ack_success":
            ack_ts = int(baseline_rows[-1]["ts_ms"]) + 5000
            write_td_params_set(td, db_name, scenario, ack_ts - 1500, params=attempted_params_for(scenario))
            write_td_ack(td, db_name, scenario, ack_ts, success=True, ack_type="applied", reason="parameters applied")
        if scenario.key == "ack_failure_validation_error":
            ack_ts = int(baseline_rows[-1]["ts_ms"]) + 5000
            write_td_params_set(td, db_name, scenario, ack_ts - 1500, params=attempted_params_for(scenario))
            write_td_ack(
                td,
                db_name,
                scenario,
                ack_ts,
                success=False,
                ack_type="validation_error",
                reason="kp_out_of_range",
                params=attempted_params_for(scenario),
            )
        fault_reason = scenario_fault_reason(scenario)
        if fault_reason:
            write_td_alarm_event(td, db_name, scenario, int(rows_for_hmi[-1]["ts_ms"]), fault_reason)
        write_td_status(td, db_name, scenario.code, int(rows_for_hmi[-1]["ts_ms"]), str(latest["system_state"]))

    action_count = 0
    feedback_count = 0
    if is_post_apply_scenario(scenario) and scenario.actual_points > 0:
        action_count = 1
        feedback_count = 1
    elif is_ack_scenario(scenario):
        action_count = 1
    return {
        "devices": 1,
        "telemetry": len(rows_for_hmi),
        "preview_rows": len(preview_rows),
        "recommendations": 1,
        "actions": action_count,
        "feedback": feedback_count,
    }


def print_summary(selected: Iterable[str], totals: Optional[dict[str, int]] = None, *, dry_run: bool = False) -> None:
    prefix = "Defense demo dry-run plan." if dry_run else "Defense demo seed complete."
    print()
    print(prefix)
    if totals:
        print(
            "Totals: "
            + ", ".join(f"{key}={value}" for key, value in totals.items() if isinstance(value, int))
        )
    print()
    print("Devices:")
    for key in selected:
        scenario = SCENARIOS[key]
        print(f"- {scenario.code} {scenario.key}")
        print(f"  Expected: {scenario.explanation}")
    print()
    print("Suggested defense order:")
    print("1. Open dashboard")
    print("2. Open DEF-101 normal_stable as the incubator baseline")
    print("3. Open DEF-108 steady_state_error to show AI diagnoses sustained setpoint bias")
    print("4. Open DEF-104 oscillation if asked about stability around the target")
    print("5. Open DEF-105 post_apply_success to show before / preview / actual improvement")
    print("6. Open DEF-106 preview_mismatch to prove the system validates AI predictions")
    print("7. Open DEF-112 / DEF-113 for MQTT ACK success and validation failure")
    print("8. Open DEF-110 / DEF-111 for safety protection")
    print("9. Keep DEF-102 slow_response as backup, not the main control story")


def print_report(db, td: Optional[TdengineClient], db_name: str) -> None:
    print("Defense demo report")
    devices = db.scalars(select(Device).where(Device.code.like(f"{DEMO_DEVICE_PREFIX}%")).order_by(Device.code.asc())).all()
    device_ids = [int(device.id) for device in devices]
    print()
    print("Service URLs:")
    print("- HMI: http://127.0.0.1:5173")
    print("- Backend docs: http://127.0.0.1:8000/docs")
    print()
    print("Demo readiness:")
    telemetry_rows = 0
    if td is not None:
        try:
            result = td.query(f"SELECT count(*) AS cnt FROM {db_name}.telemetry WHERE device_id LIKE 'DEF-%'")
            telemetry_rows = int(result.rows[0][0]) if result.rows else 0
        except Exception:
            telemetry_rows = 0
    metric_rows = (
        int(db.scalar(select(func.count()).select_from(DeviceMetric).where(DeviceMetric.device_id.in_(device_ids))) or 0)
        if device_ids
        else 0
    )
    rec_rows = (
        int(db.scalar(select(func.count()).select_from(AIRecommendation).where(AIRecommendation.device_id.in_(device_ids))) or 0)
        if device_ids
        else 0
    )
    ranking_rows = 0
    ranking_selected: list[str] = []
    if device_ids:
        recs = db.scalars(select(AIRecommendation).where(AIRecommendation.device_id.in_(device_ids))).all()
        service = RecommendationService()
        device_by_id = {int(device.id): device.code for device in devices}
        for rec in recs:
            decision = service.read_storage_metadata(rec.suggestion).get("ard")
            if not isinstance(decision, dict) or not decision.get("ranking_used"):
                continue
            ranking_rows += 1
            ranking_selected.append(f"{device_by_id.get(int(rec.device_id), rec.device_id)}:{decision.get('selected_candidate_id')}")
    action_rows = (
        int(db.scalar(select(func.count()).select_from(ControlAction).where(ControlAction.device_id.in_(device_ids))) or 0)
        if device_ids
        else 0
    )
    feedback_rows = (
        int(db.scalar(select(func.count()).select_from(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id.in_(device_ids))) or 0)
        if device_ids
        else 0
    )
    safety_alarm_rows = (
        int(db.scalar(select(func.count()).select_from(DeviceAlarm).where(DeviceAlarm.device_id.in_(device_ids))) or 0)
        if device_ids
        else 0
    )
    ack_success_count = 0
    ack_failure_count = 0
    if td is not None:
        try:
            result = td.query(
                f"SELECT count(*) AS cnt FROM {db_name}.params_ack WHERE device_id LIKE 'DEF-%' AND success=true"
            )
            ack_success_count = int(result.rows[0][0]) if result.rows else 0
        except Exception:
            ack_success_count = 0
        try:
            result = td.query(
                f"SELECT count(*) AS cnt FROM {db_name}.params_ack WHERE device_id LIKE 'DEF-%' AND success=false"
            )
            ack_failure_count = int(result.rows[0][0]) if result.rows else 0
        except Exception:
            ack_failure_count = 0
    print(f"- DEF devices count: {len(devices)}")
    print(f"- TDengine telemetry rows: {telemetry_rows} (PostgreSQL metrics fallback: {metric_rows})")
    print(f"- Recommendations count: {rec_rows}")
    print(f"- Ranking-used recommendations: {ranking_rows} ({', '.join(ranking_selected[:8])})")
    print(f"- Control actions count: {action_rows}")
    print(f"- Feedback samples count: {feedback_rows}")
    print(f"- ACK success count: {ack_success_count}")
    print(f"- ACK failure count: {ack_failure_count}")
    print(f"- Safety alarm count: {safety_alarm_rows}")
    print("- Active ranking artifacts:")
    for filename in (
        "recommendation_success_tree.joblib",
        "preview_gap_tree.joblib",
        "defense_ranking_models_manifest.json",
    ):
        path = ACTIVE_ARTIFACTS_DIR / filename
        print(f"  - {filename}: {'present' if path.exists() else 'missing'} bytes={path.stat().st_size if path.exists() else 0}")
    print()
    print("Recommended live demo devices:")
    for key in (
        "normal_stable",
        "steady_state_error",
        "oscillation",
        "post_apply_success",
        "preview_mismatch",
        "ack_success",
        "ack_failure_validation_error",
        "sensor_invalid",
        "over_temperature_safety",
        "saturation_limited",
    ):
        scenario = SCENARIOS[key]
        print(f"- {scenario.code} {scenario.key}: {scenario.explanation}")
    print()
    print("Backup Q&A devices:")
    for key in ("slow_response", "overshoot_high", "post_apply_partial", "insufficient_data"):
        scenario = SCENARIOS[key]
        print(f"- {scenario.code} {scenario.key}: {scenario.explanation}")
    print()
    print(f"PostgreSQL DEF devices: {len(devices)}")
    for device in devices:
        rec_count = db.scalar(select(func.count()).select_from(AIRecommendation).where(AIRecommendation.device_id == device.id)) or 0
        metric_count = db.scalar(select(func.count()).select_from(DeviceMetric).where(DeviceMetric.device_id == device.id)) or 0
        feedback_count = (
            db.scalar(select(func.count()).select_from(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id == device.id)) or 0
        )
        action_count = db.scalar(select(func.count()).select_from(ControlAction).where(ControlAction.device_id == device.id)) or 0
        alarm_count = db.scalar(select(func.count()).select_from(DeviceAlarm).where(DeviceAlarm.device_id == device.id)) or 0
        print(
            f"- {device.code}: metrics={metric_count} recommendations={rec_count} "
            f"actions={action_count} feedback={feedback_count} alarms={alarm_count}"
        )
    if td is None:
        print("TDengine: not checked")
        return
    for key in SCENARIO_ORDER:
        code = SCENARIOS[key].code
        try:
            result = td.query(f"SELECT count(*) AS cnt FROM {db_name}.telemetry WHERE device_id='{code}'")
            cnt = result.rows[0][0] if result.rows else 0
            print(f"- TDengine {code}: telemetry={cnt}")
        except Exception as exc:
            print(f"- TDengine {code}: unavailable ({exc})")
    if len(devices) >= 14 and telemetry_rows > 0 and rec_rows >= 14:
        print()
        print("Seeded defense demo is ready. Runtime WARN items do not block controlled demo.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the defense demo PostgreSQL + TDengine dataset.")
    parser.add_argument("--scenario", default="all", help="Scenario key or 'all'.")
    parser.add_argument("--reset", action="store_true", help="Delete existing DEF-%% / defense_%% demo data before seeding.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned writes/deletes without changing databases.")
    parser.add_argument("--report", action="store_true", help="Print current demo dataset report without seeding.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for deterministic curves.")
    parser.add_argument("--tdengine-database", default=settings.tdengine_database, help="TDengine database name.")
    parser.add_argument("--skip-tdengine", action="store_true", help="Seed PostgreSQL only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = scenario_keys(args.scenario)
    db_name = str(args.tdengine_database or settings.tdengine_database)
    db = SessionLocal()
    td: Optional[TdengineClient] = None
    try:
        if not args.skip_tdengine:
            td = TdengineClient()
            if not args.dry_run and not args.report:
                ensure_td_schema(td, db_name)

        if args.report:
            print_report(db, td, db_name)
            return 0

        if args.reset:
            pg_plan = reset_postgres(db, dry_run=bool(args.dry_run))
            print("[reset] PostgreSQL demo rows: " + ", ".join(f"{key}={value}" for key, value in pg_plan.items()))
            if td is not None:
                print("[reset] TDengine demo rows: device_id DEF-101..DEF-114 and run_id defense_%")
                reset_td(td, db_name, dry_run=bool(args.dry_run))

        totals = {"devices": 0, "telemetry": 0, "preview_rows": 0, "recommendations": 0, "actions": 0, "feedback": 0}
        anchor = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        root_rng = random.Random(int(args.seed))
        for offset, key in enumerate(selected):
            scenario = SCENARIOS[key]
            stats = seed_one_scenario(
                db=db,
                td=td,
                db_name=db_name,
                scenario=scenario,
                anchor=anchor - timedelta(minutes=(len(selected) - offset - 1) * 2),
                rng=random.Random(root_rng.randint(1, 10**9)),
                dry_run=bool(args.dry_run),
            )
            for total_key in totals:
                totals[total_key] += int(stats.get(total_key, 0))
            if not args.dry_run:
                db.commit()
        print_summary(selected, totals, dry_run=bool(args.dry_run))
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"[FAIL] seed_defense_demo_data failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
