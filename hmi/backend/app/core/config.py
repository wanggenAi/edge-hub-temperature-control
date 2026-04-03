from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
  app_name: str = os.getenv("HMI_APP_NAME", "EdgeHub HMI")
  api_prefix: str = "/api"
  token_secret: str = os.getenv("HMI_TOKEN_SECRET", "edgehub-hmi-demo-secret")
  token_expire_minutes: int = int(os.getenv("HMI_TOKEN_EXPIRE_MINUTES", "480"))
  cors_origins: tuple[str, ...] = (
      "http://localhost:5173",
      "http://127.0.0.1:5173",
  )


settings = Settings()
