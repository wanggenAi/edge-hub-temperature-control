export type Role = "viewer" | "operator";

export type DataSource =
  | "realtime_link"
  | "historical_store"
  | "fastapi_aggregate"
  | "ai_reserved";

export interface UserPublic {
  username: string;
  display_name: string;
  role: Role;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export interface MetricCard {
  key: string;
  label: string;
  value: string;
  unit?: string | null;
  trend_hint?: string | null;
  data_source: DataSource;
}

export interface ParameterState {
  target_temp_c: number;
  kp: number;
  ki: number;
  kd: number;
  control_period_ms: number;
  control_mode: string;
  updated_at: string;
  data_source: DataSource;
}

export interface AckRecord {
  ack_type: string;
  success: boolean;
  applied_immediately: boolean;
  has_pending_params: boolean;
  target_temp_c: number;
  kp: number;
  ki: number;
  kd: number;
  control_period_ms: number;
  control_mode: string;
  reason: string;
  uptime_ms: number;
  received_at: string;
  data_source: DataSource;
}

export interface RunSummary {
  run_id: string;
  window_start: string;
  window_end: string;
  duration_ms: number;
  sample_count: number;
  sensor_temp_avg: number;
  abs_error_max: number;
  pwm_duty_min: number;
  pwm_duty_max: number;
  flush_reason: string;
  data_source: DataSource;
}

export interface OverviewResponse {
  hero_title: string;
  hero_description: string;
  live_cards: MetricCard[];
  current_parameters: ParameterState;
  recent_ack: AckRecord;
  latest_summary: RunSummary;
  architecture: Array<{ name: string; role: string; status: string }>;
  quick_actions: Array<{ title: string; route: string; description: string }>;
}

export interface TelemetrySnapshot {
  device_id: string;
  collected_at: string;
  uptime_ms: number;
  target_temp_c: number;
  sim_temp_c: number;
  sensor_temp_c: number;
  error_c: number;
  integral_error: number;
  control_output: number;
  pwm_duty: number;
  pwm_norm: number;
  control_period_ms: number;
  control_mode: string;
  controller_version: string;
  kp: number;
  ki: number;
  kd: number;
  system_state: string;
  has_pending_params: boolean;
  pending_params_age_ms: number;
  data_source: DataSource;
}

export interface TimePoint {
  ts: string;
  value: number;
}

export interface Series {
  name: string;
  color: string;
  unit: string;
  data_source: DataSource;
  points: TimePoint[];
}

export interface RealtimeSeriesResponse {
  window_label: string;
  series: Series[];
}

export interface HistoryResponse {
  range_label: string;
  kpis: MetricCard[];
  series: Series[];
  runs: RunSummary[];
}

export interface ParameterPageResponse {
  current: ParameterState;
  latest_ack: AckRecord;
  recent_acks: AckRecord[];
}

export interface ParameterCommandRequest {
  target_temp_c: number;
  kp: number;
  ki: number;
  kd: number;
  control_period_ms: number;
  control_mode: string;
  apply_immediately: boolean;
}

export interface AIRecommendation {
  title: string;
  category: string;
  summary: string;
  reason: string;
  confidence: number;
  status: string;
  suggested_target_temp_c?: number | null;
  suggested_kp?: number | null;
  suggested_ki?: number | null;
  suggested_kd?: number | null;
  data_source: DataSource;
}
