from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field

from app.services.ai.enums import ExpectedEffect, ProblemType, RiskLevel


class DeviceIdentity(BaseModel):
    id: int
    code: str
    name: str


class CurrentState(BaseModel):
    current_temp: float
    target_temp: float
    pwm_output: float


class PIDParams(BaseModel):
    kp: float
    ki: float
    kd: float


class HistoryPoint(BaseModel):
    ts_ms: int
    current_temp: float
    target_temp: float
    error: float
    pwm_output: float


class HistoryWindow(BaseModel):
    start_ms: int
    end_ms: int
    points: list[HistoryPoint] = Field(default_factory=list)


class FeatureSet(BaseModel):
    mean_error: float
    mean_abs_error: float
    error_std: float
    temp_swing: float
    pwm_mean: float
    pwm_max: float
    zero_crossings: int
    in_band_ratio: float
    overshoot_pct: float
    settling_sec: Optional[float] = None
    saturation_ratio: float


class RecommendationGenerateInput(BaseModel):
    device: DeviceIdentity
    current_state: CurrentState
    current_params: PIDParams
    history_window: HistoryWindow
    target_band: float = 0.5
    steady_window_samples: int = 12
    overshoot_limit_pct: float = 3.0
    pwm_saturation_threshold: float = 85.0
    saturation_warn_ratio: float = 0.3
    saturation_high_ratio: float = 0.6


class RecommendationGenerateOutput(BaseModel):
    problem_type: ProblemType
    confidence: float
    risk_level: RiskLevel
    requires_confirmation: bool
    current_params: PIDParams
    recommended_params: PIDParams
    delta: PIDParams
    expected_effect: ExpectedEffect
    evidence: dict[str, Union[float, int, str, bool, None]]
    generated_at: datetime
