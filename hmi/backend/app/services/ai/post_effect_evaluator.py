from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.services.ai.schemas import (
    PostEffectComparison,
    PostEffectMetrics,
    PreviewMetrics,
)


@dataclass
class ObservedTelemetryPoint:
    ts_ms: int
    temp: float
    target_temp: float
    error: float
    pwm_output: float
    saturation_state: Optional[str] = None


class PostEffectEvaluator:
    """Evaluate real post-apply telemetry impact (different from preview simulation)."""

    def calc_metrics(
        self,
        *,
        points: list[ObservedTelemetryPoint],
        target_band: float,
        pwm_saturation_threshold: float,
    ) -> Optional[PreviewMetrics]:
        if len(points) < 2:
            return None

        temps = [float(p.temp) for p in points]
        errors = [float(p.error) for p in points]
        abs_errors = [abs(v) for v in errors]

        in_band_ratio = sum(1 for v in abs_errors if v <= target_band) / len(abs_errors)
        overshoot_c = max(0.0, max(float(p.temp) - float(p.target_temp) for p in points))
        mean_abs_error = sum(abs_errors) / len(abs_errors)
        temp_swing = max(temps) - min(temps)

        sat_by_state = [str(p.saturation_state or "").strip().lower() for p in points]
        if any(v for v in sat_by_state):
            saturation_ratio = sum(1 for v in sat_by_state if v not in {"", "none", "normal"}) / len(points)
        else:
            saturation_ratio = sum(1 for p in points if float(p.pwm_output) >= pwm_saturation_threshold) / len(points)

        settling_sec = self._calc_settling_sec(points=points, target_band=target_band)
        return PreviewMetrics(
            in_band_ratio=round(in_band_ratio, 6),
            overshoot_c=round(overshoot_c, 6),
            settling_sec=None if settling_sec is None else round(settling_sec, 6),
            mean_abs_error=round(mean_abs_error, 6),
            saturation_ratio=round(saturation_ratio, 6),
            temp_swing=round(temp_swing, 6),
        )

    def build_actual_summary(
        self,
        *,
        points: list[ObservedTelemetryPoint],
        metrics: PreviewMetrics,
    ) -> PostEffectMetrics:
        start_dt = datetime.utcfromtimestamp(points[0].ts_ms / 1000.0)
        end_dt = datetime.utcfromtimestamp(points[-1].ts_ms / 1000.0)
        return PostEffectMetrics(
            observed_window_start=start_dt,
            observed_window_end=end_dt,
            point_count=len(points),
            in_band_ratio_after=metrics.in_band_ratio,
            overshoot_c_after=metrics.overshoot_c,
            settling_sec_after=metrics.settling_sec,
            mean_abs_error_after=metrics.mean_abs_error,
            saturation_ratio_after=metrics.saturation_ratio,
            temp_swing_after=metrics.temp_swing,
        )

    def compare(self, *, reference: Optional[PreviewMetrics], actual: PreviewMetrics) -> PostEffectComparison:
        if reference is None:
            return PostEffectComparison()
        return PostEffectComparison(
            # Positive means improvement:
            # higher in-band is better, all other metrics lower is better.
            in_band_ratio_delta=round(actual.in_band_ratio - reference.in_band_ratio, 6),
            overshoot_c_delta=round(reference.overshoot_c - actual.overshoot_c, 6),
            settling_sec_delta=self._delta_optional(reference.settling_sec, actual.settling_sec),
            mean_abs_error_delta=round(reference.mean_abs_error - actual.mean_abs_error, 6),
            saturation_ratio_delta=round(reference.saturation_ratio - actual.saturation_ratio, 6),
            temp_swing_delta=round(reference.temp_swing - actual.temp_swing, 6),
        )

    def _calc_settling_sec(self, *, points: list[ObservedTelemetryPoint], target_band: float) -> Optional[float]:
        all_future_in_band = True
        settle_idx: Optional[int] = None
        for idx in range(len(points) - 1, -1, -1):
            in_band = abs(float(points[idx].error)) <= target_band
            all_future_in_band = all_future_in_band and in_band
            if all_future_in_band:
                settle_idx = idx
        if settle_idx is None:
            return None
        return max(0.0, float(points[settle_idx].ts_ms - points[0].ts_ms) / 1000.0)

    def _delta_optional(self, baseline: Optional[float], actual: Optional[float]) -> Optional[float]:
        if baseline is None or actual is None:
            return None
        return round(float(baseline) - float(actual), 6)
