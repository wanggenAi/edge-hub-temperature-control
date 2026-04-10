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

export interface AITuningParams {
  kp: number;
  ki: number;
  kd: number;
}

export interface AIGeneratedRecommendation {
  problem_type: "normal" | "slow_response" | "steady_state_error" | "overshoot_high" | "oscillation" | "saturation_limited" | string;
  primary_problem_type?: string;
  secondary_problem_types?: string[];
  problem_flags?: Record<string, boolean>;
  confidence: number;
  risk_level: "Low" | "Medium" | "High" | string;
  requires_confirmation: boolean;
  current_params: AITuningParams;
  recommended_params: AITuningParams;
  delta: AITuningParams;
  expected_effect:
    | "keep_stable"
    | "speed_up_response"
    | "reduce_steady_state_error"
    | "reduce_overshoot"
    | "reduce_oscillation"
    | "limited_gain_expected"
    | string;
  evidence: Record<string, string | number | boolean | null>;
  generated_at: string;
  recommendation_id?: number;
  is_new_record?: boolean;
  reused_existing?: boolean;
  reused_recommendation_id?: number | null;
  fingerprint?: string | null;
  history_state?: "generated" | "previewed" | "applied" | "dismissed" | "expired" | string | null;
  last_generate_reused?: boolean;
  reused_count?: number;
  last_accessed_at?: string | null;
  ai_decision?: Record<string, unknown> | null;
}

export interface AIPreviewCurvePoint {
  time_s: number;
  temp: number;
  target_temp: number;
  pwm_output: number;
  error: number;
}

export interface AIPreviewMetrics {
  in_band_ratio: number;
  overshoot_c: number;
  settling_sec?: number | null;
  temp_swing: number;
  mean_abs_error: number;
  saturation_ratio: number;
}

export interface AIPreviewImprovement {
  in_band_ratio_delta: number;
  overshoot_c_delta: number;
  settling_sec_delta: number;
  temp_swing_delta: number;
  mean_abs_error_delta: number;
  saturation_ratio_delta: number;
}

export interface AIPreviewSimulation {
  baseline_params: AITuningParams;
  recommended_params: AITuningParams;
  baseline_curve: AIPreviewCurvePoint[];
  recommended_curve: AIPreviewCurvePoint[];
  baseline_metrics: AIPreviewMetrics;
  recommended_metrics: AIPreviewMetrics;
  improvement: AIPreviewImprovement;
  generated_at: string;
}

export interface AIPostEffectMetrics {
  observed_window_start: string;
  observed_window_end: string;
  point_count: number;
  in_band_ratio_after: number;
  overshoot_c_after: number;
  settling_sec_after?: number | null;
  mean_abs_error_after: number;
  saturation_ratio_after: number;
  temp_swing_after: number;
}

export interface AIPostEffectComparison {
  in_band_ratio_delta?: number | null;
  overshoot_c_delta?: number | null;
  settling_sec_delta?: number | null;
  mean_abs_error_delta?: number | null;
  saturation_ratio_delta?: number | null;
  temp_swing_delta?: number | null;
}

export interface AIPostEffectEvaluation {
  recommendation_id: number;
  history_state: "generated" | "previewed" | "applied" | "dismissed" | "expired" | string;
  evaluated_at: string;
  observation_window_minutes: number;
  actual_effect_summary: AIPostEffectMetrics;
  comparison_to_before: AIPostEffectComparison;
  comparison_to_preview?: AIPostEffectComparison | null;
}

export interface AITelemetryComparisonPoint {
  relative_time_min: number;
  temp: number;
  target_temp?: number | null;
  timestamp?: string | null;
}

export interface AITelemetryComparison {
  recommendation_id: number;
  applied_at: string;
  baseline_window_minutes: number;
  observation_window_minutes: number;
  actual_start: string;
  actual_end: string;
  baseline_curve: AITelemetryComparisonPoint[];
  preview_curve: AITelemetryComparisonPoint[];
  actual_curve: AITelemetryComparisonPoint[];
  target_temp?: number | null;
  target_band?: number | null;
  preview_source: "stored" | "reconstructed" | "unavailable" | string;
  partial_post_apply_window: boolean;
  missing_curves: Array<"baseline" | "preview" | "actual" | string>;
}

