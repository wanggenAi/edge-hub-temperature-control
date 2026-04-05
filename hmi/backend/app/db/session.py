from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

if not settings.database_url.startswith("postgresql"):
    raise RuntimeError("Only PostgreSQL is supported. Please set DATABASE_URL to a PostgreSQL DSN.")

engine_kwargs: dict = {
    "future": True,
    "pool_pre_ping": True,
}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
