#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path
import random
import sys
from typing import Any, Optional

from sqlalchemy import delete, func, select

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.models.entities import (  # noqa: E402
    ControlAction,
    ControlActionEvalJob,
    ControlActionFeedbackSample,
    Device,
    DeviceMetric,
    DeviceParameter,
)


PROBLEM_TYPES = [
    "success",
    "slow_response",
    "steady_state_error",
    "overshoot_high",
    "oscillation",
    "saturation_limited",
    "disturbance_recovery",
]


@dataclass
class PIDParams:
    kp: float
    ki: float
    kd: float


@dataclass
class ThermalConfig:
    target_temp: float
    target_band: float
    ambient_base: float
    capacity: float
    heater_gain: float
    heat_loss: float
    sensor_alpha: float
    sensor_noise_std: float
    dead_time_steps: int
    pwm_saturation_threshold: float
    overshoot_limit_pct: float


@dataclass
class ThermalState:
    true_temp: float
    measured_temp: float
    integral_error: float
    last_error: float
    delayed_power: deque[float]


@dataclass
class SegmentSummary:
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


@dataclass
class Regime:
    name: str
    heater_mult: float
    loss_mult: float
    max_power: float
    disturbance_sigma: float
    disturbance_bias: float
    spike_prob: float
    spike_mag: float
    ambient_drift: float


REGIMES: dict[str, Regime] = {
    "success": Regime("success", heater_mult=1.0, loss_mult=1.0, max_power=100.0, disturbance_sigma=0.01, disturbance_bias=0.0, spike_prob=0.001, spike_mag=0.12, ambient_drift=0.02),
    "slow_response": Regime("slow_response", heater_mult=0.72, loss_mult=1.08, max_power=88.0, disturbance_sigma=0.015, disturbance_bias=-0.02, spike_prob=0.002, spike_mag=0.1, ambient_drift=0.03),
    "steady_state_error": Regime("steady_state_error", heater_mult=0.86, loss_mult=1.15, max_power=92.0, disturbance_sigma=0.018, disturbance_bias=-0.03, spike_prob=0.002, spike_mag=0.15, ambient_drift=0.04),
    "overshoot_high": Regime("overshoot_high", heater_mult=1.28, loss_mult=0.85, max_power=100.0, disturbance_sigma=0.02, disturbance_bias=0.02, spike_prob=0.003, spike_mag=0.2, ambient_drift=0.05),
    "oscillation": Regime("oscillation", heater_mult=1.16, loss_mult=0.94, max_power=100.0, disturbance_sigma=0.03, disturbance_bias=0.0, spike_prob=0.004, spike_mag=0.25, ambient_drift=0.06),
    "saturation_limited": Regime("saturation_limited", heater_mult=0.62, loss_mult=1.22, max_power=76.0, disturbance_sigma=0.02, disturbance_bias=-0.04, spike_prob=0.003, spike_mag=0.16, ambient_drift=0.05),
    "disturbance_recovery": Regime("disturbance_recovery", heater_mult=1.0, loss_mult=1.0, max_power=96.0, disturbance_sigma=0.03, disturbance_bias=0.0, spike_prob=0.012, spike_mag=0.48, ambient_drift=0.12),
}


