from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from app.api.deps import get_user_roles
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import Device, User
from app.services.tdengine_client import TdengineClient

router = APIRouter(prefix="/stream", tags=["stream"])
tdengine = TdengineClient()
log = logging.getLogger(__name__)


def _decode_username(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return username


def _load_accessible_devices(db, user: User, device_id: Optional[int]) -> list[Device]:
    query = select(Device)
    roles = set(get_user_roles(user))
    if "admin" not in roles:
        allowed = {item.device_id for item in user.user_devices}
        if not allowed:
            return []
        query = query.where(Device.id.in_(allowed))
    if device_id is not None:
        query = query.where(Device.id == device_id)
    return db.scalars(query.order_by(Device.id.asc())).all()


def _latest_snapshots_by_code() -> dict[str, dict]:
    if not tdengine.enabled():
        return {}
    db_name = settings.tdengine_database
    sql = (
        f"SELECT ts, device_id, sensor_temp_c, target_temp_c, pwm_duty, fault_latched "
        f"FROM {db_name}.telemetry ORDER BY ts DESC LIMIT 5000"
    )
    result = tdengine.query(sql)
    latest: dict[str, dict] = {}
    for raw in result.rows:
        row = tdengine.row_to_dict(result.columns, raw)
        code = str(row.get("device_id") or "")
        if not code or code in latest:
            continue
        latest[code] = row
    return latest


def _serialize_devices(devices: list[Device]) -> list[dict]:
    try:
        latest = _latest_snapshots_by_code()
    except Exception:  # noqa: BLE001
        # Keep websocket stream alive with DB snapshot if TDengine is temporarily unavailable.
        latest = {}
        log.exception("device stream snapshot from TDengine failed")
    payload: list[dict] = []
    for device in devices:
        snap = latest.get(device.code)
        snapshot_ts = None
        current_temp = float(device.current_temp)
        target_temp = float(device.target_temp)
        pwm_output = float(device.pwm_output)
        is_alarm = bool(device.is_alarm)
        is_online = bool(device.is_online)
        if snap:
            current_temp = float(snap.get("sensor_temp_c") or 0.0)
            target_temp = float(snap.get("target_temp_c") or 0.0)
            pwm_output = float(snap.get("pwm_duty") or 0.0)
            is_alarm = bool(snap.get("fault_latched") or False)
            is_online = True
            snapshot_ts = tdengine.to_datetime(snap.get("ts")).isoformat()
        payload.append(
            {
                "id": device.id,
                "code": device.code,
                "name": device.name,
                "line": device.line,
                "location": device.location,
                "status": device.status,
                "current_temp": current_temp,
                "target_temp": target_temp,
                "pwm_output": pwm_output,
                "is_alarm": is_alarm,
                "is_online": is_online,
                "created_at": device.created_at.isoformat(),
                "updated_at": device.updated_at.isoformat(),
                "snapshot_ts": snapshot_ts,
            }
        )
    return payload


@router.websocket("/devices")
async def stream_devices(
    websocket: WebSocket,
    token: str = Query(..., min_length=8),
    device_id: Optional[int] = Query(default=None),
    interval_ms: int = Query(default=2000, ge=500, le=10000),
) -> None:
    username = _decode_username(token)
    await websocket.accept()

    try:
        while True:
            with SessionLocal() as db:
                user = db.scalar(select(User).where(User.username == username))
                if not user or not user.is_active:
                    await websocket.close(code=1008, reason="Invalid user")
                    return
                devices = _load_accessible_devices(db, user, device_id)
                payload = _serialize_devices(devices)

            await websocket.send_json(
                {
                    "type": "device_snapshot",
                    "emitted_at": datetime.now(tz=timezone.utc).isoformat(),
                    "devices": payload,
                }
            )
            await asyncio.sleep(interval_ms / 1000.0)
    except WebSocketDisconnect:
        return
