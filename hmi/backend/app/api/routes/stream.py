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
LIVE_SNAPSHOT_FRESH_MS = 2 * 60 * 1000


def _utc_ms_now() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _td_ts_value_to_ms(value) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return int(value)
        return int(tdengine.to_datetime(value).timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return None


def _is_fresh_td_timestamp(value, *, max_age_ms: int = LIVE_SNAPSHOT_FRESH_MS) -> bool:
    ts_ms = _td_ts_value_to_ms(value)
    if ts_ms is None:
        return False
    age_ms = _utc_ms_now() - ts_ms
    return 0 <= age_ms <= max_age_ms


def _td_pwm_percent(row: dict, *, duty_key: str = "pwm_duty", norm_key: str = "pwm_norm") -> float:
    norm = row.get(norm_key)
    if norm is not None:
        try:
            norm_value = float(norm)
        except (TypeError, ValueError):
            norm_value = None
        if norm_value is not None and norm_value == norm_value:
            if 0.0 <= norm_value <= 1.5:
                return max(0.0, min(100.0, norm_value * 100.0))
            if 1.5 < norm_value <= 100.0:
                return max(0.0, min(100.0, norm_value))

    duty = row.get(duty_key)
    if duty is None:
        return 0.0
    try:
        duty_value = float(duty)
    except (TypeError, ValueError):
        return 0.0
    if duty_value != duty_value:
        return 0.0
    if duty_value > 100.0:
        return max(0.0, min(100.0, duty_value / 255.0 * 100.0))
    return max(0.0, min(100.0, duty_value))


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
        f"SELECT ts, device_id, sensor_temp_c, target_temp_c, pwm_duty, pwm_norm, fault_latched "
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


def _latest_status_by_code() -> dict[str, dict]:
    if not tdengine.enabled():
        return {}
    db_name = settings.tdengine_database
    sql = (
        f"SELECT ts, device_id, online, status_reason "
        f"FROM {db_name}.device_status ORDER BY ts DESC LIMIT 5000"
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
        latest_status = _latest_status_by_code()
    except Exception:  # noqa: BLE001
        # Keep websocket stream alive with DB snapshot if TDengine is temporarily unavailable.
        latest = {}
        latest_status = {}
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
        status = latest_status.get(device.code)
        status_is_fresh = bool(status and _is_fresh_td_timestamp(status.get("ts")))
        if status and status.get("online") is not None and status_is_fresh:
            is_online = bool(status.get("online"))
        if snap:
            current_temp = float(snap.get("sensor_temp_c") or 0.0)
            target_temp = float(snap.get("target_temp_c") or target_temp)
            pwm_output = _td_pwm_percent(snap)
            is_alarm = bool(snap.get("fault_latched") or False)
            if _is_fresh_td_timestamp(snap.get("ts")):
                snapshot_ts = tdengine.to_datetime(snap.get("ts")).isoformat()
                if not status:
                    is_online = True
            elif not status_is_fresh:
                is_online = False
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
