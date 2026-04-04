from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.hmi import (
    AIRecommendation,
    AckRecord,
    ControlGoalsConfig,
    ControlCompareConclusion,
    ControlCompareMetric,
    ControlCompareThresholds,
    ControlCompareWindow,
    ControlEffectComparison,
)

TARGET_BAND_C = 0.30
TEMP_RATE_THRESHOLD_C_PER_S = 0.02
STEADY_HOLD_SECONDS = 60
FLAT_CHANGE_PCT = 5.0
PWM_SATURATION_LOW = 10
PWM_SATURATION_HIGH = 245
REALTIME_STEADY_ERROR_AXIS_C = 1.2
WINDOW_GUARD_SECONDS = 15
WINDOW_DURATION_SECONDS = 180
SAMPLE_INTERVAL_SECONDS = 5
MIN_WINDOW_SAMPLES = 24

STATUS_IMPROVED = "improved"
STATUS_WORSE = "worse"
STATUS_FLAT = "flat"
STATUS_NOT_COMPARABLE = "not_comparable"

CONCLUSION_MAJOR = "major_improvement"
CONCLUSION_SLIGHT = "slight_improvement"
CONCLUSION_NONE = "no_significant_change"
CONCLUSION_WORSE = "degraded"
CONCLUSION_NOT_COMPARABLE = "not_comparable"

METRIC_DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    ("steady_state_error_c", "Steady-state error", "C", "lower"),
    ("max_overshoot_c", "Max overshoot", "C", "lower"),
    ("settling_time_s", "Settling time", "s", "lower"),
    ("rise_time_s", "Rise time", "s", "lower"),
    ("steady_stddev_c", "Steady-state stddev", "C", "lower"),
    ("saturation_ratio_pct", "PWM saturation ratio", "%", "lower"),
)

CORE_METRICS = ("steady_state_error_c", "max_overshoot_c", "settling_time_s")


@dataclass
class SimPoint:
  timestamp: datetime
  temp_c: float
  target_c: float
  error_c: float
  pwm_duty: float


@dataclass
class WindowEvaluation:
  sample_count: int
  steady_state_detected: bool
  steady_state_error_c: float | None
  max_overshoot_c: float
  settling_time_s: float | None
  rise_time_s: float | None
  steady_stddev_c: float | None
  saturation_ratio_pct: float
  pwm_avg: float
  pwm_current: float
  errors: list[float]
  temps: list[float]
  pwms: list[float]

  def value(self, key: str) -> float | None:
    return getattr(self, key, None)


@dataclass(frozen=True)
class CompareConfig:
  target_band_c: float = TARGET_BAND_C
  temp_rate_threshold_c_per_s: float = TEMP_RATE_THRESHOLD_C_PER_S
  steady_hold_seconds: int = STEADY_HOLD_SECONDS
  flat_change_pct: float = FLAT_CHANGE_PCT
  pwm_saturation_low: int = PWM_SATURATION_LOW
  pwm_saturation_high: int = PWM_SATURATION_HIGH
  realtime_steady_error_axis_c: float = REALTIME_STEADY_ERROR_AXIS_C


def build_compare_config(raw: dict | None = None) -> CompareConfig:
  if not raw:
    return CompareConfig()
  model = ControlGoalsConfig.model_validate(raw)
  return CompareConfig(**model.model_dump())


def build_params_tuning_compare(
    device: dict,
    acks: list[AckRecord],
    config: CompareConfig,
    now: datetime | None = None,
) -> ControlEffectComparison:
  current_time = now or datetime.now(UTC)
  if len(acks) < 2:
    return _build_not_comparable(
        scenario="params_tuning",
        event_label="Last parameter update",
        device_id=device["device_id"],
        event_at=acks[0].received_at if acks else None,
        reason="Need at least two successful parameter acks to compare before/after windows.",
        config=config,
    )
  after_ack = acks[0]
  baseline_ack = acks[1]
  return _build_effect_comparison(
      scenario="params_tuning",
      event_label="Last parameter update",
      device=device,
      baseline_ack=baseline_ack,
      after_ack=after_ack,
      config=config,
      now=current_time,
  )


