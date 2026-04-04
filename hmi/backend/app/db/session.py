from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Base


def _build_engine():
  database_url = settings.database_url
  if database_url.startswith("sqlite:///"):
    db_path = database_url.removeprefix("sqlite:///")
    if db_path:
      Path(db_path).parent.mkdir(parents=True, exist_ok=True)
  connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
  return create_engine(database_url, future=True, connect_args=connect_args)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
  Base.metadata.create_all(bind=engine)