def parse_bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate realistic simulated thermal-control data for AI lifecycle testing")
    parser.add_argument("--devices", type=int, default=20)
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--metrics-per-minute", type=float, default=4.0)
    parser.add_argument("--actions-per-device", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true", help="Delete simulator-owned data only (scoped by device prefix)")
    parser.add_argument("--start-days-ago", type=float, default=14.0)
    parser.add_argument("--reuse-devices", type=parse_bool, default=True, help="Reuse existing simulator devices by code prefix/index")
    parser.add_argument("--sim-device-prefix", type=str, default="SIM", help="Simulator device code prefix (default: SIM)")
    parser.add_argument("--append-only", type=parse_bool, default=True, help="When reusing devices, append after latest metric timestamp")
    parser.add_argument("--include-metrics", type=parse_bool, default=True)
    parser.add_argument("--include-actions", type=parse_bool, default=True)
    parser.add_argument("--include-feedback", type=parse_bool, default=True)
    parser.add_argument("--batch-size", type=int, default=2500)
    return parser.parse_args()


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def normalize_tags(values: list[tuple[str, bool]]) -> list[str]:
    return [k for k, ok in values if ok]


def derive_problem_flags(before: SegmentSummary, cfg: ThermalConfig) -> tuple[str, list[str], dict[str, bool]]:
    settling_bad = before.settling_sec is not None and before.settling_sec > 0.65 * (before.point_count * 15.0)
    flags = {
        "saturation_limited": before.saturation_ratio >= 0.38,
        "severe_saturation": before.saturation_ratio >= 0.55,
        "oscillation": before.zero_crossings >= 8,
        "overshoot_high": before.overshoot_c > (cfg.overshoot_limit_pct / 100.0) * max(1.0, cfg.target_temp),
        "steady_state_error": abs(before.mean_error) >= max(0.6, cfg.target_band * 1.5),
        "slow_response": bool(settling_bad),
    }
    primary = "success"
    for candidate in ("saturation_limited", "oscillation", "overshoot_high", "steady_state_error", "slow_response"):
        if flags.get(candidate):
            primary = candidate
            break
    secondary = normalize_tags([(k, v) for k, v in flags.items() if k != primary])
    return primary, secondary, flags


def expected_effect_for_problem(problem: str) -> str:
    return {
        "slow_response": "speed_up_response",
        "steady_state_error": "reduce_steady_state_error",
        "overshoot_high": "reduce_overshoot",
        "oscillation": "reduce_oscillation",
        "saturation_limited": "limited_gain_expected",
        "disturbance_recovery": "stabilize_disturbance_recovery",
        "success": "keep_stable",
    }.get(problem, "keep_stable")


def risk_level_for_problem(problem: str) -> str:
    return {
        "saturation_limited": "High",
        "oscillation": "High",
        "overshoot_high": "High",
        "steady_state_error": "Medium",
        "slow_response": "Medium",
        "disturbance_recovery": "Medium",
    }.get(problem, "Low")


def action_delta_for_problem(
    *,
    source: str,
    problem: str,
    rng: random.Random,
) -> tuple[float, float, float, str]:
    quality = 0.75 if source == "ai_runtime" else 0.45
    jitter = lambda s: rng.uniform(-s, s)  # noqa: E731
    if problem == "slow_response":
        dk = 0.08 + 0.08 * quality + jitter(0.02)
        di = 0.01 + 0.03 * quality + jitter(0.01)
        dd = -0.01 + jitter(0.015)
        candidate = "speed_boost" if source == "ai_runtime" else "manual_speed_tune"
    elif problem == "steady_state_error":
        dk = 0.03 + 0.04 * quality + jitter(0.02)
        di = 0.02 + 0.05 * quality + jitter(0.015)
        dd = jitter(0.01)
        candidate = "sse_speed_balance" if source == "ai_runtime" else "manual_integral_boost"
    elif problem == "overshoot_high":
        dk = -0.05 - 0.05 * quality + jitter(0.015)
        di = -0.005 + jitter(0.01)
        dd = 0.02 + 0.03 * quality + jitter(0.01)
        candidate = "overshoot_guard" if source == "ai_runtime" else "manual_overshoot_guard"
    elif problem == "oscillation":
        dk = -0.07 - 0.05 * quality + jitter(0.02)
        di = -0.015 + jitter(0.012)
        dd = 0.03 + 0.04 * quality + jitter(0.012)
        candidate = "oscillation_damp" if source == "ai_runtime" else "manual_damp"
    elif problem == "saturation_limited":
        dk = -0.02 + jitter(0.02)
        di = -0.01 + jitter(0.012)
        dd = 0.01 + jitter(0.01)
        candidate = "saturation_guard" if source == "ai_runtime" else "manual_saturation_guard"
    else:
        dk = jitter(0.03)
        di = jitter(0.015)
        dd = jitter(0.01)
        candidate = "rule_center" if source == "ai_runtime" else "manual_hold"
    return dk, di, dd, candidate


def pid_step(
    *,
    cfg: ThermalConfig,
    regime: Regime,
    params: PIDParams,
    state: ThermalState,
    dt: float,
    rng: random.Random,
    clean_preview: bool,
    ts_ratio: float,
) -> tuple[float, float, float, bool]:
    target = cfg.target_temp
    ambient = cfg.ambient_base + regime.ambient_drift * math.sin(2.0 * math.pi * ts_ratio)
    error = target - state.measured_temp
    state.integral_error += error * dt
    state.integral_error = clamp(state.integral_error, -250.0, 250.0)
    derivative = (error - state.last_error) / max(dt, 1e-6)
    state.last_error = error

    raw_u = params.kp * error + params.ki * state.integral_error + params.kd * derivative
    u = clamp(raw_u, 0.0, regime.max_power if not clean_preview else 100.0)
    state.delayed_power.append(u)
    applied_power = state.delayed_power.popleft()

    disturbance = 0.0
    if not clean_preview:
        disturbance += rng.gauss(regime.disturbance_bias, regime.disturbance_sigma)
        if rng.random() < regime.spike_prob:
            disturbance += rng.uniform(-regime.spike_mag, regime.spike_mag)
    else:
        disturbance += rng.gauss(regime.disturbance_bias * 0.35, regime.disturbance_sigma * 0.25)

    heater = cfg.heater_gain * regime.heater_mult * (applied_power / 100.0)
    loss = cfg.heat_loss * regime.loss_mult * (state.true_temp - ambient)
    dtemp = ((heater - loss + disturbance) / cfg.capacity) * dt
    state.true_temp += dtemp

    sensor_noise = rng.gauss(0.0, cfg.sensor_noise_std * (0.25 if clean_preview else 1.0))
    state.measured_temp += cfg.sensor_alpha * (state.true_temp - state.measured_temp) + sensor_noise

    saturated = applied_power >= cfg.pwm_saturation_threshold
    return state.measured_temp, target - state.measured_temp, applied_power, saturated


def summarize_window(points: list[dict[str, float]], *, target_band: float) -> SegmentSummary:
    if not points:
        return SegmentSummary(
            in_band_ratio=0.0,
            overshoot_c=0.0,
            settling_sec=None,
            mean_abs_error=0.0,
            saturation_ratio=0.0,
            temp_swing=0.0,
            mean_error=0.0,
            error_std=0.0,
            pwm_mean=0.0,
            pwm_max=0.0,
            zero_crossings=0,
            point_count=0,
        )
    errors = [p["error"] for p in points]
    abs_errors = [abs(e) for e in errors]
    temps = [p["temp"] for p in points]
    pwms = [p["pwm"] for p in points]
    in_band = sum(1 for e in abs_errors if e <= target_band) / float(len(points))
    overshoot_c = max(0.0, max((p["temp"] - p["target"]) for p in points))
    sat_ratio = sum(1 for p in points if p["saturated"]) / float(len(points))
    mean_error = sum(errors) / float(len(errors))
    mae = sum(abs_errors) / float(len(abs_errors))
    var = sum((e - mean_error) ** 2 for e in errors) / float(len(errors))
    error_std = math.sqrt(max(var, 0.0))
    pwm_mean = sum(pwms) / float(len(pwms))
    pwm_max = max(pwms)
    zc = 0
    for i in range(1, len(errors)):
        if (errors[i - 1] > 0 and errors[i] < 0) or (errors[i - 1] < 0 and errors[i] > 0):
            zc += 1

    settling_sec: Optional[float] = None
    hold = min(6, max(3, len(points) // 30))
    for i in range(len(points)):
        tail = errors[i:]
        if len(tail) >= hold and all(abs(v) <= target_band for v in tail[:hold]):
            settling_sec = float(points[i]["elapsed_s"])
            break

    return SegmentSummary(
        in_band_ratio=in_band,
        overshoot_c=overshoot_c,
        settling_sec=settling_sec,
        mean_abs_error=mae,
        saturation_ratio=sat_ratio,
        temp_swing=max(temps) - min(temps),
        mean_error=mean_error,
        error_std=error_std,
        pwm_mean=pwm_mean,
        pwm_max=pwm_max,
        zero_crossings=zc,
        point_count=len(points),
    )


def compare_actual_to_reference(*, actual: SegmentSummary, ref: SegmentSummary) -> dict[str, float]:
    return {
        "in_band_ratio_delta": float(actual.in_band_ratio - ref.in_band_ratio),
        "overshoot_c_delta": float(ref.overshoot_c - actual.overshoot_c),
        "settling_sec_delta": float((ref.settling_sec or 0.0) - (actual.settling_sec or 0.0)),
        "mean_abs_error_delta": float(ref.mean_abs_error - actual.mean_abs_error),
        "saturation_ratio_delta": float(ref.saturation_ratio - actual.saturation_ratio),
        "temp_swing_delta": float(ref.temp_swing - actual.temp_swing),
    }


def derive_actual_effect_label(comp: dict[str, float]) -> str:
    # Engineering deadbands: small noisy delta should remain unchanged.
    thresholds = {
        "in_band_ratio_delta": 0.03,
        "overshoot_c_delta": 0.25,
        "settling_sec_delta": 25.0,
        "mean_abs_error_delta": 0.06,
        "saturation_ratio_delta": 0.04,
        "temp_swing_delta": 0.12,
    }
    signs: list[int] = []
    for key, th in thresholds.items():
        v = float(comp.get(key, 0.0))
        if v > th:
            signs.append(1)
        elif v < -th:
            signs.append(-1)
        else:
            signs.append(0)
    pos = sum(1 for x in signs if x > 0)
    neg = sum(1 for x in signs if x < 0)
    score = sum(signs)
    if (pos >= 3 and neg == 0) or (score >= 2 and neg <= 1):
        return "improved"
    if (neg >= 3 and pos == 0) or (score <= -2 and pos <= 1):
        return "worse"
    return "unchanged"


def derive_preview_gap_label(comp_preview: dict[str, float]) -> str:
    parts = [
        min(1.0, abs(comp_preview.get("in_band_ratio_delta", 0.0)) / 0.20),
        min(1.0, abs(comp_preview.get("overshoot_c_delta", 0.0)) / 1.0),
        min(1.0, abs(comp_preview.get("settling_sec_delta", 0.0)) / 180.0),
        min(1.0, abs(comp_preview.get("mean_abs_error_delta", 0.0)) / 0.50),
        min(1.0, abs(comp_preview.get("saturation_ratio_delta", 0.0)) / 0.30),
        min(1.0, abs(comp_preview.get("temp_swing_delta", 0.0)) / 1.5),
    ]
    score = sum(parts) / float(len(parts))
    if score < 0.33:
        return "low"
    if score < 0.66:
        return "medium"
    return "high"


def choose_regime(rng: random.Random) -> Regime:
    pick = rng.random()
    if pick < 0.18:
        return REGIMES["success"]
    if pick < 0.33:
        return REGIMES["slow_response"]
    if pick < 0.47:
        return REGIMES["steady_state_error"]
    if pick < 0.6:
        return REGIMES["overshoot_high"]
    if pick < 0.74:
        return REGIMES["oscillation"]
    if pick < 0.88:
        return REGIMES["saturation_limited"]
    return REGIMES["disturbance_recovery"]


def evaluate_action_alignment(*, problem: str, delta_kp: float, delta_ki: float, delta_kd: float) -> float:
    score = 0.0
    if problem == "slow_response":
        score += 1.0 if delta_kp > 0 else -1.0
        score += 0.6 if delta_ki > 0 else -0.4
        score += 0.3 if delta_kd <= 0.03 else -0.4
    elif problem == "steady_state_error":
        score += 0.5 if delta_kp >= 0 else -0.4
        score += 1.0 if delta_ki > 0 else -0.8
        score += 0.2 if abs(delta_kd) <= 0.03 else -0.2
    elif problem == "overshoot_high":
        score += 1.0 if delta_kp < 0 else -0.8
        score += 0.8 if delta_kd > 0 else -0.7
        score += 0.3 if delta_ki <= 0 else -0.3
    elif problem == "oscillation":
        score += 0.9 if delta_kp < 0 else -0.7
        score += 1.0 if delta_kd > 0 else -0.8
        score += 0.4 if delta_ki <= 0 else -0.3
    elif problem == "saturation_limited":
        score += 0.8 if delta_kp <= 0 else -0.7
        score += 0.6 if delta_ki <= 0 else -0.5
        score += 0.2 if delta_kd >= 0 else -0.2
    else:
        score += 0.3 if abs(delta_kp) < 0.06 else -0.3
        score += 0.3 if abs(delta_ki) < 0.03 else -0.2
        score += 0.2 if abs(delta_kd) < 0.03 else -0.2
    return clamp(score / 2.5, -1.0, 1.0)


def choose_actual_regime(
    *,
    problem: str,
    source: str,
    alignment: float,
    rng: random.Random,
) -> Regime:
    # Base transition follows pre-action problem; randomness perturbs but does not reset the world.
    ai_boost = 0.15 if source == "ai_runtime" else -0.05
    effective = clamp(alignment + ai_boost + rng.uniform(-0.15, 0.15), -1.0, 1.0)
    disturbance_hit = rng.random() < (0.09 if problem != "disturbance_recovery" else 0.2)
    if disturbance_hit:
        return REGIMES["disturbance_recovery"]

    if problem == "slow_response":
        if effective > 0.35:
            return REGIMES["success"] if rng.random() < 0.72 else REGIMES["steady_state_error"]
        if effective < -0.25:
            return REGIMES["slow_response"] if rng.random() < 0.6 else REGIMES["overshoot_high"]
        return REGIMES["slow_response"]
    if problem == "steady_state_error":
        if effective > 0.35:
            return REGIMES["success"] if rng.random() < 0.66 else REGIMES["slow_response"]
        if effective < -0.25:
            return REGIMES["steady_state_error"] if rng.random() < 0.6 else REGIMES["oscillation"]
        return REGIMES["steady_state_error"]
    if problem == "overshoot_high":
        if effective > 0.35:
            return REGIMES["success"] if rng.random() < 0.65 else REGIMES["steady_state_error"]
        if effective < -0.25:
            return REGIMES["overshoot_high"] if rng.random() < 0.6 else REGIMES["oscillation"]
        return REGIMES["overshoot_high"]
    if problem == "oscillation":
        if effective > 0.35:
            return REGIMES["success"] if rng.random() < 0.62 else REGIMES["slow_response"]
        if effective < -0.25:
            return REGIMES["oscillation"] if rng.random() < 0.65 else REGIMES["overshoot_high"]
        return REGIMES["oscillation"]
    if problem == "saturation_limited":
        if effective > 0.35:
            return REGIMES["steady_state_error"] if rng.random() < 0.55 else REGIMES["success"]
        if effective < -0.25:
            return REGIMES["saturation_limited"]
        return REGIMES["saturation_limited"] if rng.random() < 0.7 else REGIMES["steady_state_error"]
    if problem == "disturbance_recovery":
        if effective > 0.35:
            return REGIMES["success"] if rng.random() < 0.5 else REGIMES["disturbance_recovery"]
        return REGIMES["disturbance_recovery"]
    # success
    if effective < -0.35:
        return REGIMES["overshoot_high"] if rng.random() < 0.5 else REGIMES["oscillation"]
    return REGIMES["success"] if rng.random() < 0.8 else REGIMES["slow_response"]


def simulate_segment(
    *,
    device: Device,
    cfg: ThermalConfig,
    params: PIDParams,
    state: ThermalState,
    regime: Regime,
    start_ts: datetime,
    steps: int,
    step_seconds: float,
    rng: random.Random,
    clean_preview: bool,
    include_metric_rows: bool,
) -> tuple[list[DeviceMetric], list[dict[str, float]], ThermalState]:
    metric_rows: list[DeviceMetric] = []
    points: list[dict[str, float]] = []
    for i in range(steps):
        ts = start_ts + timedelta(seconds=i * step_seconds)
        temp, error, pwm, saturated = pid_step(
            cfg=cfg,
            regime=regime,
            params=params,
            state=state,
            dt=step_seconds,
            rng=rng,
            clean_preview=clean_preview,
            ts_ratio=(i / max(1, steps)),
        )
        in_spec = abs(error) <= cfg.target_band
        is_alarm = abs(error) > (cfg.target_band * 3.0) or saturated
        points.append(
            {
                "temp": float(temp),
                "target": float(cfg.target_temp),
                "error": float(error),
                "pwm": float(pwm),
                "saturated": bool(saturated),
                "elapsed_s": float(i * step_seconds),
            }
        )
        if include_metric_rows:
            metric_rows.append(
                DeviceMetric(
                    device_id=device.id,
                    timestamp=ts,
                    current_temp=float(temp),
                    target_temp=float(cfg.target_temp),
                    error=float(error),
                    pwm_output=float(pwm),
                    status="active",
                    in_spec=bool(in_spec),
                    is_alarm=bool(is_alarm),
                )
            )
    return metric_rows, points, state


def build_runtime_decision_summary(
    *,
    rng: random.Random,
    primary_problem_type: str,
    selected_candidate_id: str,
) -> dict[str, Any]:
    ranking_used = rng.random() < 0.84
    fallback_used = not ranking_used and rng.random() < 0.9
    candidate_count = rng.randint(3, 6)
    top_success = rng.uniform(0.42, 0.94)
    top_gap = rng.uniform(0.30, 0.90)
    total = 0.65 * top_success + 0.35 * top_gap
    return {
        "runtime_source": "simulator",
        "fallback_used": bool(fallback_used),
        "diagnosis_source": "rule_classifier",
        "base_recommendation_source": "rule_tuning_engine",
        "ranking_used": bool(ranking_used),
        "ranking_fallback_used": bool(fallback_used),
        "primary_problem_type": primary_problem_type,
        "selected_candidate_id": selected_candidate_id if ranking_used else "rule_center",
        "base_candidate_id": "rule_center",
        "candidate_count": int(candidate_count),
        "evaluated_candidate_count": int(candidate_count),
        "configured_candidate_limit": 6,
        "top_score": float(total),
        "top_success_score": float(top_success),
        "top_gap_score": float(top_gap),
    }


def flush_metrics(db, rows: list[DeviceMetric], *, batch_size: int) -> None:
    if not rows:
        return
    for i in range(0, len(rows), batch_size):
        db.add_all(rows[i : i + batch_size])
        db.flush()


def _stable_device_rng(seed: int, code: str) -> random.Random:
    # Stable per-device random generator (independent of run order).
    h = 1469598103934665603
    for ch in f"{seed}:{code}":
        h ^= ord(ch)
        h *= 1099511628211
        h &= 0xFFFFFFFFFFFFFFFF
    return random.Random(h)


def build_device_physics(*, seed: int, code: str, target: float, band: float) -> ThermalConfig:
    r = _stable_device_rng(seed, code)
    return ThermalConfig(
        target_temp=target,
        target_band=band,
        ambient_base=r.uniform(18.0, 30.0),
        capacity=r.uniform(160.0, 420.0),
        heater_gain=r.uniform(3.8, 8.5),
        heat_loss=r.uniform(0.014, 0.04),
        sensor_alpha=r.uniform(0.08, 0.2),
        sensor_noise_std=r.uniform(0.025, 0.09),
        dead_time_steps=r.randint(1, 6),
        pwm_saturation_threshold=r.uniform(84.0, 95.0),
        overshoot_limit_pct=r.uniform(2.8, 5.2),
    )


def list_simulator_devices(db, *, prefix: str) -> list[Device]:
    like = f"{prefix}-%"
    return db.scalars(select(Device).where(Device.code.like(like)).order_by(Device.code.asc())).all()


def delete_simulator_data(db, *, prefix: str) -> int:
    devices = list_simulator_devices(db, prefix=prefix)
    if not devices:
        return 0
    ids = [int(d.id) for d in devices]
    # Explicit child cleanup scoped to simulator devices only.
    db.execute(delete(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id.in_(ids)))
    db.execute(delete(ControlActionEvalJob).where(ControlActionEvalJob.device_id.in_(ids)))
    db.execute(delete(ControlAction).where(ControlAction.device_id.in_(ids)))
    db.execute(delete(DeviceMetric).where(DeviceMetric.device_id.in_(ids)))
    db.execute(delete(DeviceParameter).where(DeviceParameter.device_id.in_(ids)))
    db.execute(delete(Device).where(Device.id.in_(ids)))
    db.commit()
    return len(ids)


def create_device_with_config(
    *,
    db,
    idx: int,
    rng: random.Random,
    global_seed: int,
    prefix: str,
    reuse_devices: bool,
) -> tuple[Device, DeviceParameter, ThermalConfig, PIDParams]:
    code = f"{prefix}-{idx:03d}"
    existing = db.scalar(select(Device).where(Device.code == code))
    if existing is not None and not reuse_devices:
        raise RuntimeError(f"Device code already exists and reuse is disabled: {code}")
    if existing is not None:
        device = existing
        pid_row = db.scalar(
            select(DeviceParameter)
            .where(DeviceParameter.device_id == device.id)
            .order_by(DeviceParameter.updated_at.desc(), DeviceParameter.id.desc())
            .limit(1)
        )
        if pid_row is None:
            pid_row = DeviceParameter(
                device_id=device.id,
                kp=2.4,
                ki=0.36,
                kd=0.08,
                control_mode="pid_control",
                target_band=0.6,
                overshoot_limit_pct=4.0,
                saturation_warn_ratio=0.30,
                saturation_high_ratio=0.60,
                pwm_saturation_threshold=90.0,
                steady_window_samples=12,
                sampling_period_ms=250,
                upload_period_s=10,
                updated_at=datetime.utcnow(),
                updated_by="simulator_repair",
            )
            db.add(pid_row)
            db.flush()
        pid = PIDParams(kp=float(pid_row.kp), ki=float(pid_row.ki), kd=float(pid_row.kd))
        cfg = build_device_physics(
            seed=global_seed,
            code=device.code,
            target=float(device.target_temp),
            band=float(pid_row.target_band or 0.6),
        )
        return device, pid_row, cfg, pid

    target = rng.uniform(42.0, 165.0)
    band = rng.uniform(0.4, 0.9)
    device = Device(
        code=code,
        name=f"Simulated Thermal Unit {idx:03d}",
        line=f"Line {1 + ((idx - 1) % 4)}",
        location=f"Zone {chr(65 + ((idx - 1) % 8))}",
        status="active",
        current_temp=target - rng.uniform(1.2, 5.0),
        target_temp=target,
        pwm_output=rng.uniform(20.0, 70.0),
        is_alarm=False,
        is_online=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(device)
    db.flush()

    pid = PIDParams(
        kp=rng.uniform(1.8, 3.4),
        ki=rng.uniform(0.24, 0.58),
        kd=rng.uniform(0.04, 0.16),
    )
    cfg = build_device_physics(seed=global_seed, code=device.code, target=target, band=band)
    param = DeviceParameter(
        device_id=device.id,
        kp=pid.kp,
        ki=pid.ki,
        kd=pid.kd,
        control_mode="pid_control",
        target_band=cfg.target_band,
        overshoot_limit_pct=cfg.overshoot_limit_pct,
        saturation_warn_ratio=0.30,
        saturation_high_ratio=0.60,
        pwm_saturation_threshold=cfg.pwm_saturation_threshold,
        steady_window_samples=max(10, int(60 / max(0.2, 1.0 / cfg.target_band))),
        sampling_period_ms=250,
        upload_period_s=10,
        updated_at=datetime.utcnow(),
        updated_by="simulator",
    )
    db.add(param)
    db.flush()
    return device, param, cfg, pid


def generate_for_device(
    *,
    db,
    device: Device,
    param_row: DeviceParameter,
    cfg: ThermalConfig,
    pid: PIDParams,
    rng: random.Random,
    start_ts: datetime,
    end_ts: datetime,
    step_seconds: float,
    actions_per_device: int,
    include_metrics: bool,
    include_actions: bool,
    include_feedback: bool,
    batch_size: int,
) -> dict[str, int]:
    total_metrics = 0
    total_actions = 0
    total_jobs = 0
    total_feedback = 0
    total_eligible = 0
    total_ai_actions = 0
    total_manual_actions = 0

    total_steps = max(1, int((end_ts - start_ts).total_seconds() / step_seconds))
    action_steps: list[int] = []
    if include_actions and actions_per_device > 0:
        lower = max(20, int(20 * 60 / step_seconds))
        upper = max(lower + 1, total_steps - lower)
        for _ in range(actions_per_device):
            action_steps.append(rng.randint(lower, upper))
        action_steps = sorted(action_steps)

    state = ThermalState(
        true_temp=device.current_temp + rng.uniform(-0.6, 0.6),
        measured_temp=device.current_temp,
        integral_error=0.0,
        last_error=cfg.target_temp - device.current_temp,
        delayed_power=deque([device.pwm_output] * max(1, cfg.dead_time_steps), maxlen=max(1, cfg.dead_time_steps)),
    )
    now_step = 0
    now_ts = start_ts
    history_points: deque[dict[str, float]] = deque(maxlen=max(1, int(20 * 60 / step_seconds)))
    pending_metric_rows: list[DeviceMetric] = []
    current_pid = PIDParams(pid.kp, pid.ki, pid.kd)

    def run_steps(steps: int, regime: Regime, clean_preview: bool = False) -> SegmentSummary:
        nonlocal now_step, now_ts, state, total_metrics, pending_metric_rows
        rows, points, state = simulate_segment(
            device=device,
            cfg=cfg,
            params=current_pid,
            state=state,
            regime=regime,
            start_ts=now_ts,
            steps=steps,
            step_seconds=step_seconds,
            rng=rng,
            clean_preview=clean_preview,
            include_metric_rows=(include_metrics and (not clean_preview)),
        )
        if include_metrics and not clean_preview and rows:
            pending_metric_rows.extend(rows)
            total_metrics += len(rows)
            if len(pending_metric_rows) >= batch_size:
                flush_metrics(db, pending_metric_rows, batch_size=batch_size)
                pending_metric_rows = []
        for p in points:
            history_points.append(p)
        now_step += steps
        now_ts += timedelta(seconds=steps * step_seconds)
        return summarize_window(points, target_band=cfg.target_band)

    for action_step in action_steps:
        if action_step <= now_step:
            continue
        run_steps(action_step - now_step, choose_regime(rng), clean_preview=False)

        before_points = list(history_points)
        before_summary = summarize_window(before_points, target_band=cfg.target_band)
        primary_problem, secondary_problems, problem_flags = derive_problem_flags(before_summary, cfg)
        source = "ai_runtime" if rng.random() < 0.62 else "manual_user"
        if source == "ai_runtime":
            total_ai_actions += 1
        else:
            total_manual_actions += 1

        dk, di, dd, selected_candidate = action_delta_for_problem(
            source=source,
            problem=primary_problem,
            rng=rng,
        )
        new_pid = PIDParams(
            kp=clamp(current_pid.kp + dk, 0.5, 6.0),
            ki=clamp(current_pid.ki + di, 0.02, 1.2),
            kd=clamp(current_pid.kd + dd, 0.0, 0.8),
        )

        action = ControlAction(
            device_id=device.id,
            source=source,
            source_ref_id=None,
            action_type="pid_apply",
            initiated_by="ai_runtime" if source == "ai_runtime" else "operator_sim",
            applied_at=now_ts,
            status="applied",
            control_mode_before="pid_control",
            control_mode_after="pid_control",
            target_temp_before=cfg.target_temp,
            target_temp_after=cfg.target_temp,
            kp_before=current_pid.kp,
            ki_before=current_pid.ki,
            kd_before=current_pid.kd,
            kp_after=new_pid.kp,
            ki_after=new_pid.ki,
            kd_after=new_pid.kd,
            delta_kp=new_pid.kp - current_pid.kp,
            delta_ki=new_pid.ki - current_pid.ki,
            delta_kd=new_pid.kd - current_pid.kd,
            context_snapshot={
                "problem_type": primary_problem,
                "secondary_problem_types": secondary_problems,
                "problem_flags": problem_flags,
            },
            created_at=now_ts,
            updated_at=now_ts,
        )
        db.add(action)
        db.flush()
        total_actions += 1

        obs_minutes = int(rng.choice([10, 12, 15, 18, 20]))
        obs_steps = max(8, int((obs_minutes * 60) / step_seconds))

        # Preview branch: cleaner and simpler than actual.
        preview_state = ThermalState(
            true_temp=state.true_temp,
            measured_temp=state.measured_temp,
            integral_error=state.integral_error,
            last_error=state.last_error,
            delayed_power=deque(list(state.delayed_power), maxlen=max(1, cfg.dead_time_steps)),
        )
        current_pid = new_pid
        _rows_preview, points_preview, _ = simulate_segment(
            device=device,
            cfg=cfg,
            params=current_pid,
            state=preview_state,
            regime=REGIMES["success"],
            start_ts=now_ts,
            steps=obs_steps,
            step_seconds=step_seconds,
            rng=random.Random(rng.randint(0, 10**9)),
            clean_preview=True,
            include_metric_rows=False,
        )
        preview_summary = summarize_window(points_preview, target_band=cfg.target_band)

        # Actual branch: condition on pre-action problem + action alignment + source, with stochastic disturbance.
        alignment = evaluate_action_alignment(
            problem=primary_problem,
            delta_kp=float(action.delta_kp or 0.0),
            delta_ki=float(action.delta_ki or 0.0),
            delta_kd=float(action.delta_kd or 0.0),
        )
        actual_regime = choose_actual_regime(
            problem=primary_problem,
            source=source,
            alignment=alignment,
            rng=rng,
        )
        actual_summary = run_steps(obs_steps, actual_regime, clean_preview=False)
        comp_before = compare_actual_to_reference(actual=actual_summary, ref=before_summary)
        comp_preview = compare_actual_to_reference(actual=actual_summary, ref=preview_summary)
        effect_label = derive_actual_effect_label(comp_before)
        preview_gap_label = derive_preview_gap_label(comp_preview)

        insufficient = rng.random() < 0.07 or actual_summary.point_count < max(12, int(8 * 60 / step_seconds))
        quality = "reject"
        if not insufficient:
            if rng.random() < 0.62:
                quality = "high"
            else:
                quality = "medium"
        trainable = bool(not insufficient and quality in {"high", "medium"} and effect_label in {"improved", "unchanged", "worse"})

        eval_job_status = "done" if not insufficient else "insufficient_data"
        eval_job = ControlActionEvalJob(
            control_action_id=action.id,
            device_id=device.id,
            status=eval_job_status,
            scheduled_at=now_ts + timedelta(minutes=obs_minutes),
            observation_window_minutes=obs_minutes,
            attempt_count=1 if eval_job_status == "done" else 2,
            last_error=None if eval_job_status == "done" else "simulated_insufficient_window",
            created_at=now_ts,
            updated_at=now_ts + timedelta(minutes=obs_minutes),
        )
        db.add(eval_job)
        total_jobs += 1

        if include_feedback:
            runtime_summary = (
                build_runtime_decision_summary(
                    rng=rng,
                    primary_problem_type=primary_problem,
                    selected_candidate_id=selected_candidate,
                )
                if source == "ai_runtime"
                else None
            )
            feedback = ControlActionFeedbackSample(
                control_action_id=action.id,
                device_id=device.id,
                source=source,
                source_ref_id=None,
                action_type=action.action_type,
                initiated_by=action.initiated_by,
                generated_at=action.applied_at - timedelta(minutes=rng.uniform(0.5, 3.0)) if source == "ai_runtime" else None,
                applied_at=action.applied_at,
                evaluated_at=action.applied_at + timedelta(minutes=obs_minutes),
                primary_problem_type=primary_problem,
                secondary_problem_types=secondary_problems,
                problem_flags=problem_flags,
                expected_effect=expected_effect_for_problem(primary_problem),
                risk_level=risk_level_for_problem(primary_problem),
                confidence=(rng.uniform(0.62, 0.95) if source == "ai_runtime" else rng.uniform(0.48, 0.86)),
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
                overshoot_pct=(before_summary.overshoot_c / max(0.01, cfg.target_temp)) * 100.0,
                settling_sec=before_summary.settling_sec,
                saturation_ratio=before_summary.saturation_ratio,
                runtime_decision_summary=runtime_summary,
                preview_metrics_summary={
                    "in_band_ratio": preview_summary.in_band_ratio,
                    "overshoot_c": preview_summary.overshoot_c,
                    "settling_sec": preview_summary.settling_sec,
                    "mean_abs_error": preview_summary.mean_abs_error,
                    "saturation_ratio": preview_summary.saturation_ratio,
                    "temp_swing": preview_summary.temp_swing,
                },
                actual_metrics_summary={
                    "point_count": actual_summary.point_count,
                    "in_band_ratio_after": actual_summary.in_band_ratio,
                    "overshoot_c_after": actual_summary.overshoot_c,
                    "settling_sec_after": actual_summary.settling_sec,
                    "mean_abs_error_after": actual_summary.mean_abs_error,
                    "saturation_ratio_after": actual_summary.saturation_ratio,
                    "temp_swing_after": actual_summary.temp_swing,
                },
                comparison_to_before=comp_before,
                comparison_to_preview=comp_preview,
                actual_effect_label=effect_label,
                preview_gap_label=preview_gap_label,
                insufficient_data=bool(insufficient),
                sample_quality=quality,
                is_training_eligible=bool(trainable),
                training_exclusion_reason=(None if trainable else ("insufficient_data" if insufficient else "sample_quality_reject")),
                label_source="simulator",
                created_at=action.applied_at + timedelta(minutes=obs_minutes),
                updated_at=action.applied_at + timedelta(minutes=obs_minutes),
            )
            db.add(feedback)
            total_feedback += 1
            if trainable:
                total_eligible += 1

        # update row-level current params for realism
        param_row.kp = current_pid.kp
        param_row.ki = current_pid.ki
        param_row.kd = current_pid.kd
        param_row.updated_at = now_ts
        param_row.updated_by = "simulator"

    # run tail to end
    if now_ts < end_ts:
        remain_steps = max(0, int((end_ts - now_ts).total_seconds() / step_seconds))
        if remain_steps > 0:
            run_steps(remain_steps, choose_regime(rng), clean_preview=False)

    if include_metrics and pending_metric_rows:
        flush_metrics(db, pending_metric_rows, batch_size=batch_size)
    device.current_temp = float(state.measured_temp)
    device.target_temp = cfg.target_temp
    device.pwm_output = float(state.delayed_power[-1] if state.delayed_power else 0.0)
    device.updated_at = datetime.utcnow()

    db.flush()
    return {
        "metrics": total_metrics,
        "actions": total_actions,
        "jobs": total_jobs,
        "feedback": total_feedback,
        "eligible_feedback": total_eligible,
        "ai_actions": total_ai_actions,
        "manual_actions": total_manual_actions,
    }


def main() -> None:
    args = parse_args()
    rng = random.Random(int(args.seed))
    now = datetime.utcnow()
    start_ts = now - timedelta(days=float(args.start_days_ago))
    end_ts = start_ts + timedelta(days=float(args.days))
    if end_ts <= start_ts:
        raise SystemExit("Invalid timeline: --days must be > 0.")
    step_seconds = 60.0 / max(0.1, float(args.metrics_per_minute))

    db = SessionLocal()
    try:
        if args.reset:
            deleted = delete_simulator_data(db, prefix=str(args.sim_device_prefix))
            print(f"[sim] reset scoped to prefix={args.sim_device_prefix}, deleted_devices={deleted}")

        totals = {
            "devices": 0,
            "metrics": 0,
            "actions": 0,
            "jobs": 0,
            "feedback": 0,
            "eligible_feedback": 0,
            "ai_actions": 0,
            "manual_actions": 0,
        }

        for i in range(1, int(args.devices) + 1):
            device, param_row, cfg, pid = create_device_with_config(
                db=db,
                idx=i,
                rng=rng,
                global_seed=int(args.seed),
                prefix=str(args.sim_device_prefix),
                reuse_devices=bool(args.reuse_devices),
            )
            device_start_ts = start_ts
            if bool(args.append_only):
                last_metric_ts = db.scalar(select(func.max(DeviceMetric.timestamp)).where(DeviceMetric.device_id == device.id))
                if last_metric_ts is not None:
                    device_start_ts = max(device_start_ts, last_metric_ts + timedelta(seconds=step_seconds))
            if device_start_ts >= end_ts:
                print(
                    f"[sim] device={device.code} skipped (append_only window exhausted): "
                    f"start={device_start_ts.isoformat()} end={end_ts.isoformat()}"
                )
                continue
            stats = generate_for_device(
                db=db,
                device=device,
                param_row=param_row,
                cfg=cfg,
                pid=pid,
                rng=random.Random(rng.randint(0, 10**9)),
                start_ts=device_start_ts,
                end_ts=end_ts,
                step_seconds=step_seconds,
                actions_per_device=max(0, int(args.actions_per_device)),
                include_metrics=bool(args.include_metrics),
                include_actions=bool(args.include_actions),
                include_feedback=bool(args.include_feedback),
                batch_size=max(200, int(args.batch_size)),
            )
            totals["devices"] += 1
            for k in ("metrics", "actions", "jobs", "feedback", "eligible_feedback", "ai_actions", "manual_actions"):
                totals[k] += int(stats.get(k, 0))
            db.commit()
            print(
                f"[sim] device={device.code} metrics={stats['metrics']} actions={stats['actions']} "
                f"feedback={stats['feedback']} eligible={stats['eligible_feedback']}"
            )

        print("[sim] generation completed")
        print(f"[sim] seed={args.seed} start={start_ts.isoformat()} end={end_ts.isoformat()} step_seconds={step_seconds:.2f}")
        for k, v in totals.items():
            print(f"[sim] {k}={v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
