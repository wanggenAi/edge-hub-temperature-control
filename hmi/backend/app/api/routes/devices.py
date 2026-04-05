from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_accessible_device_ids,
    get_current_user,
    get_db_dep,
    get_user_roles,
    require_device_access,
    require_roles,
)
from app.core.config import settings
from app.models.entities import AIRecommendation, Device, DeviceAlarm, DeviceMetric, DeviceParameter, User, UserDevice
from app.schemas.device import (
    AIRecommendationOut,
    AlarmOut,
    DeviceCreate,
    DeviceListResponse,
    DeviceOut,
    DeviceUpdate,
    MetricOut,
    ParameterOut,
    ParameterUpdate,
)
from app.services.mqtt_publisher import MqttPublisher
from app.services.tdengine_client import TdengineClient

router = APIRouter(prefix="/devices", tags=["devices"])
tdengine = TdengineClient()
mqtt_publisher = MqttPublisher()


def parse_ai_gain_suggestion(suggestion: str) -> dict[str, float]:
    updates: dict[str, float] = {}
    pattern = re.compile(r"(Kp|Ki|Kd)\s*:\s*([+-]?\d+(?:\.\d+)?)")
    for key, value in pattern.findall(suggestion):
        updates[key.lower()] = float(value)
    return updates


def query_accessible_devices(db: Session, current_user: User):
    roles = set(get_user_roles(current_user))
    if "admin" in roles:
        return select(Device)
    device_ids = get_accessible_device_ids(db, current_user)
    if not device_ids:
        return select(Device).where(Device.id == -1)
    return select(Device).where(Device.id.in_(device_ids))


def _tdb() -> str:
    return settings.tdengine_database


def _load_live_snapshot(device_code: str) -> dict:
    if not tdengine.enabled():
        return {}
    sql = (
        f"SELECT ts, sensor_temp_c, target_temp_c, pwm_duty, fault_latched "
        f"FROM {_tdb()}.telemetry WHERE device_id='{device_code}' ORDER BY ts DESC LIMIT 1"
    )
    result = tdengine.query(sql)
    if not result.rows:
        return {}
    row = tdengine.row_to_dict(result.columns, result.rows[0])
    return {
        "current_temp": float(row.get("sensor_temp_c") or 0.0),
        "target_temp": float(row.get("target_temp_c") or 0.0),
        "pwm_output": float(row.get("pwm_duty") or 0.0),
        "is_alarm": bool(row.get("fault_latched") or False),
        "is_online": True,
    }


def _apply_live_snapshot(device: Device) -> Device:
    snap = _load_live_snapshot(device.code)
    if not snap:
        return device
    device.current_temp = snap["current_temp"]
    device.target_temp = snap["target_temp"]
    device.pwm_output = snap["pwm_output"]
    device.is_alarm = snap["is_alarm"]
    device.is_online = snap["is_online"]
    return device


@router.get("", response_model=list[DeviceOut])
def list_devices(
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(default=None),
) -> list[Device]:
    query = query_accessible_devices(db, current_user)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Device.code.ilike(like),
                Device.name.ilike(like),
                Device.line.ilike(like),
                Device.location.ilike(like),
            )
        )
    rows = db.scalars(query.order_by(Device.updated_at.desc())).all()
    return [_apply_live_snapshot(row) for row in rows]


