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