export interface AIRecommendationHistoryItem {
  recommendation_id: number;
  device_id: number;
  device_code: string;
  device_name: string;
  device_line: string;
  device_location: string;
  primary_problem_type?: string;
  secondary_problem_types?: string[];
  problem_flags?: Record<string, boolean>;
  key_metrics?: Record<string, number>;
  problem_type: string;
  expected_effect?: string | null;
  risk_level?: string | null;
  confidence: number;
  requires_confirmation: boolean;
  history_state?: string | null;
  generated_at: string;
  fingerprint?: string | null;
  reused_count: number;
  last_generate_reused?: boolean | null;
  last_accessed_at?: string | null;
  applied_at?: string | null;
  current_params?: AITuningParams | null;
  recommended_params?: AITuningParams | null;
  delta?: AITuningParams | null;
  actual_effect_evaluated: boolean;
  insufficient_data?: boolean;
  evaluated_at?: string | null;
  observation_window_minutes?: number | null;
  post_effect_summary?: AIPostEffectMetrics | null;
  comparison_to_before?: AIPostEffectComparison | null;
  comparison_to_preview?: AIPostEffectComparison | null;
  effect_outcome: "improved" | "unchanged" | "worse" | "pending" | string;
  ai_decision?: Record<string, unknown> | null;
}

export interface AIRecommendationHistoryStats {
  total: number;
  applied: number;
  evaluated: number;
  improved: number;
  unchanged: number;
  worse: number;
  pending_evaluation: number;
}

