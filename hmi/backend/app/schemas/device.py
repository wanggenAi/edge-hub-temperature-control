from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DeviceBase(BaseModel):
    code: str
    name: str
    line: str
    location: str
    status: str = "active"
    target_temp: float = 37.0


class DeviceCreate(DeviceBase):
    current_temp: float = 25.0
    pwm_output: float = 0.0
    is_alarm: bool = False
    is_online: bool = True


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    line: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    target_temp: Optional[float] = None
    current_temp: Optional[float] = None
    pwm_output: Optional[float] = None
    is_alarm: Optional[bool] = None
    is_online: Optional[bool] = None


class DeviceOut(DeviceBase):
    id: int
    current_temp: float
    pwm_output: float
    is_alarm: bool
    is_online: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeviceListResponse(BaseModel):
    items: list[DeviceOut]
    total: int
    page: int
    page_size: int


class MetricOut(BaseModel):
    id: int
    timestamp: datetime
    current_temp: float
    target_temp: float
    error: float
    pwm_output: float
    status: str
    in_spec: bool
    is_alarm: bool

    class Config:
        from_attributes = True


class MetricWindowStatsOut(BaseModel):
    samples: int
    in_band_ratio: float
    total_stable_sec: int
    longest_stable_sec: int
    since_last_stable_sec: Optional[int] = None
    has_stable_window: bool


class ControlEvalOut(BaseModel):
    current_temp: float
    target_temp: float
    pwm_output: float
    error: float
    in_band: bool
    steady: bool
    steady_window_samples: int
    steady_in_band_samples: int
    observed_settling_sec: Optional[float] = None
    overshoot_pct: float
    saturation_ratio: float
    saturation_risk: str
    tune_advice: str
    result: str


class ParameterOut(BaseModel):
    id: int
    device_id: int
    kp: float
    ki: float
    kd: float
    control_mode: str
    target_band: float
    overshoot_limit_pct: float
    saturation_warn_ratio: float
    saturation_high_ratio: float
    pwm_saturation_threshold: float
    steady_window_samples: int
    sampling_period_ms: int
    upload_period_s: int
    updated_at: datetime
    updated_by: str

    class Config:
        from_attributes = True


class ParameterUpdate(BaseModel):
    target_temp: Optional[float] = None
    kp: Optional[float] = None
    ki: Optional[float] = None
    kd: Optional[float] = None
    control_mode: Optional[str] = None
    target_band: Optional[float] = None
    overshoot_limit_pct: Optional[float] = None
    saturation_warn_ratio: Optional[float] = None
    saturation_high_ratio: Optional[float] = None
    pwm_saturation_threshold: Optional[float] = None
    steady_window_samples: Optional[int] = None
    sampling_period_ms: Optional[int] = None
    upload_period_s: Optional[int] = None


class AlarmOut(BaseModel):
    id: int
    level: str
    title: str
    message: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AIRecommendationOut(BaseModel):
    id: int
    reason: str
    suggestion: str
    confidence: float
    risk: str
    last_run_at: datetime

    class Config:
        from_attributes = True
