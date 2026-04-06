from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.services.ai.schemas import (
    PIDParams,
    PreviewCurvePoint,
    PreviewImprovement,
    PreviewMetrics,
    RecommendationPreviewOutput,
)


# Centralized preview model defaults for easy tuning in future iterations.
PREVIEW_DEFAULT_HORIZON_SEC = 1800
PREVIEW_DEFAULT_STEP_SEC = 1
PREVIEW_DEFAULT_AMBIENT_TEMP = 25.0
PREVIEW_DEFAULT_HEATING_GAIN = 0.02
PREVIEW_DEFAULT_COOLING_COEFF = 0.015
PREVIEW_DEFAULT_MAX_DUTY = 100.0
PREVIEW_DEFAULT_DERIVATIVE_FILTER_ALPHA = 0.2
PREVIEW_MAX_POINTS = 3600


@dataclass
class PreviewSimulationConfig:
    horizon_sec: int = PREVIEW_DEFAULT_HORIZON_SEC
    step_sec: int = PREVIEW_DEFAULT_STEP_SEC
    ambient_temp: float = PREVIEW_DEFAULT_AMBIENT_TEMP
    heating_gain: float = PREVIEW_DEFAULT_HEATING_GAIN
    cooling_coeff: float = PREVIEW_DEFAULT_COOLING_COEFF
    target_band: float = 0.5
    pwm_saturation_threshold: float = 85.0
    max_duty: float = PREVIEW_DEFAULT_MAX_DUTY
    integral_min: Optional[float] = None
    integral_max: Optional[float] = None
    derivative_filter_alpha: float = PREVIEW_DEFAULT_DERIVATIVE_FILTER_ALPHA
    control_mode: str = "pid_control"
    integral_abs_limit: float = 500.0

    def resolved_integral_min(self) -> float:
        if self.integral_min is not None:
            return float(self.integral_min)
        return -abs(float(self.integral_abs_limit))

    def resolved_integral_max(self) -> float:
        if self.integral_max is not None:
            return float(self.integral_max)
        return abs(float(self.integral_abs_limit))


@dataclass
class PreviewPidUpdateResult:
    error: float
    derivative_error: float
    d_term: float
    integral_error: float
    raw_output: float
    control_output: float
    pwm_output: float
    saturation_state: str


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


class PreviewPidController:
    """PID core aligned with device-side PiController update sequence."""

    def __init__(self) -> None:
        self.integral_error = 0.0
        self.previous_error = 0.0
        self.previous_error_initialized = False
        self.filtered_derivative = 0.0

    def reset_integral(self) -> None:
        self.integral_error = 0.0
        self.previous_error = 0.0
        self.previous_error_initialized = False
        self.filtered_derivative = 0.0

    def update(
        self,
        *,
        target_temp: float,
        measured_temp: float,
        dt_s: float,
        params: PIDParams,
        config: PreviewSimulationConfig,
    ) -> PreviewPidUpdateResult:
        # Match device behavior:
        # - p_control disables integral/derivative gains.
        # - pid_control / pi_control use runtime gains as provided.
        mode = (config.control_mode or "pid_control").strip().lower()
        active_ki = 0.0 if mode == "p_control" else float(params.ki)
        active_kd = 0.0 if mode == "p_control" else float(params.kd)
        kp = float(params.kp)

        error = float(target_temp) - float(measured_temp)
        safe_dt_s = float(dt_s) if float(dt_s) > 0.0 else 0.0

        derivative_error = 0.0
        if self.previous_error_initialized and safe_dt_s > 0.0:
            raw_derivative = (error - self.previous_error) / safe_dt_s
            alpha = _clamp(float(config.derivative_filter_alpha), 0.0, 1.0)
            self.filtered_derivative = alpha * raw_derivative + (1.0 - alpha) * self.filtered_derivative
            derivative_error = self.filtered_derivative
        else:
            self.filtered_derivative = 0.0
            derivative_error = 0.0

        d_term = active_kd * derivative_error
        integral_min = config.resolved_integral_min()
        integral_max = config.resolved_integral_max()
        candidate_integral = _clamp(self.integral_error + error * safe_dt_s, integral_min, integral_max)

        max_duty = float(config.max_duty)
        candidate_output = error * kp + candidate_integral * active_ki + d_term
        saturating_high = candidate_output > max_duty and error > 0.0
        saturating_low = candidate_output < 0.0 and error < 0.0
        if not (saturating_high or saturating_low):
            self.integral_error = candidate_integral

        self.previous_error = error
        self.previous_error_initialized = True

        raw_output = error * kp + self.integral_error * active_ki + d_term
        if raw_output < 0.0:
            saturation_state = "low"
        elif raw_output > max_duty:
            saturation_state = "high"
        else:
            saturation_state = "none"

        control_output = _clamp(raw_output, 0.0, max_duty)
        pwm_output = control_output
        return PreviewPidUpdateResult(
            error=error,
            derivative_error=derivative_error,
            d_term=d_term,
            integral_error=self.integral_error,
            raw_output=raw_output,
            control_output=control_output,
            pwm_output=pwm_output,
            saturation_state=saturation_state,
        )