export interface AIRecommendationHistoryResponse {
  items: AIRecommendationHistoryItem[];
  stats: AIRecommendationHistoryStats;
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

export interface StorageRuleItem {
  id: number;
  scope_type: "global" | "device" | string;
  scope_value: string;
  raw_mode: "full" | "relaxed" | "strict" | "disabled" | string;
  summary_enabled: boolean;
  summary_min_samples: number;
  heartbeat_interval_ms: number;
  target_temp_deadband: number;
  sim_temp_deadband: number;
  sensor_temp_deadband: number;
  error_deadband: number;
  integral_error_deadband: number;
  control_output_deadband: number;
  pwm_duty_deadband: number;
  pwm_norm_deadband: number;
  parameter_deadband: number;
  enabled: boolean;
  updated_at: string;
  updated_by: string;
}

export interface StorageRuleListResponse {
  items: StorageRuleItem[];
  total: number;
}

export interface StorageRuleMutationResponse {
  item: StorageRuleItem;
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

export interface OpsKeyValueCount {
  key: string;
  count: number;
}

export interface OpsTrendPoint {
  ts: string;
  mqtt_ingress_tps?: number | null;
  consume_tps?: number | null;
  dropped_delta?: number | null;
  queue_depth?: number | null;
  parse_fail_delta?: number | null;
  persist_fail_delta?: number | null;
  tdengine_write_failed_delta?: number | null;
}

export interface OpsDataHub {
  as_of: string;
  source: string;
  available: boolean;
  interval_seconds?: number | null;
  mqtt_ingress_tps?: number | null;
  mqtt_egress_tps?: number | null;
  data_hub_consume_tps?: number | null;
  queue_depth?: number | null;
  dropped_total?: number | null;
  dropped_delta?: number | null;
  outcome_ingress_drop_delta?: number | null;
  outcome_pipeline_drop_delta?: number | null;
  outcome_parse_fail_delta?: number | null;
  outcome_persist_fail_delta?: number | null;
  outcome_telemetry_skip_delta?: number | null;
  outcome_control_topic_delta?: number | null;
  outcome_persisted_delta?: number | null;
  accounting_unaccounted_delta?: number | null;
  telemetry_persisted_delta?: number | null;
  params_set_delta?: number | null;
  params_ack_delta?: number | null;
  device_status_delta?: number | null;
  discard_reasons_top: OpsKeyValueCount[];
  tdengine_write_success_total?: number | null;
  tdengine_write_failed_total?: number | null;
  tdengine_write_success_delta?: number | null;
  tdengine_write_failed_delta?: number | null;
  data_hub_cpu_usage_pct?: number | null;
  trend: OpsTrendPoint[];
}

export interface OpsRuntime {
  as_of: string;
  source: string;
  process_uptime_seconds: number;
  process_thread_count: number;
  process_cpu_usage_pct?: number | null;
  load_avg_1m?: number | null;
  load_avg_5m?: number | null;
  load_avg_15m?: number | null;
  db_pool_size?: number | null;
  db_pool_checked_in?: number | null;
  db_pool_checked_out?: number | null;
  db_pool_overflow?: number | null;
  db_pool_status?: string | null;
  jvm_metrics_available: boolean;
  jvm_heap_used_mb?: number | null;
  jvm_heap_max_mb?: number | null;
  jvm_non_heap_used_mb?: number | null;
  jvm_gc_count?: number | null;
  jvm_gc_pause_ms?: number | null;
  jvm_gc_pause_max_ms?: number | null;
  jvm_thread_count?: number | null;
  ai_runtime_enabled: boolean;
  ai_runtime_url?: string | null;
  ai_runtime_log_updated_at?: string | null;
  data_hub_log_updated_at?: string | null;
}

export interface OpsEvalJobStatus {
  pending: number;
  running: number;
  done: number;
  retry_pending: number;
  terminal_insufficient: number;
  failed: number;
}

export interface OpsRecentEvalJob {
  job_id: number;
  control_action_id: number;
  device_id: number;
  source: string;
  status: string;
  attempt_count: number;
  scheduled_at: string;
  updated_at: string;
  last_error?: string | null;
}

export interface OpsLearningLoop {
  as_of: string;
  control_actions_by_source_total: OpsKeyValueCount[];
  control_actions_by_source_24h: OpsKeyValueCount[];
  eval_jobs_by_status: OpsEvalJobStatus;
  pending_overdue: number;
  worker_processed_24h: number;
  worker_last_activity_at?: string | null;
  sample_quality_distribution: OpsKeyValueCount[];
  training_eligible_total: number;
  training_eligible_7d: number;
  training_eligible_daily_7d: OpsTrendPoint[];
  actual_effect_distribution: OpsKeyValueCount[];
  recent_jobs: OpsRecentEvalJob[];
}

export interface OpsModelRuntime {
  as_of: string;
  active_model_version?: string | null;
  candidate_model_version?: string | null;
  last_trained_at?: string | null;
  last_promoted_at?: string | null;
  archived_model_artifact_count: number;
  runtime_source_breakdown: OpsKeyValueCount[];
  fallback_ratio?: number | null;
  recommendation_generated_24h: number;
  recommendation_applied_24h: number;
  ai_runtime_enabled: boolean;
  notes: string[];
}

export interface OpsAiOverview {
  as_of: string;
  ai_runtime_enabled: boolean;
  ai_runtime_url?: string | null;
  runtime_source_breakdown: OpsKeyValueCount[];
  fallback_ratio?: number | null;
  fallback_elevated: boolean;
  recommendation_generated_24h: number;
  recommendation_applied_24h: number;
  recommendation_apply_rate?: number | null;
  ai_origin_control_actions_24h: number;
  ai_effect_distribution: OpsKeyValueCount[];
  manual_effect_distribution: OpsKeyValueCount[];
  ai_improved_ratio?: number | null;
  manual_improved_ratio?: number | null;
  ai_sample_count: number;
  manual_sample_count: number;
}

export interface OpsOverview {
  as_of: string;
  data_hub: OpsDataHub;
  runtime: OpsRuntime;
  ai_overview: OpsAiOverview;
  learning_loop: OpsLearningLoop;
  models: OpsModelRuntime;
}

export interface OpsAiHealthSummary {
  overall_model_health: "Good" | "Watch" | "Poor" | "Untrusted" | string;
  success_model_macro_f1?: number | null;
  preview_gap_model_macro_f1?: number | null;
  recall_worse?: number | null;
  recall_high_gap?: number | null;
  fallback_ratio?: number | null;
  ai_improved_ratio?: number | null;
  manual_improved_ratio?: number | null;
  ai_vs_manual_improved_delta?: number | null;
  feature_drift_status: string;
  label_drift_status: string;
  interpretation: string;
}

export interface OpsAiWhyStatus {
  status: string;
  summary: string;
  reasons: string[];
}

export interface OpsAiJudgment {
  value: string;
  tone: "normal" | "warning" | "critical" | string;
  reason: string;
}

export interface OpsAiPerClassMetric {
  label: string;
  precision?: number | null;
  recall?: number | null;
  f1?: number | null;
  support?: number | null;
}

export interface OpsAiConfusionMatrix {
  labels: string[];
  matrix: number[][];
  note?: string | null;
}

export interface OpsAiModelEvaluation {
  model_key?: string | null;
  model_name?: string | null;
  artifact_path?: string | null;
  artifact_timestamp?: string | null;
  validation_size?: number | null;
  accuracy?: number | null;
  macro_precision?: number | null;
  macro_recall?: number | null;
  macro_f1?: number | null;
  per_class: OpsAiPerClassMetric[];
  confusion: OpsAiConfusionMatrix;
  training_label_distribution: OpsKeyValueCount[];
}

export interface OpsAiOfflineEvaluation {
  success_model: OpsAiModelEvaluation;
  preview_gap_model: OpsAiModelEvaluation;
}

export interface OpsAiOutcomeBreakdown {
  improved: number;
  unchanged: number;
  worse: number;
  total: number;
  improved_ratio?: number | null;
  worse_ratio?: number | null;
}

export interface OpsAiOnlineWindow {
  window: string;
  ai: OpsAiOutcomeBreakdown;
  manual: OpsAiOutcomeBreakdown;
  ai_vs_manual_improved_delta?: number | null;
}

export interface OpsAiOnlineOutcomes {
  window_24h: OpsAiOnlineWindow;
  window_7d: OpsAiOnlineWindow;
}

export interface OpsAiFeatureDrift {
  feature: string;
  baseline_mean?: number | null;
  baseline_p50?: number | null;
  baseline_p95?: number | null;
  recent_mean?: number | null;
  recent_p50?: number | null;
  recent_p95?: number | null;
  delta_ratio?: number | null;
  status: string;
}

export interface OpsAiLabelDrift {
  label_group: string;
  label: string;
  training_ratio?: number | null;
  recent_ratio?: number | null;
  delta_abs?: number | null;
  status: string;
}

export interface OpsAiDataQuality {
  recent_feedback_sample_count: number;
  usable_for_training_ratio?: number | null;
  label_coverage?: string | null;
  sample_quality_distribution: OpsKeyValueCount[];
}

export interface OpsAiDriftDataHealth {
  feature_drift_status: string;
  label_drift_status: string;
  feature_drift: OpsAiFeatureDrift[];
  label_drift: OpsAiLabelDrift[];
  data_quality: OpsAiDataQuality;
}

export interface OpsAiRuntimeReliability {
  ranking_used_ratio?: number | null;
  ranking_fallback_used_ratio?: number | null;
  runtime_fallback_ratio?: number | null;
  candidate_selection_distribution: OpsKeyValueCount[];
  rule_center_selected_ratio?: number | null;
  baseline_hold_selected_ratio?: number | null;
  conservative_selected_ratio?: number | null;
  aggressive_selected_ratio?: number | null;
  balance_selected_ratio?: number | null;
}

export interface OpsAiObservability {
  as_of: string;
  health_summary: OpsAiHealthSummary;
  why_this_status: OpsAiWhyStatus;
  offline_quality: OpsAiJudgment;
  evidence_confidence: OpsAiJudgment;
  online_usefulness: OpsAiJudgment;
  runtime_influence: OpsAiJudgment;
  drift_summary: OpsAiJudgment;
  label_drift_summary: OpsAiJudgment;
  offline_evaluation: OpsAiOfflineEvaluation;
  online_outcome_quality: OpsAiOnlineOutcomes;
  drift_data_health: OpsAiDriftDataHealth;
  runtime_reliability: OpsAiRuntimeReliability;
  primary_metrics: string[];
  secondary_metrics: string[];
}

export interface OpsRunbook {
  key: string;
  title: string;
  section: string;
  tags: string[];
  markdown_body: string;
  is_active: boolean;
  is_customized: boolean;
  version: number;
  updated_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OpsRunbookList {
  items: OpsRunbook[];
}

export interface OpsRunbookUpdateInput {
  title?: string;
  section?: string;
  tags?: string[];
  markdown_body?: string;
  is_active?: boolean;
}
