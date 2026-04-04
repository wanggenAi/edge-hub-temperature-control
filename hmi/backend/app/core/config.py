from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Multi-Device Intelligent Temperature Control API"
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./app.db"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
