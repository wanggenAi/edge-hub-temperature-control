from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OpsKeyValueCount(BaseModel):
    key: str
    count: int


class OpsTrendPoint(BaseModel):
    ts: datetime
    mqtt_ingress_tps: Optional[float] = None
    consume_tps: Optional[float] = None
    dropped_delta: Optional[int] = None
    queue_depth: Optional[int] = None
    parse_fail_delta: Optional[int] = None
    persist_fail_delta: Optional[int] = None
    tdengine_write_failed_delta: Optional[int] = None


class OpsDataHubOut(BaseModel):
    as_of: datetime
    source: str
    available: bool
    interval_seconds: Optional[float] = None
    mqtt_ingress_tps: Optional[float] = None
    mqtt_egress_tps: Optional[float] = None
    data_hub_consume_tps: Optional[float] = None
    queue_depth: Optional[int] = None
    dropped_total: Optional[int] = None
    dropped_delta: Optional[int] = None
    outcome_ingress_drop_delta: Optional[int] = None
    outcome_pipeline_drop_delta: Optional[int] = None
    outcome_parse_fail_delta: Optional[int] = None
    outcome_persist_fail_delta: Optional[int] = None
    outcome_telemetry_skip_delta: Optional[int] = None
    outcome_control_topic_delta: Optional[int] = None
    outcome_persisted_delta: Optional[int] = None
    accounting_unaccounted_delta: Optional[int] = None
    telemetry_persisted_delta: Optional[int] = None
    params_set_delta: Optional[int] = None
    params_ack_delta: Optional[int] = None
    device_status_delta: Optional[int] = None
    discard_reasons_top: list[OpsKeyValueCount] = Field(default_factory=list)
    tdengine_write_success_total: Optional[int] = None
    tdengine_write_failed_total: Optional[int] = None
    tdengine_write_success_delta: Optional[int] = None
    tdengine_write_failed_delta: Optional[int] = None
    data_hub_cpu_usage_pct: Optional[float] = None
    trend: list[OpsTrendPoint] = Field(default_factory=list)


class OpsRuntimeOut(BaseModel):
    as_of: datetime
    source: str = "local_process"
    process_uptime_seconds: float
    process_thread_count: int
    process_cpu_usage_pct: Optional[float] = None
    load_avg_1m: Optional[float] = None
    load_avg_5m: Optional[float] = None
    load_avg_15m: Optional[float] = None
    db_pool_size: Optional[int] = None
    db_pool_checked_in: Optional[int] = None
    db_pool_checked_out: Optional[int] = None
    db_pool_overflow: Optional[int] = None
    db_pool_status: Optional[str] = None
    jvm_metrics_available: bool = False
    jvm_heap_used_mb: Optional[float] = None
    jvm_heap_max_mb: Optional[float] = None
    jvm_non_heap_used_mb: Optional[float] = None
    jvm_gc_count: Optional[int] = None
    jvm_gc_pause_ms: Optional[float] = None
    jvm_gc_pause_max_ms: Optional[float] = None
    jvm_thread_count: Optional[int] = None
    ai_runtime_enabled: bool = False
    ai_runtime_url: Optional[str] = None
    ai_runtime_log_updated_at: Optional[datetime] = None
    data_hub_log_updated_at: Optional[datetime] = None


class OpsEvalJobStatusOut(BaseModel):
    pending: int = 0
    running: int = 0
    done: int = 0
    retry_pending: int = 0
    terminal_insufficient: int = 0
    failed: int = 0


class OpsRecentEvalJobOut(BaseModel):
    job_id: int
    control_action_id: int
    device_id: int
    source: str
    status: str
    attempt_count: int
    scheduled_at: datetime
    updated_at: datetime
    last_error: Optional[str] = None


