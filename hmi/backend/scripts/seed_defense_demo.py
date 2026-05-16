#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path
import random
import sys
import time
from typing import Any, Optional

from paho.mqtt import client as mqtt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import (
    AIRecommendation,
    ControlAction,
    ControlActionEvalJob,
    ControlActionFeedbackSample,
    Device,
    DeviceAlarm,
    DeviceMetric,
    DeviceParameter,
    DeviceSummary,
    ModelLifecycleRun,
    User,
    UserDevice,
)
from app.services.ai.enums import ExpectedEffect, ProblemType, RiskLevel
from app.services.ai.feature_extractor import extract_features
from app.services.ai.post_effect_evaluator import ObservedTelemetryPoint, PostEffectEvaluator
from app.services.ai.preview_simulator import PreviewSimulationConfig, RecommendationPreviewSimulator
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import (
    CurrentState,
    DeviceIdentity,
    HistoryPoint,
    HistoryWindow,
    PIDParams,
    PreviewMetrics,
    RecommendationGenerateInput,
    RecommendationGenerateOutput,
)
from app.services.ai.tuning_engine import build_recommendation


DEMO_TAG = "defense_demo_v1"
DEFAULT_PREFIX = "DEF"
DEFAULT_STEP_SECONDS = 15
DEFAULT_MINUTES = 180


@dataclass(frozen=True)
class Scenario:
    code_suffix: str
    name: str
    line: str
    location: str
    target_temp: float
    start_temp: float
    base_params: PIDParams
    environment_key: str
    problem_type: ProblemType
    expected_effect: ExpectedEffect
    risk_level: RiskLevel
    confidence: float
    description: str
    before_minutes: int = 90
    after_minutes: int = 60
    applied: bool = False
    active_alarm: bool = True


@dataclass(frozen=True)
class Point:
    ts: datetime
    temp: float
    target: float
    error: float
    pwm: float
    sim_temp: float
    integral_error: float
    derivative_error: float
    saturation_state: str
    actual_dt_ms: int
    dt_error_ms: int


@dataclass(frozen=True)
class Summary:
    in_band_ratio: float
    overshoot_c: float
    settling_sec: Optional[float]
    mean_abs_error: float
    saturation_ratio: float
    temp_swing: float
    mean_error: float
    error_std: float
    pwm_mean: float
    pwm_max: float
    zero_crossings: int
    point_count: int


@dataclass(frozen=True)
class ThermalEnvironment:
    key: str
    label: str
    ambient_temp: float
    heater_gain_c_per_s: float
    heat_loss_per_s: float
    max_pwm: float
    sensor_alpha: float
    sensor_noise_std: float
    dead_time_steps: int
    feedforward_pwm: float
    controller_gain: float
    disturbance_bias_c_per_s: float = 0.0
    disturbance_std_c_per_s: float = 0.0
    periodic_disturbance_c_per_s: float = 0.0
    ambient_drift_c: float = 0.0


@dataclass
class ThermalState:
    true_temp: float
    measured_temp: float
    integral_error: float = 0.0
    last_error: float = 0.0
    delayed_pwm: Optional[list[float]] = None


@dataclass(frozen=True)
class MqttReplayConfig:
    enabled: bool
    host: str
    port: int
    username: str
    password: str
    qos: int
    topic_template: str
    speedup: float
    limit: int


ENVIRONMENTS: dict[str, ThermalEnvironment] = {
    "balanced_cell": ThermalEnvironment(
        key="balanced_cell",
        label="Balanced thermal cell",
        ambient_temp=25.0,
        heater_gain_c_per_s=0.145,
        heat_loss_per_s=0.0052,
        max_pwm=86.0,
        sensor_alpha=0.24,
        sensor_noise_std=0.025,
        dead_time_steps=1,
        feedforward_pwm=46.0,
        controller_gain=3.2,
        disturbance_std_c_per_s=0.0008,
        periodic_disturbance_c_per_s=0.0015,
        ambient_drift_c=0.4,
    ),
    "high_mass_load": ThermalEnvironment(
        key="high_mass_load",
        label="High thermal mass / slow heater",
        ambient_temp=24.0,
        heater_gain_c_per_s=0.090,
        heat_loss_per_s=0.0058,
        max_pwm=94.0,
        sensor_alpha=0.12,
        sensor_noise_std=0.035,
        dead_time_steps=4,
        feedforward_pwm=68.0,
        controller_gain=2.7,
        disturbance_bias_c_per_s=-0.001,
        disturbance_std_c_per_s=0.0012,
        periodic_disturbance_c_per_s=0.001,
        ambient_drift_c=0.6,
    ),
    "laggy_loop": ThermalEnvironment(
        key="laggy_loop",
        label="Laggy loop with delayed heat transfer",
        ambient_temp=25.0,
        heater_gain_c_per_s=0.170,
        heat_loss_per_s=0.0065,
        max_pwm=100.0,
        sensor_alpha=0.08,
        sensor_noise_std=0.045,
        dead_time_steps=7,
        feedforward_pwm=52.0,
        controller_gain=3.4,
        disturbance_std_c_per_s=0.0015,
        periodic_disturbance_c_per_s=0.002,
        ambient_drift_c=0.5,
    ),
    "fast_heater": ThermalEnvironment(
        key="fast_heater",
        label="Fast heater / low thermal capacity",
        ambient_temp=26.0,
        heater_gain_c_per_s=0.220,
        heat_loss_per_s=0.0070,
        max_pwm=100.0,
        sensor_alpha=0.30,
        sensor_noise_std=0.03,
        dead_time_steps=2,
        feedforward_pwm=42.0,
        controller_gain=3.2,
        disturbance_std_c_per_s=0.001,
        periodic_disturbance_c_per_s=0.001,
        ambient_drift_c=0.3,
    ),
    "weak_actuator": ThermalEnvironment(
        key="weak_actuator",
        label="Weak actuator / high heat loss",
        ambient_temp=22.5,
        heater_gain_c_per_s=0.075,
        heat_loss_per_s=0.0105,
        max_pwm=76.0,
        sensor_alpha=0.17,
        sensor_noise_std=0.035,
        dead_time_steps=3,
        feedforward_pwm=92.0,
        controller_gain=2.8,
        disturbance_bias_c_per_s=-0.0015,
        disturbance_std_c_per_s=0.001,
        periodic_disturbance_c_per_s=0.0015,
        ambient_drift_c=0.7,
    ),
    "loss_drift": ThermalEnvironment(
        key="loss_drift",
        label="Heat loss drift / integral needed",
        ambient_temp=23.0,
        heater_gain_c_per_s=0.120,
        heat_loss_per_s=0.0088,
        max_pwm=90.0,
        sensor_alpha=0.20,
        sensor_noise_std=0.03,
        dead_time_steps=2,
        feedforward_pwm=62.0,
        controller_gain=2.6,
        disturbance_bias_c_per_s=-0.0012,
        disturbance_std_c_per_s=0.001,
        periodic_disturbance_c_per_s=0.0012,
        ambient_drift_c=1.0,
    ),
}


