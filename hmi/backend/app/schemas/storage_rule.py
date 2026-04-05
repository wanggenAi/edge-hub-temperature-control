from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ScopeType = Literal["global", "device"]
RawMode = Literal["full", "relaxed", "strict", "disabled"]


class StorageRuleBase(BaseModel):
    scope_type: ScopeType = "global"
    scope_value: str = "*"
    raw_mode: RawMode = "full"
    summary_enabled: bool = True
    summary_min_samples: int = Field(default=3, ge=1)
    heartbeat_interval_ms: int = Field(default=30000, ge=0)
    target_temp_deadband: float = Field(default=0.05, ge=0)
    sim_temp_deadband: float = Field(default=0.05, ge=0)
    sensor_temp_deadband: float = Field(default=0.05, ge=0)
    error_deadband: float = Field(default=0.02, ge=0)
    integral_error_deadband: float = Field(default=1.0, ge=0)
    control_output_deadband: float = Field(default=1.0, ge=0)
    pwm_duty_deadband: float = Field(default=1.0, ge=0)
    pwm_norm_deadband: float = Field(default=0.01, ge=0)
    parameter_deadband: float = Field(default=0.01, ge=0)
    enabled: bool = True


class StorageRuleCreateIn(StorageRuleBase):
    pass


class StorageRuleUpdateIn(BaseModel):
    scope_type: ScopeType
    scope_value: str
    raw_mode: RawMode
    summary_enabled: bool
    summary_min_samples: int = Field(ge=1)
    heartbeat_interval_ms: int = Field(ge=0)
    target_temp_deadband: float = Field(ge=0)
    sim_temp_deadband: float = Field(ge=0)
    sensor_temp_deadband: float = Field(ge=0)
    error_deadband: float = Field(ge=0)
    integral_error_deadband: float = Field(ge=0)
    control_output_deadband: float = Field(ge=0)
    pwm_duty_deadband: float = Field(ge=0)
    pwm_norm_deadband: float = Field(ge=0)
    parameter_deadband: float = Field(ge=0)
    enabled: bool


class StorageRuleItem(StorageRuleBase):
    id: int
    updated_at: datetime
    updated_by: str


class StorageRuleListResponse(BaseModel):
    items: list[StorageRuleItem]
    total: int


class StorageRuleMutationResponse(BaseModel):
    item: StorageRuleItem


class StorageRuleDeleteResponse(BaseModel):
    ok: bool = True