class OpsLearningLoopOut(BaseModel):
    as_of: datetime
    control_actions_by_source_total: list[OpsKeyValueCount] = Field(default_factory=list)
    control_actions_by_source_24h: list[OpsKeyValueCount] = Field(default_factory=list)
    eval_jobs_by_status: OpsEvalJobStatusOut
    pending_overdue: int = 0
    worker_processed_24h: int = 0
    worker_last_activity_at: Optional[datetime] = None
    sample_quality_distribution: list[OpsKeyValueCount] = Field(default_factory=list)
    training_eligible_total: int = 0
    training_eligible_7d: int = 0
    training_eligible_daily_7d: list[OpsTrendPoint] = Field(default_factory=list)
    actual_effect_distribution: list[OpsKeyValueCount] = Field(default_factory=list)
    recent_jobs: list[OpsRecentEvalJobOut] = Field(default_factory=list)


class OpsModelRuntimeOut(BaseModel):
    as_of: datetime
    active_model_version: Optional[str] = None
    candidate_model_version: Optional[str] = None
    last_trained_at: Optional[datetime] = None
    last_promoted_at: Optional[datetime] = None
    archived_model_artifact_count: int = 0
    runtime_source_breakdown: list[OpsKeyValueCount] = Field(default_factory=list)
    fallback_ratio: Optional[float] = None
    recommendation_generated_24h: int = 0
    recommendation_applied_24h: int = 0
    ai_runtime_enabled: bool = False
    notes: list[str] = Field(default_factory=list)


class OpsAiOverviewOut(BaseModel):
    as_of: datetime
    ai_runtime_enabled: bool = False
    ai_runtime_url: Optional[str] = None
    runtime_source_breakdown: list[OpsKeyValueCount] = Field(default_factory=list)
    fallback_ratio: Optional[float] = None
    fallback_elevated: bool = False
    recommendation_generated_24h: int = 0
    recommendation_applied_24h: int = 0
    recommendation_apply_rate: Optional[float] = None
    ai_origin_control_actions_24h: int = 0
    ai_effect_distribution: list[OpsKeyValueCount] = Field(default_factory=list)
    manual_effect_distribution: list[OpsKeyValueCount] = Field(default_factory=list)
    ai_improved_ratio: Optional[float] = None
    manual_improved_ratio: Optional[float] = None
    ai_sample_count: int = 0
    manual_sample_count: int = 0


class OpsAiHealthSummaryOut(BaseModel):
    overall_model_health: str = "Untrusted"
    success_model_macro_f1: Optional[float] = None
    preview_gap_model_macro_f1: Optional[float] = None
    recall_worse: Optional[float] = None
    recall_high_gap: Optional[float] = None
    fallback_ratio: Optional[float] = None
    ai_improved_ratio: Optional[float] = None
    manual_improved_ratio: Optional[float] = None
    ai_vs_manual_improved_delta: Optional[float] = None
    feature_drift_status: str = "Unknown"
    label_drift_status: str = "Unknown"
    interpretation: str = ""


class OpsAiWhyStatusOut(BaseModel):
    status: str = "Untrusted"
    summary: str = ""
    reasons: list[str] = Field(default_factory=list)


class OpsAiJudgmentOut(BaseModel):
    value: str
    tone: str
    reason: str


class OpsAiPerClassMetricOut(BaseModel):
    label: str
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    support: Optional[int] = None


class OpsAiConfusionMatrixOut(BaseModel):
    labels: list[str] = Field(default_factory=list)
    matrix: list[list[int]] = Field(default_factory=list)
    note: Optional[str] = None


class OpsAiModelEvaluationOut(BaseModel):
    model_key: Optional[str] = None
    model_name: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_timestamp: Optional[datetime] = None
    validation_size: Optional[int] = None
    accuracy: Optional[float] = None
    macro_precision: Optional[float] = None
    macro_recall: Optional[float] = None
    macro_f1: Optional[float] = None
    per_class: list[OpsAiPerClassMetricOut] = Field(default_factory=list)
    confusion: OpsAiConfusionMatrixOut = Field(default_factory=OpsAiConfusionMatrixOut)
    training_label_distribution: list[OpsKeyValueCount] = Field(default_factory=list)