SCENARIOS = [
    Scenario(
        code_suffix="STABLE-01",
        name="Defense Stable Cell",
        line="Defense Line",
        location="Normal Control",
        target_temp=37.0,
        start_temp=36.7,
        base_params=PIDParams(kp=2.5, ki=0.36, kd=0.08),
        environment_key="balanced_cell",
        problem_type=ProblemType.NORMAL,
        expected_effect=ExpectedEffect.KEEP_STABLE,
        risk_level=RiskLevel.LOW,
        confidence=0.93,
        description="Stable baseline: proves the closed-loop platform is not only showing alarms.",
        active_alarm=False,
    ),
    Scenario(
        code_suffix="SLOW-01",
        name="Defense Slow Response",
        line="Defense Line",
        location="Load Ramp",
        target_temp=38.0,
        start_temp=33.4,
        base_params=PIDParams(kp=1.7, ki=0.18, kd=0.04),
        environment_key="high_mass_load",
        problem_type=ProblemType.SLOW_RESPONSE,
        expected_effect=ExpectedEffect.SPEED_UP_RESPONSE,
        risk_level=RiskLevel.MEDIUM,
        confidence=0.84,
        description="Slow response: demonstrates feature-based diagnosis and safe gain increase.",
    ),
    Scenario(
        code_suffix="OSC-01",
        name="Defense Oscillation Cell",
        line="Defense Line",
        location="High Inertia Loop",
        target_temp=37.0,
        start_temp=37.8,
        base_params=PIDParams(kp=4.0, ki=0.72, kd=0.02),
        environment_key="laggy_loop",
        problem_type=ProblemType.OSCILLATION,
        expected_effect=ExpectedEffect.REDUCE_OSCILLATION,
        risk_level=RiskLevel.HIGH,
        confidence=0.88,
        description="Oscillation: demonstrates zero-crossing evidence, damping recommendation and preview.",
        applied=True,
    ),
    Scenario(
        code_suffix="OVS-01",
        name="Defense Overshoot Cell",
        line="Defense Line",
        location="Fast Heater",
        target_temp=36.5,
        start_temp=35.9,
        base_params=PIDParams(kp=3.8, ki=0.66, kd=0.02),
        environment_key="fast_heater",
        problem_type=ProblemType.OVERSHOOT_HIGH,
        expected_effect=ExpectedEffect.REDUCE_OVERSHOOT,
        risk_level=RiskLevel.HIGH,
        confidence=0.86,
        description="Overshoot: demonstrates conservative tuning and actuator safety boundary.",
        applied=True,
    ),
    Scenario(
        code_suffix="SAT-01",
        name="Defense Saturation Limited",
        line="Defense Line",
        location="Weak Actuator",
        target_temp=40.0,
        start_temp=34.2,
        base_params=PIDParams(kp=2.4, ki=0.34, kd=0.08),
        environment_key="weak_actuator",
        problem_type=ProblemType.SATURATION_LIMITED,
        expected_effect=ExpectedEffect.LIMITED_GAIN_EXPECTED,
        risk_level=RiskLevel.HIGH,
        confidence=0.9,
        description="Saturation limited: shows AI knows when PID alone cannot solve actuator headroom.",
    ),
    Scenario(
        code_suffix="SSE-01",
        name="Defense Steady-State Error",
        line="Defense Line",
        location="Heat Loss Drift",
        target_temp=37.5,
        start_temp=35.8,
        base_params=PIDParams(kp=2.2, ki=0.16, kd=0.07),
        environment_key="loss_drift",
        problem_type=ProblemType.STEADY_STATE_ERROR,
        expected_effect=ExpectedEffect.REDUCE_STEADY_STATE_ERROR,
        risk_level=RiskLevel.MEDIUM,
        confidence=0.82,
        description="Steady-state error: shows integral correction and evidence-driven recommendation.",
        applied=True,
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a high-signal defense demo dataset for the HMI and AI learning-loop pages."
    )
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Device code prefix scoped by the script.")
    parser.add_argument("--reset", action="store_true", help="Delete existing devices with the chosen prefix before seeding.")
    parser.add_argument("--seed", type=int, default=20260515, help="Deterministic random seed.")
    parser.add_argument("--minutes", type=int, default=DEFAULT_MINUTES, help="Total generated timeline length.")
    parser.add_argument("--step-seconds", type=int, default=DEFAULT_STEP_SECONDS, help="Metric sampling interval.")
    parser.add_argument(
        "--anchor-now",
        default=None,
        help="Optional ISO datetime used as dataset end time. Defaults to current UTC time.",
    )
    parser.add_argument(
        "--with-lifecycle",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Seed model lifecycle rows that make the Ops page look exercised.",
    )
    parser.add_argument(
        "--mqtt-replay",
        action="store_true",
        help="Publish generated telemetry to the real MQTT broker after database seeding.",
    )
    parser.add_argument("--mqtt-host", default=settings.mqtt_broker_host, help="MQTT broker host for --mqtt-replay.")
    parser.add_argument("--mqtt-port", type=int, default=settings.mqtt_broker_port, help="MQTT broker port.")
    parser.add_argument("--mqtt-username", default=settings.mqtt_username, help="MQTT username.")
    parser.add_argument("--mqtt-password", default=settings.mqtt_password, help="MQTT password.")
    parser.add_argument("--mqtt-qos", type=int, default=settings.mqtt_publish_qos, help="MQTT publish QoS.")
    parser.add_argument(
        "--mqtt-topic-template",
        default="edge/temperature/{device_id}/telemetry",
        help="Telemetry topic template used by --mqtt-replay.",
    )
    parser.add_argument(
        "--mqtt-replay-speedup",
        type=float,
        default=60.0,
        help="Replay speedup. 60 means 15 seconds of data is sent every 0.25 seconds.",
    )
    parser.add_argument(
        "--mqtt-replay-limit",
        type=int,
        default=240,
        help="Maximum telemetry points to publish during replay. 0 means all generated points.",
    )
    return parser.parse_args()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_anchor(raw: Optional[str]) -> datetime:
    if not raw:
        return datetime.utcnow().replace(microsecond=0)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None, microsecond=0)
    except ValueError as exc:
        raise SystemExit(f"Invalid --anchor-now value: {raw}") from exc


def scenario_code(prefix: str, scenario: Scenario) -> str:
    return f"{prefix}-{scenario.code_suffix}"


def delete_demo_data(db: Session, *, prefix: str) -> int:
    rows = db.scalars(select(Device).where(Device.code.like(f"{prefix}-%"))).all()
    if not rows:
        return 0
    ids = [int(row.id) for row in rows]
    db.execute(delete(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id.in_(ids)))
    db.execute(delete(ControlActionEvalJob).where(ControlActionEvalJob.device_id.in_(ids)))
    db.execute(delete(ControlAction).where(ControlAction.device_id.in_(ids)))
    db.execute(delete(AIRecommendation).where(AIRecommendation.device_id.in_(ids)))
    db.execute(delete(DeviceAlarm).where(DeviceAlarm.device_id.in_(ids)))
    db.execute(delete(DeviceSummary).where(DeviceSummary.device_id.in_(ids)))
    db.execute(delete(DeviceMetric).where(DeviceMetric.device_id.in_(ids)))
    db.execute(delete(DeviceParameter).where(DeviceParameter.device_id.in_(ids)))
    db.execute(delete(UserDevice).where(UserDevice.device_id.in_(ids)))
    db.execute(delete(Device).where(Device.id.in_(ids)))
    db.commit()
    return len(ids)


