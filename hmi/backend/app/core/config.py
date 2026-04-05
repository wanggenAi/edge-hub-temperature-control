from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Multi-Device Intelligent Temperature Control API"
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./app.db"
    redis_enabled: bool = True
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_alarm_rules_key: str = "datahub:alarm:rules"
    redis_alarm_rules_ttl_seconds: int = 172800
    data_source_mode: str = "sqlite"
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
    mqtt_publish_qos: int = 0
    mqtt_publish_retain: bool = False
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