class OpsAiOfflineEvaluationOut(BaseModel):
    success_model: OpsAiModelEvaluationOut
    preview_gap_model: OpsAiModelEvaluationOut


class OpsAiOutcomeBreakdownOut(BaseModel):
    improved: int = 0
    unchanged: int = 0
    worse: int = 0
    total: int = 0
    improved_ratio: Optional[float] = None
    worse_ratio: Optional[float] = None


class OpsAiOnlineWindowOut(BaseModel):
    window: str
    ai: OpsAiOutcomeBreakdownOut
    manual: OpsAiOutcomeBreakdownOut
    ai_vs_manual_improved_delta: Optional[float] = None


class OpsAiOnlineOutcomesOut(BaseModel):
    window_24h: OpsAiOnlineWindowOut
    window_7d: OpsAiOnlineWindowOut


class OpsAiFeatureDriftOut(BaseModel):
    feature: str
    baseline_mean: Optional[float] = None
    baseline_p50: Optional[float] = None
    baseline_p95: Optional[float] = None
    recent_mean: Optional[float] = None
    recent_p50: Optional[float] = None
    recent_p95: Optional[float] = None
    delta_ratio: Optional[float] = None
    status: str = "Unknown"


class OpsAiLabelDriftOut(BaseModel):
    label_group: str
    label: str
    training_ratio: Optional[float] = None
    recent_ratio: Optional[float] = None
    delta_abs: Optional[float] = None
    status: str = "Unknown"


class OpsAiDataQualityOut(BaseModel):
    recent_feedback_sample_count: int = 0
    usable_for_training_ratio: Optional[float] = None
    label_coverage: Optional[str] = None
    sample_quality_distribution: list[OpsKeyValueCount] = Field(default_factory=list)


class OpsAiDriftDataHealthOut(BaseModel):
    feature_drift_status: str = "Unknown"
    label_drift_status: str = "Unknown"
    feature_drift: list[OpsAiFeatureDriftOut] = Field(default_factory=list)
    label_drift: list[OpsAiLabelDriftOut] = Field(default_factory=list)
    data_quality: OpsAiDataQualityOut = Field(default_factory=OpsAiDataQualityOut)


class OpsAiRuntimeReliabilityOut(BaseModel):
    ranking_used_ratio: Optional[float] = None
    ranking_fallback_used_ratio: Optional[float] = None
    runtime_fallback_ratio: Optional[float] = None
    candidate_selection_distribution: list[OpsKeyValueCount] = Field(default_factory=list)
    rule_center_selected_ratio: Optional[float] = None
    baseline_hold_selected_ratio: Optional[float] = None
    conservative_selected_ratio: Optional[float] = None
    aggressive_selected_ratio: Optional[float] = None
    balance_selected_ratio: Optional[float] = None


class OpsAiObservabilityOut(BaseModel):
    as_of: datetime
    health_summary: OpsAiHealthSummaryOut
    why_this_status: OpsAiWhyStatusOut
    offline_quality: OpsAiJudgmentOut
    evidence_confidence: OpsAiJudgmentOut
    online_usefulness: OpsAiJudgmentOut
    runtime_influence: OpsAiJudgmentOut
    drift_summary: OpsAiJudgmentOut
    label_drift_summary: OpsAiJudgmentOut
    offline_evaluation: OpsAiOfflineEvaluationOut
    online_outcome_quality: OpsAiOnlineOutcomesOut
    drift_data_health: OpsAiDriftDataHealthOut
    runtime_reliability: OpsAiRuntimeReliabilityOut
    primary_metrics: list[str] = Field(default_factory=list)
    secondary_metrics: list[str] = Field(default_factory=list)


class OpsOverviewOut(BaseModel):
    as_of: datetime
    data_hub: OpsDataHubOut
    runtime: OpsRuntimeOut
    ai_overview: OpsAiOverviewOut
    learning_loop: OpsLearningLoopOut
    models: OpsModelRuntimeOut
