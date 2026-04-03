from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DataSource = Literal["realtime_link", "historical_store", "fastapi_aggregate", "ai_reserved"]


class MetricCard(BaseModel):
  key: str
  label: str
  value: str
  unit: str | None = None
  trend_hint: str | None = None
  data_source: DataSource


class QuickAction(BaseModel):
  title: str
  route: str
  description: str


class ArchitectureNode(BaseModel):
  name: str
  role: str
  status: str


class ParameterState(BaseModel):
  target_temp_c: float
  kp: float
  ki: float
  kd: float
  control_period_ms: int
  control_mode: str
  updated_at: str
  data_source: DataSource


class AckRecord(BaseModel):
  ack_type: str
  success: bool
  applied_immediately: bool
  has_pending_params: bool
  target_temp_c: float
  kp: float
  ki: float
  kd: float
  control_period_ms: int
  control_mode: str
  reason: str
  uptime_ms: int
  received_at: str
  data_source: DataSource


class RunSummary(BaseModel):
  run_id: str
  window_start: str
  window_end: str
  duration_ms: int
  sample_count: int
  sensor_temp_avg: float
  abs_error_max: float
  pwm_duty_min: int
  pwm_duty_max: int
  flush_reason: str
  data_source: DataSource


class OverviewResponse(BaseModel):
  hero_title: str
  hero_description: str
  live_cards: list[MetricCard]
  current_parameters: ParameterState
  recent_ack: AckRecord
  latest_summary: RunSummary
  architecture: list[ArchitectureNode]
  quick_actions: list[QuickAction]


class TelemetrySnapshot(BaseModel):
  device_id: str
  collected_at: str
  uptime_ms: int
  target_temp_c: float
  sim_temp_c: float
  sensor_temp_c: float
  error_c: float
  integral_error: float
  control_output: float
  pwm_duty: int
  pwm_norm: float
  control_period_ms: int
  control_mode: str
  controller_version: str
  kp: float
  ki: float
  kd: float
  system_state: str
  has_pending_params: bool
  pending_params_age_ms: int
  data_source: DataSource


class TimePoint(BaseModel):
  ts: str
  value: float


class Series(BaseModel):
  name: str
  color: str
  unit: str
  data_source: DataSource
  points: list[TimePoint]


class RealtimeSeriesResponse(BaseModel):
  window_label: str
  series: list[Series]


class HistoryResponse(BaseModel):
  range_label: str
  kpis: list[MetricCard]
  series: list[Series]
  runs: list[RunSummary]


class ParameterCommandRequest(BaseModel):
  target_temp_c: float = Field(ge=20.0, le=60.0)
  kp: float = Field(ge=0.0, le=500.0)
  ki: float = Field(ge=0.0, le=200.0)
  kd: float = Field(ge=0.0, le=50.0)
  control_period_ms: int = Field(ge=100, le=5000)
  control_mode: str
  apply_immediately: bool = True


class ParameterPageResponse(BaseModel):
  current: ParameterState
  latest_ack: AckRecord
  recent_acks: list[AckRecord]


class AIRecommendation(BaseModel):
  title: str
  category: str
  summary: str
  reason: str
  confidence: float
  status: str
  suggested_target_temp_c: float | None = None
  suggested_kp: float | None = None
  suggested_ki: float | None = None
  suggested_kd: float | None = None
  data_source: DataSource