def ensure_user_access(db: Session, device: Device) -> None:
    users = db.scalars(select(User)).all()
    for user in users:
        exists = db.scalar(select(UserDevice.id).where(UserDevice.user_id == user.id, UserDevice.device_id == device.id))
        if not exists:
            db.add(UserDevice(user_id=user.id, device_id=device.id))


def upsert_device(db: Session, *, prefix: str, scenario: Scenario, latest: Point) -> tuple[Device, DeviceParameter]:
    code = scenario_code(prefix, scenario)
    device = db.scalar(select(Device).where(Device.code == code))
    if device is None:
        device = Device(code=code, name=scenario.name)
        db.add(device)
        db.flush()

    device.name = scenario.name
    device.line = scenario.line
    device.location = scenario.location
    device.status = "active"
    device.current_temp = round(latest.temp, 3)
    device.target_temp = scenario.target_temp
    device.pwm_output = round(latest.pwm, 2)
    device.is_alarm = bool(scenario.active_alarm and not scenario.applied)
    device.is_online = True
    device.updated_at = datetime.utcnow()

    param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
    if param is None:
        param = DeviceParameter(device_id=device.id)
        db.add(param)
        db.flush()
    param.kp = scenario.base_params.kp
    param.ki = scenario.base_params.ki
    param.kd = scenario.base_params.kd
    param.control_mode = "pid_control"
    param.target_band = 0.5
    param.overshoot_limit_pct = 3.0
    param.saturation_warn_ratio = 0.3
    param.saturation_high_ratio = 0.6
    env = environment_for(scenario)
    param.pwm_saturation_threshold = min(85.0, round(env.max_pwm * 0.95, 4))
    param.steady_window_samples = 12
    param.sampling_period_ms = 250
    param.upload_period_s = 10
    param.updated_at = datetime.utcnow()
    param.updated_by = DEMO_TAG
    ensure_user_access(db, device)
    return device, param


def environment_for(scenario: Scenario) -> ThermalEnvironment:
    try:
        return ENVIRONMENTS[scenario.environment_key]
    except KeyError as exc:
        raise RuntimeError(f"Unknown thermal environment: {scenario.environment_key}") from exc


def new_thermal_state(*, scenario: Scenario, env: ThermalEnvironment) -> ThermalState:
    return ThermalState(
        true_temp=float(scenario.start_temp),
        measured_temp=float(scenario.start_temp),
        integral_error=0.0,
        last_error=float(scenario.target_temp - scenario.start_temp),
        delayed_pwm=[env.feedforward_pwm] * max(1, int(env.dead_time_steps)),
    )


def simulate_points(
    *,
    scenario: Scenario,
    env: ThermalEnvironment,
    params: PIDParams,
    state: ThermalState,
    start_ts: datetime,
    minutes: int,
    step_seconds: int,
    rng: random.Random,
    phase: str,
) -> tuple[list[Point], ThermalState]:
    count = max(12, int(minutes * 60 / max(1, step_seconds)))
    out: list[Point] = []
    for idx in range(count):
        progress = idx / max(1, count - 1)
        ts = start_ts + timedelta(seconds=idx * step_seconds)
        point = thermal_step(
            scenario=scenario,
            env=env,
            params=params,
            state=state,
            ts=ts,
            dt=float(step_seconds),
            progress=progress,
            phase=phase,
            rng=rng,
        )
        out.append(point)
    return out, state


def thermal_step(
    *,
    scenario: Scenario,
    env: ThermalEnvironment,
    params: PIDParams,
    state: ThermalState,
    ts: datetime,
    dt: float,
    progress: float,
    phase: str,
    rng: random.Random,
) -> Point:
    target = float(scenario.target_temp)
    error_for_control = target - state.measured_temp
    dt_minutes = max(1e-6, dt / 60.0)
    proposed_integral = clamp(state.integral_error + error_for_control * dt_minutes, -80.0, 80.0)
    derivative = (error_for_control - state.last_error) / dt_minutes
    state.last_error = error_for_control

    p_term = params.kp * error_for_control
    i_term = params.ki * proposed_integral
    d_term = params.kd * derivative
    raw_pwm = env.feedforward_pwm + env.controller_gain * (p_term + i_term + d_term)

    if phase == "after" and scenario.problem_type == ProblemType.OVERSHOOT_HIGH:
        raw_pwm *= 0.88
    elif phase == "after" and scenario.problem_type == ProblemType.OSCILLATION:
        raw_pwm = 0.65 * raw_pwm + 0.35 * env.feedforward_pwm

    pwm = clamp(raw_pwm, 0.0, env.max_pwm)
    pushing_high = pwm >= env.max_pwm and error_for_control > 0
    pushing_low = pwm <= 0.0 and error_for_control < 0
    if not (pushing_high or pushing_low):
        state.integral_error = proposed_integral
    if state.delayed_pwm is None:
        state.delayed_pwm = [pwm] * max(1, int(env.dead_time_steps))
    state.delayed_pwm.append(pwm)
    applied_pwm = state.delayed_pwm.pop(0)

    ambient = env.ambient_temp + env.ambient_drift_c * math.sin(progress * math.tau)
    disturbance = (
        env.disturbance_bias_c_per_s
        + env.periodic_disturbance_c_per_s * math.sin(progress * math.tau * 2.0 + 0.4)
        + rng.gauss(0.0, env.disturbance_std_c_per_s)
    )
    if phase == "before" and scenario.problem_type == ProblemType.SLOW_RESPONSE:
        disturbance -= 0.0015
    if phase == "before" and scenario.problem_type == ProblemType.STEADY_STATE_ERROR:
        disturbance -= 0.0012

    heating = env.heater_gain_c_per_s * (applied_pwm / 100.0)
    cooling = env.heat_loss_per_s * (state.true_temp - ambient)
    state.true_temp += (heating - cooling + disturbance) * dt
    sensor_noise = rng.gauss(0.0, env.sensor_noise_std)
    state.measured_temp += env.sensor_alpha * (state.true_temp - state.measured_temp) + sensor_noise

    observed_error = state.measured_temp - target
    saturation_state = "high" if pwm >= 85.0 or pwm >= env.max_pwm * 0.96 else ("medium" if pwm >= 70.0 else "normal")
    actual_dt_ms = int(dt * 1000 + rng.gauss(0.0, 45.0))
    dt_error_ms = int(actual_dt_ms - dt * 1000)
    return Point(
        ts=ts,
        temp=round(state.measured_temp, 4),
        target=target,
        error=round(observed_error, 4),
        pwm=round(pwm, 4),
        sim_temp=round(state.true_temp, 4),
        integral_error=round(state.integral_error, 4),
        derivative_error=round(derivative, 6),
        saturation_state=saturation_state,
        actual_dt_ms=actual_dt_ms,
        dt_error_ms=dt_error_ms,
    )


