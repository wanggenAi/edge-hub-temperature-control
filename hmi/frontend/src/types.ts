export type Role = string;
export type DataSource = string;

export interface PermissionDefinition {
  key: string;
  label: string;
  description: string;
}

export interface RoleDefinition {
  key: string;
  name: string;
  permissions: string[];
}

export interface UserPublic {
  username: string;
  display_name: string;
  role: Role;
  permissions: string[];
}

export interface ManagedUser extends UserPublic {
  enabled: boolean;
  assigned_device_ids: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export interface DeviceSummary {
  device_id: string;
  name: string;
  location: string;
  status: string;
  target_temp_c: number;
  control_mode: string;
  updated_at: string;
}

export interface DevicePageResponse {
  items: DeviceSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface DeviceStatsResponse {
  total: number;
  running: number;
  idle: number;
  offline: number;
}

export interface DeviceUpsertRequest {
  device_id: string;
  name: string;
  location: string;
  status: string;
  target_temp_c: number;
  control_mode: string;
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
  device_id: string;
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
  device_id: string;
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

export interface ControlCompareThresholds {
  target_band_c: number;
  temp_rate_threshold_c_per_s: number;
  steady_hold_seconds: number;
  flat_change_pct: number;
  pwm_saturation_low: number;
  pwm_saturation_high: number;
}

export interface ControlGoalsConfig extends ControlCompareThresholds {
  realtime_steady_error_axis_c: number;
}

export interface ControlCompareWindow {
  label: string;
  started_at: string;
  ended_at: string;
  sample_count: number;
  steady_state_detected: boolean;
}

export type ControlCompareMetricStatus = "improved" | "worse" | "flat" | "not_comparable";

export interface ControlCompareMetric {
  key: string;
  label: string;
  unit: string;
  baseline?: number | null;
  after?: number | null;
  delta?: number | null;
  delta_pct?: number | null;
  better_direction: string;
  status: ControlCompareMetricStatus;
  status_label: string;
  not_comparable_reason?: string | null;
}

export interface ControlCompareConclusion {
  status: "major_improvement" | "slight_improvement" | "no_significant_change" | "degraded" | "not_comparable";
  label: string;
  summary: string;
  highlights: string[];
}

export interface ControlEffectComparison {
  scenario: string;
  device_id: string;
  event_label: string;
  event_at?: string | null;
  comparable: boolean;
  not_comparable_reason?: string | null;
  baseline_window: ControlCompareWindow;
  after_window: ControlCompareWindow;
  thresholds: ControlCompareThresholds;
  metrics: ControlCompareMetric[];
  conclusion: ControlCompareConclusion;
  data_source: DataSource;
}

export interface RunSummary {
  device_id: string;
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
  selected_device: DeviceSummary;
  telemetry_collected_at: string;
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
  device_id: string;
  window_label: string;
  series: Series[];
  steady_error_series: Series;
  goals: ControlGoalsConfig;
}

export interface HistoryResponse {
  device_id: string;
  range_label: string;
  kpis: MetricCard[];
  series: Series[];
  runs: RunSummary[];
}

export interface ParameterPageResponse {
  device_id: string;
  current: ParameterState;
  latest_ack: AckRecord;
  recent_acks: AckRecord[];
  latest_tuning_compare: ControlEffectComparison;
}

export interface ParameterCommandRequest {
  device_id?: string | null;
  target_temp_c: number;
  kp: number;
  ki: number;
  kd: number;
  control_period_ms: number;
  control_mode: string;
  apply_immediately: boolean;
}

export interface AIRecommendation {
  device_id: string;
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

export interface AIPageResponse {
  device_id: string;
  recommendations: AIRecommendation[];
  adoption_compare: ControlEffectComparison;
}

export interface SystemAccessResponse {
  users: ManagedUser[];
  roles: RoleDefinition[];
  permissions: PermissionDefinition[];
  devices: DeviceSummary[];
}

export interface UserUpsertRequest {
  username: string;
  display_name: string;
  role: string;
  password?: string;
  enabled: boolean;
  device_ids?: string[] | null;
}

export interface RoleUpsertRequest {
  key: string;
  name: string;
  permissions: string[];
}

export interface DeleteResult {
  deleted: boolean;
  resource: string;
  key: string;
}
