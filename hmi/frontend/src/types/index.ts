export type Role = "admin" | "operator" | "viewer";

export interface Me {
  id: number;
  username: string;
  email: string;
  roles: Role[];
}

export interface Device {
  id: number;
  code: string;
  name: string;
  line: string;
  location: string;
  status: string;
  current_temp: number;
  target_temp: number;
  pwm_output: number;
  is_alarm: boolean;
  is_online: boolean;
  created_at: string;
  updated_at: string;
}

export interface Metric {
  id: number;
  timestamp: string;
  current_temp: number;
  target_temp: number;
  error: number;
  pwm_output: number;
  status: string;
  in_spec: boolean;
  is_alarm: boolean;
}

export interface MetricWindowStats {
  samples: number;
  in_band_ratio: number;
  total_stable_sec: number;
  longest_stable_sec: number;
  since_last_stable_sec?: number | null;
  has_stable_window: boolean;
}

export interface ControlEvaluation {
  current_temp: number;
  target_temp: number;
  pwm_output: number;
  error: number;
  in_band: boolean;
  steady: boolean;
  steady_window_samples: number;
  steady_in_band_samples: number;
  observed_settling_sec?: number | null;
  overshoot_pct: number;
  saturation_ratio: number;
  saturation_risk: "Low" | "Medium" | "High" | string;
  tune_advice: "Keep" | "Tune" | string;
  result: "On Target" | "Critical" | "Not Met" | string;
}

export interface Parameter {
  id: number;
  device_id: number;
  kp: number;
  ki: number;
  kd: number;
  control_mode: string;
  target_band: number;
  overshoot_limit_pct: number;
  saturation_warn_ratio: number;
  saturation_high_ratio: number;
  pwm_saturation_threshold: number;
  steady_window_samples: number;
  sampling_period_ms: number;
  upload_period_s: number;
  updated_at: string;
  updated_by: string;
}

export interface Alarm {
  id: number;
  level: string;
  title: string;
  message: string;
  is_active: boolean;
  created_at: string;
}

export interface AIRecommendation {
  id: number;
  reason: string;
  suggestion: string;
  confidence: number;
  risk: string;
  last_run_at: string;
}

export interface UserItem {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  created_at: string;
  roles: Role[];
}

export interface PagedDevices {
  items: Device[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlarmListItem {
  id: number;
  device_id: number;
  device_code: string;
  device_name: string;
  level: string;
  title: string;
  message: string;
  is_active: boolean;
  created_at: string;
}

export interface AlarmListResponse {
  items: AlarmListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ActiveAlarmItem {
  id: number;
  device_id: number;
  device_code: string;
  device_name: string;
  alarm_name: string;
  severity: string;
  triggered_at: string;
  status: "Active" | "Cleared";
  reason: string;
  acknowledged: boolean;
}

export interface ActiveAlarmResponse {
  stats: {
    active_total: number;
    critical: number;
    warning: number;
  };
  items: ActiveAlarmItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlarmHistoryItem {
  id: number;
  time: string;
  device_id: number;
  device_code: string;
  device_name: string;
  alarm_type: string;
  severity: string;
  duration_seconds?: number | null;
  recovery: "Cleared" | "Uncleared";
  source: "telemetry" | "params_ack" | "device_status" | "rule_engine" | string;
}

export interface AlarmHistoryResponse {
  items: AlarmHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlarmRuleItem {
  id: number;
  rule_code: string;
  name: string;
  target: string;
  operator: string;
  threshold: string;
  hold_seconds: number;
  severity: string;
  enabled: boolean;
  scope_type: "global" | "device" | "group" | string;
  scope_value: string;
  updated_at: string;
  updated_by: string;
}

export interface AlarmRuleListResponse {
  items: AlarmRuleItem[];
  total: number;
}

export interface AlarmRuleUpdateResponse {
  item: AlarmRuleItem;
  applied: boolean;
}

export interface SummaryItem {
  id: number;
  device_id: number;
  device_code: string;
  device_name: string;
  window_start: string;
  window_end: string;
  sample_count: number;
  avg_temp: number;
  avg_error: number;
  max_overshoot_pct: number;
  saturation_ratio: number;
  observed_settling_sec?: number | null;
  trigger_event: string;
  created_at: string;
}

export interface SummaryListResponse {
  items: SummaryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface SummaryDetailResponse {
  summary: SummaryItem;
  metrics: Metric[];
}
