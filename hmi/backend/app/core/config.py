from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Multi-Device Intelligent Temperature Control API"
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "postgresql+psycopg://edgehub:edgehub@127.0.0.1:5432/edgehub"
    run_db_migrations_on_startup: bool = False
    seed_default_alarm_rules_on_startup: bool = False
    seed_demo_data_on_startup: bool = False
    data_source_mode: str = "tdengine"
    tdengine_enabled: bool = False
    tdengine_url: str = "http://127.0.0.1:6041"
    tdengine_database: str = "edgehub"
    tdengine_username: str = "root"
    tdengine_password: str = "taosdata"
    tdengine_query_timeout_seconds: int = 8
    mqtt_publish_enabled: bool = False
    mqtt_broker_host: str = "127.0.0.1"
    mqtt_broker_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id_prefix: str = "hmi-backend"
    mqtt_params_set_topic_template: str = "edge/temperature/{device_id}/params/set"
    mqtt_publish_qos: int = 1
    mqtt_publish_retain: bool = False
    recommendation_generate_cooldown_sec: int = 30
    recommendation_generate_new_record_after_sec: int = 600
    recommendation_float_tolerance: float = 0.001
    ai_runtime_enabled: bool = False
    ai_runtime_url: str = "http://127.0.0.1:8010"
    ai_runtime_timeout_seconds: float = 4.0
    ai_runtime_fail_open: bool = True
    ops_enable_external_metrics: bool = False
    ops_data_hub_metrics_url: str = ""
    ops_runtime_metrics_url: str = ""
    ops_metrics_timeout_seconds: float = 2.0
    ops_ai_health_artifact_max_age_days: int = 30
    ops_ai_health_untrusted_danger_recall_critical: float = 0.30
    ops_ai_health_untrusted_fallback_critical: float = 0.60
    ops_ai_health_poor_success_macro_f1_max: float = 0.55
    ops_ai_health_poor_gap_macro_f1_max: float = 0.45
    ops_ai_health_poor_danger_recall_max: float = 0.45
    ops_ai_health_poor_fallback_min: float = 0.40
    ops_ai_health_poor_ai_manual_delta_min: float = -0.05
    ops_ai_health_watch_success_macro_f1_max: float = 0.70
    ops_ai_health_watch_gap_macro_f1_max: float = 0.65
    ops_ai_health_watch_danger_recall_max: float = 0.60
    ops_ai_health_watch_fallback_min: float = 0.25
    ops_ai_health_watch_ai_manual_delta_min: float = 0.00
    ops_ai_judgment_min_validation_samples: int = 30
    ops_ai_judgment_min_online_samples: int = 10
    ops_ai_judgment_min_drift_recent_samples: int = 20
    ops_ai_judgment_offline_strong_success_macro_f1_min: float = 0.72
    ops_ai_judgment_offline_strong_gap_macro_f1_min: float = 0.65
    ops_ai_judgment_offline_strong_danger_recall_min: float = 0.60
    ops_ai_judgment_offline_weak_success_macro_f1_max: float = 0.55
    ops_ai_judgment_offline_weak_gap_macro_f1_max: float = 0.45
    ops_ai_judgment_offline_weak_danger_recall_max: float = 0.45
    ops_ai_judgment_online_positive_delta_min: float = 0.03
    ops_ai_judgment_online_negative_delta_max: float = -0.03
    ops_ai_judgment_online_worse_guard_delta: float = 0.03
    ops_ai_judgment_runtime_bypassed_fallback_min: float = 0.60
    ops_ai_judgment_runtime_high_ranking_used_min: float = 0.50
    ops_ai_judgment_runtime_high_non_rule_center_min: float = 0.35
    ops_ai_judgment_runtime_high_fallback_max: float = 0.30
    ops_ai_judgment_runtime_low_ranking_used_max: float = 0.20
    ops_ai_judgment_runtime_low_non_rule_center_max: float = 0.15
    model_lifecycle_enabled: bool = False
    model_lifecycle_check_interval_seconds: int = 1800
    model_lifecycle_min_new_eligible_samples: int = 30
    model_lifecycle_min_recent_eligible_samples_7d: int = 40
    model_lifecycle_min_hours_between_runs: int = 12
    model_lifecycle_min_validation_samples: int = 30
    model_lifecycle_max_macro_f1_regression: float = 0.02
    model_lifecycle_max_danger_recall_regression: float = 0.03
    model_lifecycle_max_danger_misclass_regression: float = 0.05
    model_lifecycle_min_macro_f1_improvement: float = 0.0
    model_lifecycle_min_first_promotion_danger_recall: float = 0.50
    hmi_log_level: str = "INFO"
    hmi_console_log_level: str = "INFO"
    hmi_access_log_level: str = "INFO"
    hmi_log_dir: str = "../../runtime/logs/hmi-backend"
    hmi_log_max_bytes: int = 10 * 1024 * 1024
    hmi_log_backup_count: int = 14
    hmi_log_file_name: str = "app.log"
    hmi_error_log_file_name: str = "error.log"
    hmi_access_log_file_name: str = "access.log"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
