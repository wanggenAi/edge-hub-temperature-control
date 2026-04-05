from __future__ import annotations

from statistics import mean, pstdev
from typing import Optional

from app.services.ai.schemas import FeatureSet, RecommendationGenerateInput


def _calc_zero_crossings(errors: list[float]) -> int:
    crossings = 0
    prev_sign = 0
    for value in errors:
        sign = 1 if value > 0 else (-1 if value < 0 else 0)
        if sign == 0:
            continue
        if prev_sign != 0 and sign != prev_sign:
            crossings += 1
        prev_sign = sign
    return crossings


def _calc_settling_sec(
    ts_ms: list[int],
    errors: list[float],
    target_band: float,
    steady_window_samples: int,
) -> Optional[float]:
    if len(errors) < max(2, steady_window_samples):
        return None
    for i in range(0, len(errors) - steady_window_samples + 1):
        window = errors[i : i + steady_window_samples]
        if all(abs(err) <= target_band for err in window):
            return max(0.0, (ts_ms[i] - ts_ms[0]) / 1000.0)
    return None


def extract_features(payload: RecommendationGenerateInput) -> FeatureSet:
    points = payload.history_window.points
    if not points:
        return FeatureSet(
            mean_error=0.0,
            mean_abs_error=0.0,
            error_std=0.0,
            temp_swing=0.0,
            pwm_mean=payload.current_state.pwm_output,
            pwm_max=payload.current_state.pwm_output,
            zero_crossings=0,
            in_band_ratio=0.0,
            overshoot_pct=0.0,
            settling_sec=None,
            saturation_ratio=0.0,
        )

    errors = [float(p.error) for p in points]
    temps = [float(p.current_temp) for p in points]
    targets = [float(p.target_temp) for p in points]
    pwms = [float(p.pwm_output) for p in points]
    ts_ms = [int(p.ts_ms) for p in points]

    in_band_ratio = sum(1 for err in errors if abs(err) <= payload.target_band) / len(errors)
    saturation_ratio = sum(1 for pwm in pwms if pwm >= payload.pwm_saturation_threshold) / len(pwms)

    overshoot_pct = 0.0
    for temp, target in zip(temps, targets):
        denom = max(abs(target), 1e-3)
        overshoot_pct = max(overshoot_pct, max(0.0, ((temp - target) / denom) * 100.0))

    return FeatureSet(
        mean_error=mean(errors),
        mean_abs_error=mean([abs(err) for err in errors]),
        error_std=pstdev(errors) if len(errors) > 1 else 0.0,
        temp_swing=max(temps) - min(temps),
        pwm_mean=mean(pwms),
        pwm_max=max(pwms),
        zero_crossings=_calc_zero_crossings(errors),
        in_band_ratio=in_band_ratio,
        overshoot_pct=overshoot_pct,
        settling_sec=_calc_settling_sec(ts_ms, errors, payload.target_band, payload.steady_window_samples),
        saturation_ratio=saturation_ratio,
    )
