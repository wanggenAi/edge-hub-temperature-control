from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import alarms, auth, devices, history, users
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
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
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(alarms.router)
app.include_router(history.router)