def summarize(points: list[Point], *, target_band: float, pwm_threshold: float) -> Summary:
    errors = [p.error for p in points]
    abs_errors = [abs(v) for v in errors]
    temps = [p.temp for p in points]
    pwms = [p.pwm for p in points]
    mean_error = sum(errors) / max(1, len(errors))
    variance = sum((v - mean_error) ** 2 for v in errors) / max(1, len(errors))
    zero_crossings = 0
    for left, right in zip(errors, errors[1:]):
        if (left < 0 < right) or (left > 0 > right):
            zero_crossings += 1
    settling_sec: Optional[float] = None
    hold = min(12, max(4, len(points) // 8))
    for idx in range(0, max(0, len(points) - hold + 1)):
        if all(abs(p.error) <= target_band for p in points[idx : idx + hold]):
            settling_sec = (points[idx].ts - points[0].ts).total_seconds()
            break
    return Summary(
        in_band_ratio=sum(1 for v in abs_errors if v <= target_band) / max(1, len(abs_errors)),
        overshoot_c=max(0.0, max((p.temp - p.target) for p in points)),
        settling_sec=settling_sec,
        mean_abs_error=sum(abs_errors) / max(1, len(abs_errors)),
        saturation_ratio=sum(1 for p in points if p.pwm >= pwm_threshold) / max(1, len(points)),
        temp_swing=max(temps) - min(temps),
        mean_error=mean_error,
        error_std=math.sqrt(max(0.0, variance)),
        pwm_mean=sum(pwms) / max(1, len(pwms)),
        pwm_max=max(pwms),
        zero_crossings=zero_crossings,
        point_count=len(points),
    )


def comparison(*, actual: Summary, reference: Summary) -> dict[str, float]:
    return {
        "in_band_ratio_delta": round(actual.in_band_ratio - reference.in_band_ratio, 6),
        "overshoot_c_delta": round(reference.overshoot_c - actual.overshoot_c, 6),
        "settling_sec_delta": round(float(reference.settling_sec or 0.0) - float(actual.settling_sec or 0.0), 6),
        "mean_abs_error_delta": round(reference.mean_abs_error - actual.mean_abs_error, 6),
        "saturation_ratio_delta": round(reference.saturation_ratio - actual.saturation_ratio, 6),
        "temp_swing_delta": round(reference.temp_swing - actual.temp_swing, 6),
    }


def effect_label(comp: dict[str, float]) -> str:
    score = 0
    for key, threshold in {
        "in_band_ratio_delta": 0.04,
        "overshoot_c_delta": 0.2,
        "settling_sec_delta": 30.0,
        "mean_abs_error_delta": 0.08,
        "saturation_ratio_delta": 0.05,
        "temp_swing_delta": 0.15,
    }.items():
        value = float(comp.get(key, 0.0))
        if value > threshold:
            score += 1
        elif value < -threshold:
            score -= 1
    if score >= 2:
        return "improved"
    if score <= -2:
        return "worse"
    return "unchanged"


def preview_gap_label(comp: dict[str, float]) -> str:
    normalized = [
        min(1.0, abs(float(comp.get("in_band_ratio_delta", 0.0))) / 0.25),
        min(1.0, abs(float(comp.get("overshoot_c_delta", 0.0))) / 1.0),
        min(1.0, abs(float(comp.get("settling_sec_delta", 0.0))) / 240.0),
        min(1.0, abs(float(comp.get("mean_abs_error_delta", 0.0))) / 0.8),
        min(1.0, abs(float(comp.get("saturation_ratio_delta", 0.0))) / 0.35),
        min(1.0, abs(float(comp.get("temp_swing_delta", 0.0))) / 1.8),
    ]
    score = sum(normalized) / len(normalized)
    if score < 0.33:
        return "low"
    if score < 0.66:
        return "medium"
    return "high"


def as_feature_input(device: Device, param: DeviceParameter, points: list[Point]) -> RecommendationGenerateInput:
    return RecommendationGenerateInput(
        device=DeviceIdentity(id=int(device.id), code=device.code, name=device.name),
        current_state=CurrentState(
            current_temp=float(points[-1].temp),
            target_temp=float(device.target_temp),
            pwm_output=float(points[-1].pwm),
        ),
        current_params=PIDParams(kp=float(param.kp), ki=float(param.ki), kd=float(param.kd)),
        history_window=HistoryWindow(
            start_ms=int(points[0].ts.timestamp() * 1000),
            end_ms=int(points[-1].ts.timestamp() * 1000),
            points=[
                HistoryPoint(
                    ts_ms=int(p.ts.timestamp() * 1000),
                    current_temp=p.temp,
                    target_temp=p.target,
                    error=p.error,
                    pwm_output=p.pwm,
                )
                for p in points
            ],
        ),
        target_band=float(param.target_band),
        steady_window_samples=int(param.steady_window_samples),
        overshoot_limit_pct=float(param.overshoot_limit_pct),
        pwm_saturation_threshold=float(param.pwm_saturation_threshold),
        saturation_warn_ratio=float(param.saturation_warn_ratio),
        saturation_high_ratio=float(param.saturation_high_ratio),
    )


def build_recommendation_output(
    *,
    device: Device,
    param: DeviceParameter,
    scenario: Scenario,
    before_points: list[Point],
    generated_at: datetime,
) -> RecommendationGenerateOutput:
    payload = as_feature_input(device, param, before_points)
    features = extract_features(payload)
    current_params, recommended_params, delta, risk_level, requires_confirmation, expected_effect = build_recommendation(
        scenario.problem_type,
        payload.current_params,
    )
    evidence: dict[str, Any] = {
        "rule_saturation_limited": scenario.problem_type == ProblemType.SATURATION_LIMITED,
        "rule_severe_saturation": scenario.problem_type == ProblemType.SATURATION_LIMITED,
        "rule_oscillation": scenario.problem_type == ProblemType.OSCILLATION,
        "rule_overshoot_high": scenario.problem_type == ProblemType.OVERSHOOT_HIGH,
        "rule_steady_state_error": scenario.problem_type == ProblemType.STEADY_STATE_ERROR,
        "rule_slow_response": scenario.problem_type == ProblemType.SLOW_RESPONSE,
        "mean_error": round(features.mean_error, 4),
        "mean_abs_error": round(features.mean_abs_error, 4),
        "error_std": round(features.error_std, 4),
        "temp_swing": round(features.temp_swing, 4),
        "pwm_mean": round(features.pwm_mean, 4),
        "pwm_max": round(features.pwm_max, 4),
        "zero_crossings": features.zero_crossings,
        "in_band_ratio": round(features.in_band_ratio, 4),
        "overshoot_pct": round(features.overshoot_pct, 4),
        "settling_sec": None if features.settling_sec is None else round(features.settling_sec, 4),
        "saturation_ratio": round(features.saturation_ratio, 4),
        "demo_description": scenario.description,
        "thermal_environment": scenario.environment_key,
        "thermal_environment_label": environment_for(scenario).label,
    }
    return RecommendationGenerateOutput(
        problem_type=scenario.problem_type,
        primary_problem_type=scenario.problem_type,
        secondary_problem_types=[] if scenario.problem_type == ProblemType.NORMAL else secondary_problem_types_for(scenario.problem_type),
        problem_flags={k.replace("rule_", ""): bool(v) for k, v in evidence.items() if k.startswith("rule_")},
        confidence=scenario.confidence,
        risk_level=risk_level if scenario.problem_type == ProblemType.NORMAL else scenario.risk_level,
        requires_confirmation=requires_confirmation,
        current_params=current_params,
        recommended_params=recommended_params,
        delta=delta,
        expected_effect=expected_effect if scenario.problem_type == ProblemType.NORMAL else scenario.expected_effect,
        evidence=evidence,
        generated_at=generated_at,
    )


def secondary_problem_types_for(problem: ProblemType) -> list[ProblemType]:
    if problem == ProblemType.SATURATION_LIMITED:
        return [ProblemType.SLOW_RESPONSE]
    if problem == ProblemType.OSCILLATION:
        return [ProblemType.OVERSHOOT_HIGH]
    if problem == ProblemType.OVERSHOOT_HIGH:
        return [ProblemType.OSCILLATION]
    return []


def runtime_decision_summary(scenario: Scenario, *, selected_candidate_id: str = "rule_center") -> dict[str, Any]:
    ranking_used = scenario.problem_type in {ProblemType.OSCILLATION, ProblemType.OVERSHOOT_HIGH, ProblemType.STEADY_STATE_ERROR}
    return {
        "runtime_source": "defense_demo",
        "fallback_used": False,
        "diagnosis_source": "rule_classifier",
        "base_recommendation_source": "rule_tuning_engine",
        "ranking_used": ranking_used,
        "ranking_fallback_used": False,
        "primary_problem_type": scenario.problem_type.value,
        "selected_candidate_id": selected_candidate_id if ranking_used else "rule_center",
        "base_candidate_id": "rule_center",
        "candidate_count": 5 if ranking_used else 1,
        "evaluated_candidate_count": 5 if ranking_used else 1,
        "configured_candidate_limit": 6,
        "top_score": 0.78 if ranking_used else 0.64,
        "top_success_score": 0.82 if ranking_used else 0.68,
        "top_gap_score": 0.7 if ranking_used else 0.56,
    }


def preview_summary_payload(
    *,
    baseline: PreviewMetrics,
    recommended: PreviewMetrics,
    recommended_curve: list[dict[str, float]],
) -> dict[str, Any]:
    return {
        "baseline_metrics": baseline.model_dump(mode="json"),
        "recommended_metrics": recommended.model_dump(mode="json"),
        "recommended_curve": recommended_curve,
    }


def run_preview(
    *,
    scenario: Scenario,
    current_temp: float,
    baseline_params: PIDParams,
    recommended_params: PIDParams,
    observation_minutes: int,
) -> tuple[PreviewMetrics, PreviewMetrics, list[dict[str, float]]]:
    simulator = RecommendationPreviewSimulator()
    output = simulator.run(
        current_temp=current_temp,
        target_temp=scenario.target_temp,
        baseline_params=baseline_params,
        recommended_params=recommended_params,
        config=PreviewSimulationConfig(
            horizon_sec=max(120, observation_minutes * 60),
            step_sec=10,
            ambient_temp=max(20.0, scenario.target_temp - 10.0),
            heating_gain=0.08,
            cooling_coeff=0.015,
            target_band=0.5,
            pwm_saturation_threshold=85.0,
            control_mode="pid_control",
        ),
    )
    raw_curve = [
        {
            "time_s": round(float(p.time_s), 3),
            "temp": round(float(p.temp), 4),
            "target_temp": round(float(p.target_temp), 4),
            "pwm_output": round(float(p.pwm_output), 4),
            "error": round(float(p.error), 4),
        }
        for p in output.recommended_curve
    ]
    curve = sample_curve(raw_curve, max_points=48)
    return output.baseline_metrics, output.recommended_metrics, curve


def sample_curve(points: list[dict[str, float]], *, max_points: int) -> list[dict[str, float]]:
    if len(points) <= max_points:
        return points
    if max_points <= 2:
        return points[:max_points]
    last = len(points) - 1
    indexes = sorted({round(i * last / (max_points - 1)) for i in range(max_points)})
    return [points[i] for i in indexes]


def insert_metrics(db: Session, *, device: Device, points: list[Point], target_band: float, pwm_threshold: float) -> None:
    for p in points:
        db.add(
            DeviceMetric(
                device_id=device.id,
                timestamp=p.ts,
                current_temp=p.temp,
                target_temp=p.target,
                error=p.error,
                pwm_output=p.pwm,
                status="active",
                in_spec=abs(p.error) <= target_band,
                is_alarm=abs(p.error) > target_band * 3.0 or p.pwm >= pwm_threshold,
            )
        )


def insert_summaries(db: Session, *, device: Device, points: list[Point], target_band: float, pwm_threshold: float) -> None:
    chunk_size = max(4, len(points) // 6)
    for idx in range(0, len(points), chunk_size):
        chunk = points[idx : idx + chunk_size]
        if len(chunk) < 2:
            continue
        s = summarize(chunk, target_band=target_band, pwm_threshold=pwm_threshold)
        if s.saturation_ratio >= 0.5:
            trigger = "saturation_window"
        elif s.mean_abs_error > target_band:
            trigger = "error_window"
        elif s.zero_crossings >= 4:
            trigger = "oscillation_window"
        else:
            trigger = "steady_state_window"
        db.add(
            DeviceSummary(
                device_id=device.id,
                window_start=chunk[0].ts,
                window_end=chunk[-1].ts,
                sample_count=len(chunk),
                avg_temp=round(sum(p.temp for p in chunk) / len(chunk), 4),
                avg_error=round(s.mean_abs_error, 4),
                max_overshoot_pct=round((s.overshoot_c / max(0.001, chunk[-1].target)) * 100.0, 4),
                saturation_ratio=round(s.saturation_ratio, 4),
                trigger_event=trigger,
            )
        )


def insert_alarm(
    db: Session,
    *,
    device: Device,
    scenario: Scenario,
    created_at: datetime,
    cleared_at: Optional[datetime],
) -> None:
    if not scenario.active_alarm:
        return
    if scenario.problem_type == ProblemType.SATURATION_LIMITED:
        title = "PWM Saturation Risk"
        rule_code = "high_saturation"
        message = f"{device.code} is near actuator saturation; PID changes alone have limited effect."
    elif scenario.problem_type == ProblemType.OSCILLATION:
        title = "Oscillation Detected"
        rule_code = "out_of_band"
        message = f"{device.code} repeatedly crosses the target band; damping-oriented tuning is recommended."
    elif scenario.problem_type == ProblemType.OVERSHOOT_HIGH:
        title = "Overshoot Above Limit"
        rule_code = "out_of_band"
        message = f"{device.code} exceeds the overshoot threshold; conservative gains should be reviewed."
    else:
        title = "Temperature Control Deviation"
        rule_code = "out_of_band"
        message = f"{device.code} stays outside the target band; review PID recommendation and load condition."
    db.add(
        DeviceAlarm(
            device_id=device.id,
            level="critical" if scenario.risk_level == RiskLevel.HIGH else "warning",
            rule_code=rule_code,
            source="defense_demo_rule_engine",
            title=title,
            message=message,
            is_active=cleared_at is None,
            acknowledged=cleared_at is not None,
            created_at=created_at,
            cleared_at=cleared_at,
        )
    )


def observed(points: list[Point]) -> list[ObservedTelemetryPoint]:
    return [
        ObservedTelemetryPoint(
            ts_ms=int(p.ts.timestamp() * 1000),
            temp=p.temp,
            target_temp=p.target,
            error=p.error,
            pwm_output=p.pwm,
            saturation_state=p.saturation_state,
        )
        for p in points
    ]


def seed_one_scenario(
    db: Session,
    *,
    prefix: str,
    scenario: Scenario,
    dataset_end: datetime,
    minutes: int,
    step_seconds: int,
    rng: random.Random,
) -> dict[str, Any]:
    env = environment_for(scenario)
    reserved_after = scenario.after_minutes + 10 if scenario.applied else 0
    before_minutes = min(scenario.before_minutes if scenario.applied else minutes, max(45, minutes - reserved_after))
    after_minutes = scenario.after_minutes if scenario.applied else 0
    apply_gap_minutes = 4 if scenario.applied else 0
    total_minutes = before_minutes + apply_gap_minutes + after_minutes
    start_ts = dataset_end - timedelta(minutes=total_minutes)

    before_state = new_thermal_state(scenario=scenario, env=env)
    before_points, state = simulate_points(
        scenario=scenario,
        env=env,
        params=scenario.base_params,
        state=before_state,
        start_ts=start_ts,
        minutes=before_minutes,
        step_seconds=step_seconds,
        rng=rng,
        phase="before",
    )
    after_points: list[Point] = []
    if scenario.applied:
        after_start = before_points[-1].ts + timedelta(minutes=apply_gap_minutes)
        _, recommended_params_for_after, _, _, _, _ = build_recommendation(scenario.problem_type, scenario.base_params)
        after_points, state = simulate_points(
            scenario=scenario,
            env=env,
            params=recommended_params_for_after,
            state=state,
            start_ts=after_start,
            minutes=after_minutes,
            step_seconds=step_seconds,
            rng=rng,
            phase="after",
        )

    latest = (after_points or before_points)[-1]
    device, param = upsert_device(db, prefix=prefix, scenario=scenario, latest=latest)

    for model in (
        ControlActionFeedbackSample,
        ControlActionEvalJob,
        ControlAction,
        AIRecommendation,
        DeviceAlarm,
        DeviceSummary,
        DeviceMetric,
    ):
        db.execute(delete(model).where(model.device_id == device.id))
    db.flush()

    all_points = before_points + after_points
    insert_metrics(
        db,
        device=device,
        points=all_points,
        target_band=float(param.target_band),
        pwm_threshold=float(param.pwm_saturation_threshold),
    )
    insert_summaries(
        db,
        device=device,
        points=all_points,
        target_band=float(param.target_band),
        pwm_threshold=float(param.pwm_saturation_threshold),
    )
    insert_alarm(
        db,
        device=device,
        scenario=scenario,
        created_at=before_points[-1].ts - timedelta(minutes=10),
        cleared_at=(after_points[-1].ts if scenario.applied and after_points else None),
    )

    generated_at = before_points[-1].ts - timedelta(minutes=3)
    recommendation_output = build_recommendation_output(
        device=device,
        param=param,
        scenario=scenario,
        before_points=before_points,
        generated_at=generated_at,
    )
    rec_service = RecommendationService()
    fingerprint = rec_service.build_recommendation_fingerprint(recommendation_output)
    obs_minutes = max(10, scenario.after_minutes)
    baseline_preview, recommended_preview, preview_curve = run_preview(
        scenario=scenario,
        current_temp=before_points[-1].temp,
        baseline_params=recommendation_output.current_params,
        recommended_params=recommendation_output.recommended_params,
        observation_minutes=obs_minutes,
    )
    runtime_decision = runtime_decision_summary(
        scenario,
        selected_candidate_id={
            ProblemType.OSCILLATION: "oscillation_damp",
            ProblemType.OVERSHOOT_HIGH: "overshoot_guard",
            ProblemType.STEADY_STATE_ERROR: "sse_speed_balance",
        }.get(scenario.problem_type, "rule_center"),
    )
    reason, suggestion, risk = rec_service.to_storage_fields(
        recommendation_output,
        fingerprint=fingerprint,
        history_state="applied" if scenario.applied else ("generated" if scenario.problem_type != ProblemType.NORMAL else "previewed"),
        last_accessed_at=generated_at,
        runtime_decision=runtime_decision,
    )

    before_summary = summarize(before_points, target_band=float(param.target_band), pwm_threshold=float(param.pwm_saturation_threshold))
    actual_summary = None
    comp_before = None
    comp_preview = None
    if scenario.applied and after_points:
        applied_at = after_points[0].ts
        evaluator = PostEffectEvaluator()
        actual_metrics = evaluator.calc_metrics(
            points=observed(after_points),
            target_band=float(param.target_band),
            pwm_saturation_threshold=float(param.pwm_saturation_threshold),
        )
        if actual_metrics is not None:
            actual_summary = evaluator.build_actual_summary(points=observed(after_points), metrics=actual_metrics).model_dump(mode="json")
            actual_points_summary = summarize(
                after_points,
                target_band=float(param.target_band),
                pwm_threshold=float(param.pwm_saturation_threshold),
            )
            comp_before = comparison(actual=actual_points_summary, reference=before_summary)
            preview_ref = Summary(
                in_band_ratio=recommended_preview.in_band_ratio,
                overshoot_c=recommended_preview.overshoot_c,
                settling_sec=recommended_preview.settling_sec,
                mean_abs_error=recommended_preview.mean_abs_error,
                saturation_ratio=recommended_preview.saturation_ratio,
                temp_swing=recommended_preview.temp_swing,
                mean_error=0.0,
                error_std=0.0,
                pwm_mean=0.0,
                pwm_max=0.0,
                zero_crossings=0,
                point_count=len(preview_curve),
            )
            comp_preview = comparison(actual=actual_points_summary, reference=preview_ref)
        suggestion = rec_service.update_storage_metadata(
            suggestion,
            history_state="applied",
            last_accessed_at=applied_at,
            applied_at=applied_at,
            preview_summary=preview_summary_payload(
                baseline=baseline_preview,
                recommended=recommended_preview,
                recommended_curve=preview_curve,
            ),
            post_effect_summary=actual_summary,
            post_effect_comparison_before=comp_before,
            post_effect_comparison_preview=comp_preview,
            actual_effect_evaluated=actual_summary is not None,
            insufficient_data=False,
            observation_window_minutes=obs_minutes,
            evaluated_at=(after_points[-1].ts if after_points else None),
            runtime_decision=runtime_decision,
        )
    else:
        suggestion = rec_service.update_storage_metadata(
            suggestion,
            history_state="previewed" if scenario.problem_type == ProblemType.NORMAL else "generated",
            preview_summary=preview_summary_payload(
                baseline=baseline_preview,
                recommended=recommended_preview,
                recommended_curve=preview_curve,
            ),
            runtime_decision=runtime_decision,
        )

    rec = AIRecommendation(
        device_id=device.id,
        reason=reason,
        suggestion=suggestion,
        confidence=scenario.confidence,
        risk=risk,
        last_run_at=generated_at,
    )
    db.add(rec)
    db.flush()

    actions = 0
    feedback = 0
    if scenario.applied and after_points:
        applied_at = after_points[0].ts
        after_params = recommendation_output.recommended_params
        action = ControlAction(
            device_id=device.id,
            source="ai_runtime",
            source_ref_id=rec.id,
            action_type="pid_apply",
            initiated_by="operator_defense_demo",
            applied_at=applied_at,
            status="applied",
            control_mode_before="pid_control",
            control_mode_after="pid_control",
            target_temp_before=scenario.target_temp,
            target_temp_after=scenario.target_temp,
            kp_before=recommendation_output.current_params.kp,
            ki_before=recommendation_output.current_params.ki,
            kd_before=recommendation_output.current_params.kd,
            kp_after=after_params.kp,
            ki_after=after_params.ki,
            kd_after=after_params.kd,
            delta_kp=recommendation_output.delta.kp,
            delta_ki=recommendation_output.delta.ki,
            delta_kd=recommendation_output.delta.kd,
            context_snapshot={
                "demo_tag": DEMO_TAG,
                "problem_type": scenario.problem_type.value,
                "recommendation_id": rec.id,
                "ack_status": "acknowledged",
            },
            created_at=applied_at,
            updated_at=applied_at,
        )
        db.add(action)
        db.flush()
        actions += 1

        db.add(
            ControlActionEvalJob(
                control_action_id=action.id,
                device_id=device.id,
                status="done",
                scheduled_at=after_points[-1].ts,
                observation_window_minutes=obs_minutes,
                attempt_count=1,
                created_at=applied_at,
                updated_at=after_points[-1].ts,
            )
        )

        after_summary = summarize(after_points, target_band=float(param.target_band), pwm_threshold=float(param.pwm_saturation_threshold))
        comp_before_final = comparison(actual=after_summary, reference=before_summary)
        comp_preview_final = comp_preview or comparison(
            actual=after_summary,
            reference=Summary(
                in_band_ratio=recommended_preview.in_band_ratio,
                overshoot_c=recommended_preview.overshoot_c,
                settling_sec=recommended_preview.settling_sec,
                mean_abs_error=recommended_preview.mean_abs_error,
                saturation_ratio=recommended_preview.saturation_ratio,
                temp_swing=recommended_preview.temp_swing,
                mean_error=0.0,
                error_std=0.0,
                pwm_mean=0.0,
                pwm_max=0.0,
                zero_crossings=0,
                point_count=len(preview_curve),
            ),
        )
        trainable = scenario.problem_type != ProblemType.NORMAL
        db.add(
            ControlActionFeedbackSample(
                control_action_id=action.id,
                device_id=device.id,
                source="ai_runtime",
                source_ref_id=rec.id,
                action_type="pid_apply",
                initiated_by="operator_defense_demo",
                generated_at=generated_at,
                applied_at=applied_at,
                evaluated_at=after_points[-1].ts,
                primary_problem_type=scenario.problem_type.value,
                secondary_problem_types=[p.value for p in secondary_problem_types_for(scenario.problem_type)],
                problem_flags=recommendation_output.problem_flags,
                expected_effect=scenario.expected_effect.value,
                risk_level=scenario.risk_level.value,
                confidence=scenario.confidence,
                control_mode_before=action.control_mode_before,
                control_mode_after=action.control_mode_after,
                target_temp_before=action.target_temp_before,
                target_temp_after=action.target_temp_after,
                kp_before=action.kp_before,
                ki_before=action.ki_before,
                kd_before=action.kd_before,
                kp_after=action.kp_after,
                ki_after=action.ki_after,
                kd_after=action.kd_after,
                delta_kp=action.delta_kp,
                delta_ki=action.delta_ki,
                delta_kd=action.delta_kd,
                mean_error=before_summary.mean_error,
                mean_abs_error=before_summary.mean_abs_error,
                error_std=before_summary.error_std,
                temp_swing=before_summary.temp_swing,
                pwm_mean=before_summary.pwm_mean,
                pwm_max=before_summary.pwm_max,
                zero_crossings=before_summary.zero_crossings,
                in_band_ratio=before_summary.in_band_ratio,
                overshoot_pct=(before_summary.overshoot_c / max(0.001, scenario.target_temp)) * 100.0,
                settling_sec=before_summary.settling_sec,
                saturation_ratio=before_summary.saturation_ratio,
                runtime_decision_summary=runtime_decision,
                preview_metrics_summary=recommended_preview.model_dump(mode="json"),
                actual_metrics_summary={
                    "point_count": after_summary.point_count,
                    "in_band_ratio_after": after_summary.in_band_ratio,
                    "overshoot_c_after": after_summary.overshoot_c,
                    "settling_sec_after": after_summary.settling_sec,
                    "mean_abs_error_after": after_summary.mean_abs_error,
                    "saturation_ratio_after": after_summary.saturation_ratio,
                    "temp_swing_after": after_summary.temp_swing,
                },
                comparison_to_before=comp_before_final,
                comparison_to_preview=comp_preview_final,
                actual_effect_label=effect_label(comp_before_final),
                preview_gap_label=preview_gap_label(comp_preview_final),
                insufficient_data=False,
                sample_quality="high",
                is_training_eligible=trainable,
                training_exclusion_reason=None if trainable else "normal_no_change_reference",
                label_source=DEMO_TAG,
                created_at=after_points[-1].ts,
                updated_at=after_points[-1].ts,
            )
        )
        feedback += 1

        param.kp = after_params.kp
        param.ki = after_params.ki
        param.kd = after_params.kd
        param.updated_at = applied_at
        param.updated_by = "ai_runtime_defense_demo"

    return {
        "metrics": len(all_points),
        "summaries": max(1, len(all_points) // max(1, len(all_points) // 6)),
        "recommendations": 1,
        "actions": actions,
        "feedback": feedback,
        "points": all_points,
    }


def seed_lifecycle_rows(db: Session, *, anchor: datetime) -> None:
    db.execute(delete(ModelLifecycleRun).where(ModelLifecycleRun.trigger_source == DEMO_TAG))
    families = [
        ("recommendation_success", "promoted", True, "candidate improved danger recall and macro_f1"),
        ("preview_gap", "rejected", False, "danger_recall_regression_guard"),
        ("recommendation_success", "skipped", False, "not enough new eligible samples"),
    ]
    for idx, (family, status, promoted, reason) in enumerate(families):
        started = anchor - timedelta(hours=idx * 7 + 1)
        db.add(
            ModelLifecycleRun(
                lifecycle_run_id=f"defense-demo-{family}-{idx + 1}",
                model_family=family,
                trigger_source=DEMO_TAG,
                status=status,
                promoted=promoted,
                dry_run=False,
                reason=reason,
                gate_reasons=[] if promoted else [reason],
                training_sample_count=96 - idx * 18,
                new_eligible_samples_since_last=36 - idx * 8,
                recent_eligible_samples_7d=72 - idx * 10,
                validation_size=28 - idx * 4,
                candidate_artifact_dir=f"artifacts/candidates/{family}/defense-demo",
                active_artifact_dir_before=f"artifacts/active/{family}",
                archive_artifact_dir=f"artifacts/archive/{family}/defense-demo",
                candidate_metrics={
                    "macro_f1": 0.78 - idx * 0.06,
                    "danger_recall": 0.72 - idx * 0.08,
                    "danger_misclass_rate": 0.05 + idx * 0.03,
                },
                active_metrics={
                    "macro_f1": 0.73,
                    "danger_recall": 0.66,
                    "danger_misclass_rate": 0.07,
                },
                comparison_summary={
                    "macro_f1_delta": 0.05 - idx * 0.04,
                    "danger_recall_delta": 0.06 - idx * 0.07,
                },
                started_at=started,
                completed_at=started + timedelta(minutes=4),
                created_at=started,
                updated_at=started + timedelta(minutes=4),
            )
        )


def telemetry_payload(
    *,
    device_code: str,
    scenario: Scenario,
    point: Point,
    index: int,
    step_seconds: int,
) -> dict[str, Any]:
    pwm_duty = int(round(clamp(point.pwm, 0.0, 100.0) * 255.0 / 100.0))
    return {
        "device_id": device_code,
        "uptime_ms": int((index + 1) * step_seconds * 1000),
        "target_temp_c": round(point.target, 4),
        "sim_temp_c": round(point.sim_temp, 4),
        "sensor_temp_c": round(point.temp, 4),
        "sensor_status": "ok",
        "error_c": round(point.error, 4),
        "integral_error": round(point.integral_error, 4),
        "derivative_error": round(point.derivative_error, 6),
        "d_term": 0.0,
        "control_output": round(pwm_duty, 4),
        "pwm_duty": pwm_duty,
        "pwm_norm": round(pwm_duty / 255.0, 6),
        "control_period_ms": int(step_seconds * 1000),
        "actual_dt_ms": int(point.actual_dt_ms),
        "dt_error_ms": int(point.dt_error_ms),
        "saturation_state": point.saturation_state,
        "sensor_valid": True,
        "run_id": f"{device_code}-defense-demo",
        "control_mode": "pid_control",
        "controller_version": "defense_thermal_env_v2",
        "kp": float(scenario.base_params.kp),
        "ki": float(scenario.base_params.ki),
        "kd": float(scenario.base_params.kd),
        "system_state": "running",
        "wifi_connected": True,
        "mqtt_connected": True,
        "mqtt_reconnect_count": 0,
        "mqtt_publish_fail_count": 0,
        "safety_output_forced_off": False,
        "fault_latched": False,
        "fault_reason": "none",
        "software_max_safe_temp_c": 65.0,
        "has_pending_params": False,
        "pending_params_age_ms": 0,
        "thermal_environment": scenario.environment_key,
    }


def sample_replay_rows(
    rows: list[tuple[str, Scenario, int, Point]],
    *,
    limit: int,
) -> list[tuple[str, Scenario, int, Point]]:
    ordered = sorted(rows, key=lambda item: item[3].ts)
    if limit <= 0 or len(ordered) <= limit:
        return ordered
    last = len(ordered) - 1
    indexes = sorted({round(i * last / (limit - 1)) for i in range(limit)})
    return [ordered[i] for i in indexes]


def replay_to_mqtt(
    rows: list[tuple[str, Scenario, int, Point]],
    *,
    config: MqttReplayConfig,
    step_seconds: int,
) -> int:
    if not config.enabled or not rows:
        return 0

    selected = sample_replay_rows(rows, limit=max(0, int(config.limit)))
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{settings.mqtt_client_id_prefix}-defense-replay-{int(time.time())}",
        protocol=mqtt.MQTTv311,
    )
    if config.username:
        client.username_pw_set(config.username, config.password or None)

    client.connect(config.host, int(config.port), keepalive=30)
    client.loop_start()
    published = 0
    previous_ts: Optional[datetime] = None
    try:
        for device_code, scenario, idx, point in selected:
            if previous_ts is not None:
                delta = max(0.0, (point.ts - previous_ts).total_seconds())
                sleep_s = min(1.0, delta / max(1.0, float(config.speedup)))
                if sleep_s > 0:
                    time.sleep(sleep_s)
            topic = config.topic_template.format(device_id=device_code)
            payload = telemetry_payload(
                device_code=device_code,
                scenario=scenario,
                point=point,
                index=idx,
                step_seconds=step_seconds,
            )
            result = client.publish(
                topic,
                json.dumps(payload, separators=(",", ":")),
                qos=max(0, min(2, int(config.qos))),
                retain=False,
            )
            result.wait_for_publish(timeout=5.0)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish failed rc={result.rc} topic={topic}")
            published += 1
            previous_ts = point.ts
    finally:
        client.loop_stop()
        client.disconnect()
    return published


def main() -> None:
    args = parse_args()
    prefix = str(args.prefix).strip() or DEFAULT_PREFIX
    anchor = parse_anchor(args.anchor_now)
    minutes = max(120, int(args.minutes))
    step_seconds = max(5, int(args.step_seconds))
    root_rng = random.Random(int(args.seed))
    mqtt_config = MqttReplayConfig(
        enabled=bool(args.mqtt_replay),
        host=str(args.mqtt_host),
        port=int(args.mqtt_port),
        username=str(args.mqtt_username or ""),
        password=str(args.mqtt_password or ""),
        qos=int(args.mqtt_qos),
        topic_template=str(args.mqtt_topic_template),
        speedup=max(1.0, float(args.mqtt_replay_speedup)),
        limit=max(0, int(args.mqtt_replay_limit)),
    )

    totals = {"devices": 0, "metrics": 0, "summaries": 0, "recommendations": 0, "actions": 0, "feedback": 0}
    replay_rows: list[tuple[str, Scenario, int, Point]] = []
    db = SessionLocal()
    try:
        if args.reset:
            deleted = delete_demo_data(db, prefix=prefix)
            print(f"[defense-demo] reset prefix={prefix} deleted_devices={deleted}")

        for idx, scenario in enumerate(SCENARIOS, start=1):
            stats = seed_one_scenario(
                db,
                prefix=prefix,
                scenario=scenario,
                dataset_end=anchor - timedelta(minutes=(len(SCENARIOS) - idx) * 2),
                minutes=minutes,
                step_seconds=step_seconds,
                rng=random.Random(root_rng.randint(1, 10**9)),
            )
            totals["devices"] += 1
            for key in ("metrics", "summaries", "recommendations", "actions", "feedback"):
                totals[key] += int(stats.get(key, 0))
            for point_idx, point in enumerate(stats.get("points", [])):
                replay_rows.append((scenario_code(prefix, scenario), scenario, point_idx, point))
            db.commit()
            print(
                f"[defense-demo] {scenario_code(prefix, scenario)} problem={scenario.problem_type.value} "
                f"metrics={stats['metrics']} rec=1 actions={stats['actions']} feedback={stats['feedback']}"
            )

        if bool(args.with_lifecycle):
            seed_lifecycle_rows(db, anchor=anchor)
            db.commit()
            print("[defense-demo] lifecycle_rows=3")

        if mqtt_config.enabled:
            published = replay_to_mqtt(replay_rows, config=mqtt_config, step_seconds=step_seconds)
            print(f"[defense-demo] mqtt_replay_published={published} broker={mqtt_config.host}:{mqtt_config.port}")

        print("[defense-demo] completed")
        print(f"[defense-demo] prefix={prefix} seed={args.seed} anchor={anchor.isoformat()} step_seconds={step_seconds}")
        for key, value in totals.items():
            print(f"[defense-demo] {key}={value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
