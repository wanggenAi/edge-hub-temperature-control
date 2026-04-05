from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import alarms, auth, devices, history, storage_rules, stream, users
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.migrations import upgrade_to_head
from app.services.seed import seed_database

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    if settings.run_db_migrations_on_startup:
        upgrade_to_head()

    db = SessionLocal()
    try:
        seed_database(
            db,
            with_default_alarm_rules=settings.seed_default_alarm_rules_on_startup,
            with_demo_data=settings.seed_demo_data_on_startup,
        )
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(alarms.router)
app.include_router(storage_rules.router)
app.include_router(history.router)
app.include_router(stream.router)