def build_ai_adoption_compare(
    device: dict,
    acks: list[AckRecord],
    recommendation: AIRecommendation | None,
    config: CompareConfig,
    now: datetime | None = None,
) -> ControlEffectComparison:
  current_time = now or datetime.now(UTC)
  if recommendation is None:
    return _build_not_comparable(
        scenario="ai_adoption",
        event_label="AI recommendation adoption",
        device_id=device["device_id"],
        event_at=None,
        reason="No recommendation available for adoption comparison.",
        config=config,
    )
  if len(acks) < 2:
    return _build_not_comparable(
        scenario="ai_adoption",
        event_label="AI recommendation adoption",
        device_id=device["device_id"],
        event_at=acks[0].received_at if acks else None,
        reason="Need one pre-adoption ack and one post-adoption ack to compare AI impact.",
        config=config,
    )
  if not _is_ai_adopted(acks[0], recommendation):
    return _build_not_comparable(
        scenario="ai_adoption",
        event_label="AI recommendation adoption",
        device_id=device["device_id"],
        event_at=acks[0].received_at,
        reason="Latest parameter state does not match the suggested AI values yet.",
        config=config,
    )
  after_ack = acks[0]
  baseline_ack = acks[1]
  return _build_effect_comparison(
      scenario="ai_adoption",
      event_label="AI recommendation adoption",
      device=device,
      baseline_ack=baseline_ack,
      after_ack=after_ack,
      config=config,
      now=current_time,
  )


def _build_effect_comparison(
    scenario: str,
    event_label: str,
    device: dict,
    baseline_ack: AckRecord,
    after_ack: AckRecord,
    config: CompareConfig,
    now: datetime,
) -> ControlEffectComparison:
  if not baseline_ack.success or not after_ack.success:
    return _build_not_comparable(
        scenario=scenario,
        event_label=event_label,
        device_id=device["device_id"],
        event_at=after_ack.received_at,
        reason="Comparison requires two successful ack records.",
        config=config,
    )

  event_at = datetime.fromisoformat(after_ack.received_at)
  baseline_start = event_at - timedelta(seconds=WINDOW_GUARD_SECONDS + WINDOW_DURATION_SECONDS)
  baseline_end = event_at - timedelta(seconds=WINDOW_GUARD_SECONDS)
  after_start = event_at + timedelta(seconds=WINDOW_GUARD_SECONDS)
  after_end = event_at + timedelta(seconds=WINDOW_GUARD_SECONDS + WINDOW_DURATION_SECONDS)

  baseline_window = ControlCompareWindow(
      label="Baseline",
      started_at=baseline_start.isoformat(),
      ended_at=baseline_end.isoformat(),
      sample_count=0,
      steady_state_detected=False,
  )
  after_window = ControlCompareWindow(
      label="After",
      started_at=after_start.isoformat(),
      ended_at=after_end.isoformat(),
      sample_count=0,
      steady_state_detected=False,
  )

  if now < after_end:
    return _build_not_comparable(
        scenario=scenario,
        event_label=event_label,
        device_id=device["device_id"],
        event_at=after_ack.received_at,
        reason="After window is still collecting data; comparison is not ready.",
        config=config,
        baseline_window=baseline_window,
        after_window=after_window,
    )

  baseline_points = _simulate_window(device, baseline_ack, baseline_start, baseline_end, seed=1.0)
  after_points = _simulate_window(device, after_ack, after_start, after_end, seed=2.0)
  baseline_eval = _evaluate_window(baseline_points, config)
  after_eval = _evaluate_window(after_points, config)

  baseline_window.sample_count = baseline_eval.sample_count
  baseline_window.steady_state_detected = baseline_eval.steady_state_detected
  after_window.sample_count = after_eval.sample_count
  after_window.steady_state_detected = after_eval.steady_state_detected

  if baseline_eval.sample_count < MIN_WINDOW_SAMPLES or after_eval.sample_count < MIN_WINDOW_SAMPLES:
    return _build_not_comparable(
        scenario=scenario,
        event_label=event_label,
        device_id=device["device_id"],
        event_at=after_ack.received_at,
        reason="Window sample count is insufficient for reliable comparison.",
        config=config,
        baseline_window=baseline_window,
        after_window=after_window,
    )

  metrics = _build_metric_rows(baseline_eval, after_eval, config)
  conclusion = _build_conclusion(metrics)
  comparable = conclusion.status != CONCLUSION_NOT_COMPARABLE
  reason = None if comparable else "Core metrics are incomplete; baseline and after are not comparable."
  return ControlEffectComparison(
      scenario=scenario,
      device_id=device["device_id"],
      event_label=event_label,
      event_at=after_ack.received_at,
      comparable=comparable,
      not_comparable_reason=reason,
      baseline_window=baseline_window,
      after_window=after_window,
      thresholds=_thresholds_model(config),
      metrics=metrics,
      conclusion=conclusion,
      data_source="fastapi_aggregate",
  )


