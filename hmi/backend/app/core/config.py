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
    ai_runtime_config_path: str = "../../runtime/ai_runtime_config.json"
    problem_classifier_enabled: bool = True
    success_predictor_enabled: bool = True
    preview_gap_predictor_enabled: bool = True
    candidate_ranker_enabled: bool = True
    problem_classifier_model_path: str = "artifacts/problem_classifier/problem_classifier_tree.joblib"
    success_model_path: str = "artifacts/recommendation_success/recommendation_success_tree.joblib"
    preview_gap_model_path: str = "artifacts/preview_gap/preview_gap_baseline.joblib"
    success_model_variant: str = "tree"
    preview_gap_model_variant: str = "baseline"
    ranker_alpha: float = 0.65
    ranker_beta: float = 0.35
    ranker_candidate_count: int = 6
    high_gap_penalty_threshold: float = 0.75
    use_problem_classifier_for_candidate_bias: bool = False
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