class RecommendationPreviewSimulator:
    def run(
        self,
        *,
        current_temp: float,
        target_temp: float,
        baseline_params: PIDParams,
        recommended_params: PIDParams,
        config: PreviewSimulationConfig,
    ) -> RecommendationPreviewOutput:
        baseline_curve = self._simulate_curve(
            current_temp=current_temp,
            target_temp=target_temp,
            params=baseline_params,
            config=config,
        )
        recommended_curve = self._simulate_curve(
            current_temp=current_temp,
            target_temp=target_temp,
            params=recommended_params,
            config=config,
        )

        baseline_metrics = self._calc_metrics(
            curve=baseline_curve,
            target_temp=target_temp,
            target_band=config.target_band,
            pwm_saturation_threshold=config.pwm_saturation_threshold,
        )
        recommended_metrics = self._calc_metrics(
            curve=recommended_curve,
            target_temp=target_temp,
            target_band=config.target_band,
            pwm_saturation_threshold=config.pwm_saturation_threshold,
        )

        # Delta is oriented as "improvement" (positive is better):
        # - higher is better: in_band_ratio
        # - lower is better: overshoot/settling/swing/MAE/saturation
        improvement = PreviewImprovement(
            in_band_ratio_delta=round(recommended_metrics.in_band_ratio - baseline_metrics.in_band_ratio, 6),
            overshoot_c_delta=round(baseline_metrics.overshoot_c - recommended_metrics.overshoot_c, 6),
            settling_sec_delta=round(self._safe_delta(baseline_metrics.settling_sec, recommended_metrics.settling_sec), 6),
            temp_swing_delta=round(baseline_metrics.temp_swing - recommended_metrics.temp_swing, 6),
            mean_abs_error_delta=round(baseline_metrics.mean_abs_error - recommended_metrics.mean_abs_error, 6),
            saturation_ratio_delta=round(baseline_metrics.saturation_ratio - recommended_metrics.saturation_ratio, 6),
        )

        return RecommendationPreviewOutput(
            baseline_params=baseline_params,
            recommended_params=recommended_params,
            baseline_curve=baseline_curve,
            recommended_curve=recommended_curve,
            baseline_metrics=baseline_metrics,
            recommended_metrics=recommended_metrics,
            improvement=improvement,
            generated_at=datetime.utcnow(),
        )

    def _simulate_curve(
        self,
        *,
        current_temp: float,
        target_temp: float,
        params: PIDParams,
        config: PreviewSimulationConfig,
    ) -> list[PreviewCurvePoint]:
        step_sec = max(1, int(config.step_sec))
        horizon_sec = max(step_sec, int(config.horizon_sec))
        total_steps = max(1, min(PREVIEW_MAX_POINTS, horizon_sec // step_sec))

        temp = float(current_temp)
        controller = PreviewPidController()
        points: list[PreviewCurvePoint] = []

        for idx in range(total_steps):
            time_s = idx * step_sec
            pid = controller.update(
                target_temp=float(target_temp),
                measured_temp=temp,
                dt_s=float(step_sec),
                params=params,
                config=config,
            )

            # First-order thermal inertia model:
            # dT/dt = heating_gain * u - cooling_coeff * (T - Tamb)
            d_temp_dt = config.heating_gain * pid.control_output - config.cooling_coeff * (temp - config.ambient_temp)
            temp = temp + d_temp_dt * float(step_sec)

            points.append(
                PreviewCurvePoint(
                    time_s=time_s,
                    temp=round(temp, 6),
                    target_temp=round(target_temp, 6),
                    pwm_output=round(pid.pwm_output, 6),
                    error=round(pid.error, 6),
                )
            )

        return points

    def _calc_metrics(
        self,
        *,
        curve: list[PreviewCurvePoint],
        target_temp: float,
        target_band: float,
        pwm_saturation_threshold: float,
    ) -> PreviewMetrics:
        if not curve:
            return PreviewMetrics(
                in_band_ratio=0.0,
                overshoot_c=0.0,
                settling_sec=None,
                temp_swing=0.0,
                mean_abs_error=0.0,
                saturation_ratio=0.0,
            )

        temps = [p.temp for p in curve]
        errors = [abs(p.error) for p in curve]
        in_band = [abs(p.error) <= target_band for p in curve]
        sat = [p.pwm_output >= pwm_saturation_threshold for p in curve]

        in_band_ratio = sum(1 for x in in_band if x) / len(in_band)
        overshoot_c = max(0.0, max(t - target_temp for t in temps))
        temp_swing = max(temps) - min(temps)
        mean_abs_error = sum(errors) / len(errors)
        saturation_ratio = sum(1 for x in sat if x) / len(sat)
        settling_sec = self._calc_settling_sec(curve=curve, target_band=target_band)

        return PreviewMetrics(
            in_band_ratio=round(in_band_ratio, 6),
            overshoot_c=round(overshoot_c, 6),
            settling_sec=None if settling_sec is None else round(settling_sec, 6),
            temp_swing=round(temp_swing, 6),
            mean_abs_error=round(mean_abs_error, 6),
            saturation_ratio=round(saturation_ratio, 6),
        )

    def _calc_settling_sec(self, *, curve: list[PreviewCurvePoint], target_band: float) -> Optional[float]:
        # Find the earliest point after which all future samples stay in band.
        all_future_in_band = True
        settle_time: Optional[float] = None
        for idx in range(len(curve) - 1, -1, -1):
            in_band = abs(curve[idx].error) <= target_band
            all_future_in_band = all_future_in_band and in_band
            if all_future_in_band:
                settle_time = float(curve[idx].time_s)
        return settle_time

    def _safe_delta(self, baseline: Optional[float], recommended: Optional[float]) -> float:
        # If either side never settles, treat missing as worst case horizon.
        b = float(baseline) if baseline is not None else float(PREVIEW_DEFAULT_HORIZON_SEC)
        r = float(recommended) if recommended is not None else float(PREVIEW_DEFAULT_HORIZON_SEC)
        return b - r