def _simulate_window(
    device: dict,
    ack: AckRecord,
    started_at: datetime,
    ended_at: datetime,
    seed: float,
) -> list[SimPoint]:
  total_seconds = max(0, int((ended_at - started_at).total_seconds()))
  steps = (total_seconds // SAMPLE_INTERVAL_SECONDS) + 1

  kp_factor = max(0.15, ack.kp / 120.0)
  ki_factor = max(0.05, ack.ki / 12.0)
  kd_factor = max(0.0, ack.kd / 6.0)
  variation = max(0.05, float(device.get("variation", 0.2)))

  aggressiveness = kp_factor * 0.62 + ki_factor * 0.30 + kd_factor * 0.08
  tau = _clamp(120.0 - aggressiveness * 72.0 + variation * 22.0, 28.0, 160.0)
  oscillation_amp = _clamp((kp_factor - 0.90) * 0.18 + ki_factor * 0.05 - kd_factor * 0.08, 0.0, 0.45)
  disturbance = variation * 0.05
  initial_error = _clamp(1.4 - aggressiveness * 0.52 + variation * 0.62, 0.35, 2.8)
  if ack.control_mode == "manual_hold":
    tau = 9999.0
    oscillation_amp = 0.0
    initial_error = max(initial_error, 1.0)

  points: list[SimPoint] = []
  integral_error = 0.0
  prev_temp = ack.target_temp_c - initial_error
  for index in range(steps):
    ts = started_at + timedelta(seconds=index * SAMPLE_INTERVAL_SECONDS)
    elapsed_s = index * SAMPLE_INTERVAL_SECONDS
    phase = (ts.timestamp() / 38.0) + seed

    if ack.control_mode == "manual_hold":
      temp_c = ack.target_temp_c - initial_error * 0.75 + disturbance * math.sin(phase)
    else:
      approach = ack.target_temp_c - initial_error * math.exp(-elapsed_s / tau)
      ringing = oscillation_amp * math.exp(-elapsed_s / 55.0) * math.sin((2.0 * math.pi * elapsed_s / 52.0) + seed)
      noise = disturbance * math.sin((elapsed_s + seed * 12.0) / 45.0)
      temp_c = approach + ringing + noise

    error_c = ack.target_temp_c - temp_c
    derivative = (temp_c - prev_temp) / SAMPLE_INTERVAL_SECONDS
    integral_error += error_c * SAMPLE_INTERVAL_SECONDS
    pwm_base = 128.0 + error_c * (58.0 + kp_factor * 10.0) + (integral_error / 210.0) - derivative * 34.0
    if ack.control_mode == "manual_hold":
      pwm_base *= 0.4
    pwm_duty = _clamp(pwm_base, 0.0, 255.0)

    points.append(
        SimPoint(
            timestamp=ts,
            temp_c=temp_c,
            target_c=ack.target_temp_c,
            error_c=error_c,
            pwm_duty=pwm_duty,
        ),
    )
    prev_temp = temp_c
  return points


def _evaluate_window(points: list[SimPoint], config: CompareConfig) -> WindowEvaluation:
  if not points:
    return WindowEvaluation(
        sample_count=0,
        steady_state_detected=False,
        steady_state_error_c=None,
        max_overshoot_c=0.0,
        settling_time_s=None,
        rise_time_s=None,
        steady_stddev_c=None,
        saturation_ratio_pct=0.0,
        pwm_avg=0.0,
        pwm_current=0.0,
        errors=[],
        temps=[],
        pwms=[],
    )

  temps = [item.temp_c for item in points]
  targets = [item.target_c for item in points]
  errors = [item.error_c for item in points]
  pwms = [item.pwm_duty for item in points]

  rates = [0.0]
  for index in range(1, len(points)):
    rates.append(abs((temps[index] - temps[index - 1]) / SAMPLE_INTERVAL_SECONDS))

  hold_samples = max(1, math.ceil(config.steady_hold_seconds / SAMPLE_INTERVAL_SECONDS))
  run_count = 0
  steady_start_idx: int | None = None
  for index, error in enumerate(errors):
    in_band = abs(error) <= config.target_band_c
    low_rate = rates[index] <= config.temp_rate_threshold_c_per_s
    if in_band and low_rate:
      run_count += 1
    else:
      run_count = 0
    if run_count >= hold_samples:
      steady_start_idx = index - hold_samples + 1
      break

  steady_state_detected = steady_start_idx is not None
  if steady_state_detected and steady_start_idx is not None:
    steady_errors = [abs(value) for value in errors[steady_start_idx:]]
    steady_temps = temps[steady_start_idx:]
    steady_state_error_c = _safe_mean(steady_errors)
    steady_stddev_c = _safe_stddev(steady_temps)
    settling_time_s = float(steady_start_idx * SAMPLE_INTERVAL_SECONDS)
  else:
    steady_state_error_c = None
    steady_stddev_c = None
    settling_time_s = None

  initial_temp = temps[0]
  target_temp = targets[0]
  step = target_temp - initial_temp
  rise_time_s: float | None = None
  if abs(step) < 0.05:
    rise_time_s = 0.0
  else:
    threshold = initial_temp + step * 0.9
    for index, temp in enumerate(temps):
      if (step >= 0 and temp >= threshold) or (step < 0 and temp <= threshold):
        rise_time_s = float(index * SAMPLE_INTERVAL_SECONDS)
        break

  if step >= 0:
    max_overshoot_c = max(0.0, max(temp - target_temp for temp in temps))
  else:
    max_overshoot_c = max(0.0, max(target_temp - temp for temp in temps))

  saturation_count = sum(1 for pwm in pwms if pwm <= config.pwm_saturation_low or pwm >= config.pwm_saturation_high)
  saturation_ratio_pct = (saturation_count / len(pwms)) * 100.0
  return WindowEvaluation(
      sample_count=len(points),
      steady_state_detected=steady_state_detected,
      steady_state_error_c=steady_state_error_c,
      max_overshoot_c=max_overshoot_c,
      settling_time_s=settling_time_s,
      rise_time_s=rise_time_s,
      steady_stddev_c=steady_stddev_c,
      saturation_ratio_pct=saturation_ratio_pct,
      pwm_avg=_safe_mean(pwms),
      pwm_current=pwms[-1],
      errors=errors,
      temps=temps,
      pwms=pwms,
  )


def _build_metric_rows(
    baseline_eval: WindowEvaluation,
    after_eval: WindowEvaluation,
    config: CompareConfig,
) -> list[ControlCompareMetric]:
  rows: list[ControlCompareMetric] = []
  for key, label, unit, better_direction in METRIC_DEFINITIONS:
    baseline_value = baseline_eval.value(key)
    after_value = after_eval.value(key)
    not_comparable_reason = _metric_not_comparable_reason(
        key=key,
        baseline_eval=baseline_eval,
        after_eval=after_eval,
        baseline_value=baseline_value,
        after_value=after_value,
    )
    if not_comparable_reason is not None:
      rows.append(
          ControlCompareMetric(
              key=key,
              label=label,
              unit=unit,
              baseline=_round_or_none(baseline_value, key),
              after=_round_or_none(after_value, key),
              delta=None,
              delta_pct=None,
              better_direction=better_direction,
              status=STATUS_NOT_COMPARABLE,
              status_label="Not comparable",
              not_comparable_reason=not_comparable_reason,
          ),
      )
      continue

    assert baseline_value is not None
    assert after_value is not None
    delta = after_value - baseline_value
    delta_pct = _delta_pct(baseline_value, delta)
    status = _classify_metric_change(key, delta, delta_pct, better_direction, config)
    rows.append(
        ControlCompareMetric(
            key=key,
            label=label,
            unit=unit,
            baseline=_round_or_none(baseline_value, key),
            after=_round_or_none(after_value, key),
            delta=_round_or_none(delta, key),
            delta_pct=_round_or_none(delta_pct, "pct", digits=1),
            better_direction=better_direction,
            status=status,
            status_label=_status_label(status),
            not_comparable_reason=None,
        ),
    )
  return rows


def _metric_not_comparable_reason(
    key: str,
    baseline_eval: WindowEvaluation,
    after_eval: WindowEvaluation,
    baseline_value: float | None,
    after_value: float | None,
) -> str | None:
  if baseline_value is None or after_value is None:
    if key in {"steady_state_error_c", "steady_stddev_c"}:
      return "Steady-state segment not found in both windows."
    if key == "settling_time_s":
      return "Settling condition not reached in one of the windows."
    if key == "rise_time_s":
      return "90% rise condition not reached in one of the windows."
    return "Metric is unavailable in one of the windows."

  if key in {"steady_state_error_c", "steady_stddev_c"}:
    if not baseline_eval.steady_state_detected or not after_eval.steady_state_detected:
      return "Steady-state detection failed in one of the windows."
  return None


def _classify_metric_change(
    key: str,
    delta: float,
    delta_pct: float | None,
    better_direction: str,
    config: CompareConfig,
) -> str:
  if delta_pct is not None and abs(delta_pct) < config.flat_change_pct:
    return STATUS_FLAT
  if delta_pct is None and abs(delta) <= _flat_abs_threshold(key):
    return STATUS_FLAT
  if better_direction == "lower":
    return STATUS_IMPROVED if delta < 0 else STATUS_WORSE
  return STATUS_IMPROVED if delta > 0 else STATUS_WORSE


def _build_conclusion(metrics: list[ControlCompareMetric]) -> ControlCompareConclusion:
  by_key = {metric.key: metric for metric in metrics}
  core_rows = [by_key[key] for key in CORE_METRICS]
  if any(row.status == STATUS_NOT_COMPARABLE for row in core_rows):
    return ControlCompareConclusion(
        status=CONCLUSION_NOT_COMPARABLE,
        label="Not comparable",
        summary="Baseline and after windows are not comparable for core metrics.",
        highlights=[],
    )

  improved = sum(1 for row in core_rows if row.status == STATUS_IMPROVED)
  worse = sum(1 for row in core_rows if row.status == STATUS_WORSE)
  if improved == 3 and worse == 0:
    status = CONCLUSION_MAJOR
    label = "Major improvement"
    summary = "Core control metrics improved together after this adjustment."
  elif improved >= 1 and worse == 0:
    status = CONCLUSION_SLIGHT
    label = "Slight improvement"
    summary = "Core control metrics improved with no significant regression."
  elif worse >= 2:
    status = CONCLUSION_WORSE
    label = "Degraded"
    summary = "Core control metrics regressed after this adjustment."
  elif improved == 0 and worse == 0:
    status = CONCLUSION_NONE
    label = "No significant change"
    summary = "Core control metrics stayed within the flat-change threshold."
  else:
    status = CONCLUSION_NONE
    label = "No significant change"
    summary = "Mixed metric movement did not produce a net improvement."

  highlights = _build_highlights(by_key)
  return ControlCompareConclusion(
      status=status,
      label=label,
      summary=summary,
      highlights=highlights,
  )


def _build_highlights(metric_map: dict[str, ControlCompareMetric]) -> list[str]:
  highlights: list[str] = []
  for key in ("steady_state_error_c", "max_overshoot_c", "settling_time_s"):
    metric = metric_map.get(key)
    if metric is None:
      continue
    if metric.status == STATUS_NOT_COMPARABLE:
      highlights.append(f"{metric.label}: not comparable")
      continue
    if metric.delta is None:
      continue
    trend_symbol = "="
    if metric.status == STATUS_IMPROVED:
      trend_symbol = "down" if metric.better_direction == "lower" else "up"
    elif metric.status == STATUS_WORSE:
      trend_symbol = "up" if metric.better_direction == "lower" else "down"

    if metric.delta_pct is not None:
      direction_text = f"{trend_symbol} {abs(metric.delta_pct):.1f}%"
    else:
      direction_text = f"{trend_symbol} {abs(metric.delta):.2f}{metric.unit}"
    highlights.append(f"{metric.label}: {direction_text}")
  return highlights


def _build_not_comparable(
    scenario: str,
    event_label: str,
    device_id: str,
    event_at: str | None,
    reason: str,
    config: CompareConfig,
    baseline_window: ControlCompareWindow | None = None,
    after_window: ControlCompareWindow | None = None,
) -> ControlEffectComparison:
  anchor = datetime.fromisoformat(event_at) if event_at else datetime.now(UTC)
  return ControlEffectComparison(
      scenario=scenario,
      device_id=device_id,
      event_label=event_label,
      event_at=event_at,
      comparable=False,
      not_comparable_reason=reason,
      baseline_window=baseline_window or _window_stub("Baseline", anchor - timedelta(seconds=WINDOW_DURATION_SECONDS * 2)),
      after_window=after_window or _window_stub("After", anchor),
      thresholds=_thresholds_model(config),
      metrics=[
          ControlCompareMetric(
              key=key,
              label=label,
              unit=unit,
              baseline=None,
              after=None,
              delta=None,
              delta_pct=None,
              better_direction=better_direction,
              status=STATUS_NOT_COMPARABLE,
              status_label="Not comparable",
              not_comparable_reason=reason,
          )
          for key, label, unit, better_direction in METRIC_DEFINITIONS
      ],
      conclusion=ControlCompareConclusion(
          status=CONCLUSION_NOT_COMPARABLE,
          label="Not comparable",
          summary=reason,
          highlights=[],
      ),
      data_source="fastapi_aggregate",
  )


def _window_stub(label: str, started_at: datetime) -> ControlCompareWindow:
  ended_at = started_at + timedelta(seconds=WINDOW_DURATION_SECONDS)
  return ControlCompareWindow(
      label=label,
      started_at=started_at.isoformat(),
      ended_at=ended_at.isoformat(),
      sample_count=0,
      steady_state_detected=False,
  )


def _thresholds_model(config: CompareConfig) -> ControlCompareThresholds:
  return ControlCompareThresholds(
      target_band_c=config.target_band_c,
      temp_rate_threshold_c_per_s=config.temp_rate_threshold_c_per_s,
      steady_hold_seconds=config.steady_hold_seconds,
      flat_change_pct=config.flat_change_pct,
      pwm_saturation_low=config.pwm_saturation_low,
      pwm_saturation_high=config.pwm_saturation_high,
  )


def _flat_abs_threshold(key: str) -> float:
  if key in {"steady_state_error_c", "max_overshoot_c", "steady_stddev_c"}:
    return 0.02
  if key in {"settling_time_s", "rise_time_s"}:
    return 2.0
  if key == "saturation_ratio_pct":
    return 1.0
  return 0.01


def _delta_pct(baseline: float, delta: float) -> float | None:
  if abs(baseline) < 1e-9:
    return None
  return (delta / abs(baseline)) * 100.0


def _status_label(status: str) -> str:
  if status == STATUS_IMPROVED:
    return "Improved"
  if status == STATUS_WORSE:
    return "Worse"
  if status == STATUS_FLAT:
    return "Flat"
  return "Not comparable"


def _round_or_none(value: float | None, key: str, digits: int | None = None) -> float | None:
  if value is None:
    return None
  if digits is not None:
    return round(value, digits)
  if key in {"settling_time_s", "rise_time_s"}:
    return round(value, 1)
  if key == "saturation_ratio_pct":
    return round(value, 1)
  return round(value, 3)


def _safe_mean(values: list[float]) -> float:
  if not values:
    return 0.0
  return sum(values) / len(values)


def _safe_stddev(values: list[float]) -> float:
  if len(values) <= 1:
    return 0.0
  mean = _safe_mean(values)
  variance = sum((item - mean) ** 2 for item in values) / len(values)
  return math.sqrt(variance)


def _clamp(value: float, minimum: float, maximum: float) -> float:
  return max(minimum, min(maximum, value))


def _is_ai_adopted(ack: AckRecord, recommendation: AIRecommendation) -> bool:
  if recommendation.suggested_kp is None or recommendation.suggested_ki is None or recommendation.suggested_kd is None:
    return False
  if recommendation.suggested_target_temp_c is None:
    return False
  tolerance = 1e-3
  return (
      abs(ack.kp - recommendation.suggested_kp) <= tolerance
      and abs(ack.ki - recommendation.suggested_ki) <= tolerance
      and abs(ack.kd - recommendation.suggested_kd) <= tolerance
      and abs(ack.target_temp_c - recommendation.suggested_target_temp_c) <= tolerance
  )