@router.get("/manage", response_model=DeviceListResponse)
def list_devices_paginated(
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> DeviceListResponse:
    query = query_accessible_devices(db, current_user)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Device.code.ilike(like),
                Device.name.ilike(like),
                Device.line.ilike(like),
                Device.location.ilike(like),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0

    items = db.scalars(
        query.order_by(Device.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [_apply_live_snapshot(row) for row in items]

    return DeviceListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> Device:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _apply_live_snapshot(device)


@router.post("", response_model=DeviceOut)
def create_device(
    payload: DeviceCreate,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> Device:
    if db.scalar(select(Device).where(Device.code == payload.code)):
        raise HTTPException(status_code=400, detail="Device code already exists")

    device = Device(**payload.model_dump())
    db.add(device)
    db.flush()

    db.add(UserDevice(user_id=current_user.id, device_id=device.id))
    db.add(DeviceParameter(device_id=device.id, updated_by=current_user.username))

    db.commit()
    db.refresh(device)
    return device


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin", "operator")),
    current_user: User = Depends(get_current_user),
) -> Device:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(device, key, value)
    device.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin", "operator")),
    current_user: User = Depends(get_current_user),
) -> dict:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()
    return {"ok": True}


@router.get("/{device_id}/metrics", response_model=list[MetricOut])
def get_metrics(
    device_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> list[DeviceMetric]:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if tdengine.enabled():
        sql = (
            f"SELECT ts, sensor_temp_c, target_temp_c, error_c, pwm_duty, sensor_valid, fault_latched "
            f"FROM {_tdb()}.telemetry WHERE device_id='{device.code}' ORDER BY ts ASC LIMIT 1000"
        )
        result = tdengine.query(sql)
        metrics: list[MetricOut] = []
        for idx, row_raw in enumerate(result.rows):
            row = tdengine.row_to_dict(result.columns, row_raw)
            metrics.append(
                MetricOut(
                    id=idx + 1,
                    timestamp=tdengine.to_datetime(row.get("ts")),
                    current_temp=float(row.get("sensor_temp_c") or 0.0),
                    target_temp=float(row.get("target_temp_c") or 0.0),
                    error=float(row.get("error_c") or 0.0),
                    pwm_output=float(row.get("pwm_duty") or 0.0),
                    status="active",
                    in_spec=abs(float(row.get("error_c") or 0.0)) <= 0.5,
                    is_alarm=bool(row.get("fault_latched") or (row.get("sensor_valid") is False)),
                )
            )
        return metrics
    return db.scalars(
        select(DeviceMetric).where(DeviceMetric.device_id == device_id).order_by(DeviceMetric.timestamp.asc())
    ).all()


@router.get("/{device_id}/parameters", response_model=ParameterOut)
def get_parameters(
    device_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> DeviceParameter:
    require_device_access(device_id, db, current_user)
    param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not param:
        raise HTTPException(status_code=404, detail="Parameters not found")
    return param


@router.put("/{device_id}/parameters", response_model=ParameterOut)
def update_parameters(
    device_id: int,
    payload: ParameterUpdate,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> DeviceParameter:
    require_device_access(device_id, db, current_user)
    param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not param:
        raise HTTPException(status_code=404, detail="Parameters not found")
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(param, key, value)
    param.updated_by = current_user.username
    param.updated_at = datetime.utcnow()

    # Publish runtime parameter update to device MQTT params/set topic.
    mqtt_publisher.publish_params_set(
        device_id=device.code,
        target_temp_c=device.target_temp,
        kp=param.kp,
        ki=param.ki,
        kd=param.kd,
        control_mode=param.control_mode,
        control_period_ms=param.sampling_period_ms,
        apply_immediately=True,
    )

    db.commit()
    db.refresh(param)
    return param


@router.get("/{device_id}/alarms", response_model=list[AlarmOut])
def get_alarms(
    device_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> list[DeviceAlarm]:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if tdengine.enabled():
        sql = (
            f"SELECT ts, rule_code, severity, source, reason, alarm_event_type AS event_type "
            f"FROM {_tdb()}.alarm_events WHERE device_id='{device.code}' ORDER BY ts DESC LIMIT 200"
        )
        result = tdengine.query(sql)
        rows: list[AlarmOut] = []
        for idx, row_raw in enumerate(result.rows):
            row = tdengine.row_to_dict(result.columns, row_raw)
            rows.append(
                AlarmOut(
                    id=idx + 1,
                    level=str(row.get("severity") or "warning"),
                    title=str(row.get("rule_code") or "alarm"),
                    message=str(row.get("reason") or ""),
                    is_active=str(row.get("event_type") or "").lower() != "cleared",
                    created_at=tdengine.to_datetime(row.get("ts")),
                )
            )
        return rows
    return db.scalars(
        select(DeviceAlarm).where(DeviceAlarm.device_id == device_id).order_by(DeviceAlarm.created_at.desc())
    ).all()


@router.get("/{device_id}/ai-recommendation", response_model=AIRecommendationOut)
def get_ai_recommendation(
    device_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> AIRecommendation:
    require_device_access(device_id, db, current_user)
    rec = db.scalar(
        select(AIRecommendation)
        .where(AIRecommendation.device_id == device_id)
        .order_by(AIRecommendation.last_run_at.desc())
    )
    if not rec:
        raise HTTPException(status_code=404, detail="AI recommendation not found")
    return rec


@router.post("/{device_id}/alarms/{alarm_id}/ack")
def acknowledge_alarm(
    device_id: int,
    alarm_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> dict:
    require_device_access(device_id, db, current_user)
    alarm = db.scalar(
        select(DeviceAlarm).where(DeviceAlarm.id == alarm_id, DeviceAlarm.device_id == device_id)
    )
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    # V1 behavior: acknowledge only marks operator acknowledgment.
    # Active/Cleared lifecycle is controlled by alarm state transitions, not ack action.
    alarm.acknowledged = True

    db.commit()
    return {"ok": True, "acknowledged": True}


@router.post("/{device_id}/ai-recommendation/apply", response_model=ParameterOut)
def apply_ai_recommendation(
    device_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> DeviceParameter:
    require_device_access(device_id, db, current_user)
    rec = db.scalar(
        select(AIRecommendation)
        .where(AIRecommendation.device_id == device_id)
        .order_by(AIRecommendation.last_run_at.desc())
    )
    if not rec:
        raise HTTPException(status_code=404, detail="AI recommendation not found")

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not params:
        raise HTTPException(status_code=404, detail="Parameters not found")

    updates = parse_ai_gain_suggestion(rec.suggestion)
    if not updates:
        params.updated_by = f"{current_user.username}:ai-noop"
        params.updated_at = datetime.utcnow()
        rec.last_run_at = datetime.utcnow()
        db.commit()
        db.refresh(params)
        return params

    for key, delta in updates.items():
        current = float(getattr(params, key))
        setattr(params, key, round(current + delta, 4))

    params.updated_by = f"{current_user.username}:ai"
    params.updated_at = datetime.utcnow()
    rec.last_run_at = datetime.utcnow()
    db.commit()
    db.refresh(params)
    return params
