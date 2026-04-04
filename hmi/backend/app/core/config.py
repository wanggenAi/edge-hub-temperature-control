from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_database_url() -> str:
  db_path = Path(__file__).resolve().parents[2] / "data" / "access.db"
  return f"sqlite:///{db_path}"


@dataclass(frozen=True)
class Settings:
  app_name: str = os.getenv("HMI_APP_NAME", "EdgeHub HMI")
  api_prefix: str = "/api"
  token_secret: str = os.getenv("HMI_TOKEN_SECRET", "edgehub-hmi-demo-secret")
  token_expire_minutes: int = int(os.getenv("HMI_TOKEN_EXPIRE_MINUTES", "480"))
  database_url: str = os.getenv("HMI_DATABASE_URL", _default_database_url())
  max_device_ids_per_request: int = int(os.getenv("HMI_MAX_DEVICE_IDS_PER_REQUEST", "500"))
  cors_origins: tuple[str, ...] = (
      "http://localhost:5173",
      "http://127.0.0.1:5173",
  )


settings = Settings()
