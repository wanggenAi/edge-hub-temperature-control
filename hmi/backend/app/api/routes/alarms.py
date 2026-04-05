from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_device_ids, get_current_user, get_db_dep, get_user_roles, require_roles
from app.core.config import settings
from app.models.entities import AlarmRule, Device, DeviceAlarm, User
from app.schemas.alarm import (
    ActiveAlarmItem,
    ActiveAlarmResponse,
    ActiveAlarmStats,
    AlarmHistoryItem,
    AlarmHistoryResponse,
    AlarmRuleItem,
    AlarmRuleListResponse,
    AlarmRuleUpdateIn,
    AlarmRuleUpdateOut,
)
from app.services.alarm_rule_cache import sync_rule_to_redis
from app.services.tdengine_client import TdengineClient

router = APIRouter(prefix="/alarms", tags=["alarms"])
tdengine = TdengineClient()


def _scoped_base(db: Session, current_user: User):
    roles = set(get_user_roles(current_user))
    base = select(DeviceAlarm, Device).join(Device, DeviceAlarm.device_id == Device.id)
    if "admin" in roles:
        return base
    ids = get_accessible_device_ids(db, current_user)
    if not ids:
        return base.where(DeviceAlarm.device_id == -1)
    return base.where(DeviceAlarm.device_id.in_(ids))


def _tdb() -> str:
    return settings.tdengine_database


def _load_accessible_devices_by_code(db: Session, current_user: User) -> dict[str, Device]:
    roles = set(get_user_roles(current_user))
    q = select(Device)
    if "admin" not in roles:
        ids = get_accessible_device_ids(db, current_user)
        if not ids:
            return {}
        q = q.where(Device.id.in_(ids))
    rows = db.scalars(q).all()
    return {d.code: d for d in rows}


@router.get("/active", response_model=ActiveAlarmResponse)
def list_active_alarms(
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
    status: str = Query(default="active", regex="^(active|all)$"),
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> ActiveAlarmResponse:
    if tdengine.enabled():
        device_map = _load_accessible_devices_by_code(db, current_user)
        if not device_map:
            return ActiveAlarmResponse(
                stats=ActiveAlarmStats(active_total=0, critical=0, warning=0),
                items=[],
                total=0,
                page=page,
                page_size=page_size,
            )
        sql = (
            f"SELECT e.device_id, e.rule_code, e.severity, e.source, e.reason, e.ts, e.alarm_event_type AS event_type "
            f"FROM {_tdb()}.alarm_events e "
            f"INNER JOIN (SELECT device_id, rule_code, MAX(ts) AS max_ts FROM {_tdb()}.alarm_events GROUP BY device_id, rule_code) latest "
            f"ON e.device_id=latest.device_id AND e.rule_code=latest.rule_code AND e.ts=latest.max_ts "
            f"ORDER BY e.ts DESC LIMIT 2000"
        )
        result = tdengine.query(sql)
        all_items: list[ActiveAlarmItem] = []
        for idx, row_raw in enumerate(result.rows):
            row = tdengine.row_to_dict(result.columns, row_raw)
            if str(row.get("event_type") or "").lower() != "triggered":
                continue
            device_code = str(row.get("device_id") or "")
            device = device_map.get(device_code)
            if not device:
                continue
            severity = str(row.get("severity") or "warning")
            if q:
                text = f"{device.code} {device.name} {row.get('rule_code') or ''} {row.get('reason') or ''}".lower()
                if q.strip().lower() not in text:
                    continue
            all_items.append(
                ActiveAlarmItem(
                    id=idx + 1,
                    device_id=device.id,
                    device_code=device.code,
                    device_name=device.name,
                    alarm_name=str(row.get("rule_code") or "alarm"),
                    severity=severity,
                    triggered_at=tdengine.to_datetime(row.get("ts")),
                    status="Active",
                    reason=str(row.get("reason") or ""),
                    acknowledged=False,
                )
            )
        if status == "all":
            pass
        active_total = len(all_items)
        critical = sum(1 for i in all_items if i.severity == "critical")
        warning = sum(1 for i in all_items if i.severity == "warning")
        start = (page - 1) * page_size
        end = start + page_size
        return ActiveAlarmResponse(
            stats=ActiveAlarmStats(active_total=active_total, critical=critical, warning=warning),
            items=all_items[start:end],
            total=active_total,
            page=page,
            page_size=page_size,
        )

    base = _scoped_base(db, current_user)
    if status == "active":
        base = base.where(DeviceAlarm.is_active.is_(True))

    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                DeviceAlarm.title.ilike(like),
                DeviceAlarm.message.ilike(like),
                Device.name.ilike(like),
                Device.code.ilike(like),
            )
        )

    severity_order = case((DeviceAlarm.level == "critical", 0), (DeviceAlarm.level == "warning", 1), else_=2)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.execute(
        base.order_by(DeviceAlarm.created_at.desc(), severity_order.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    active_stats_base = _scoped_base(db, current_user).where(DeviceAlarm.is_active.is_(True))
    active_total = db.scalar(select(func.count()).select_from(active_stats_base.subquery())) or 0
    critical = db.scalar(
        select(func.count()).select_from(active_stats_base.where(DeviceAlarm.level == "critical").subquery())
    ) or 0
    warning = db.scalar(
        select(func.count()).select_from(active_stats_base.where(DeviceAlarm.level == "warning").subquery())
    ) or 0

    items = [
        ActiveAlarmItem(
            id=alarm.id,
            device_id=alarm.device_id,
            device_code=device.code,
            device_name=device.name,
            alarm_name=alarm.title,
            severity=alarm.level,
            triggered_at=alarm.created_at,
            status="Active" if alarm.is_active else "Cleared",
            reason=alarm.message,
            acknowledged=alarm.acknowledged,
        )
        for alarm, device in rows
    ]

    return ActiveAlarmResponse(
        stats=ActiveAlarmStats(active_total=active_total, critical=critical, warning=warning),
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/history", response_model=AlarmHistoryResponse)
def list_alarm_history(
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    alarm_type: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    range_key: str = Query(default="24h", regex="^(24h|7d)$"),
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> AlarmHistoryResponse:
    if tdengine.enabled():
        device_map = _load_accessible_devices_by_code(db, current_user)
        if not device_map:
            return AlarmHistoryResponse(items=[], total=0, page=page, page_size=page_size)
        since = datetime.utcnow() - (timedelta(hours=24) if range_key == "24h" else timedelta(days=7))
        sql = (
            f"SELECT ts, device_id, rule_code, severity, source, reason, alarm_event_type AS event_type, duration_seconds "
            f"FROM {_tdb()}.alarm_events WHERE ts >= {int(since.timestamp() * 1000)} ORDER BY ts DESC LIMIT 5000"
        )
        result = tdengine.query(sql)
        items_all: list[AlarmHistoryItem] = []
        for idx, row_raw in enumerate(result.rows):
            row = tdengine.row_to_dict(result.columns, row_raw)
            device_code = str(row.get("device_id") or "")
            device = device_map.get(device_code)
            if not device:
                continue
            sev = str(row.get("severity") or "warning")
            rule = str(row.get("rule_code") or "")
            src = str(row.get("source") or "rule_engine")
            if device_id is not None and device.id != device_id:
                continue
            if severity and sev != severity:
                continue
            if alarm_type and rule != alarm_type:
                continue
            if source and src != source:
                continue
            if q:
                text = f"{device.code} {device.name} {rule} {row.get('reason') or ''}".lower()
                if q.strip().lower() not in text:
                    continue
            ev_type = str(row.get("event_type") or "").lower()
            items_all.append(
                AlarmHistoryItem(
                    id=idx + 1,
                    time=tdengine.to_datetime(row.get("ts")),
                    device_id=device.id,
                    device_code=device.code,
                    device_name=device.name,
                    alarm_type=rule,
                    severity=sev,
                    duration_seconds=int(row.get("duration_seconds")) if row.get("duration_seconds") is not None else None,
                    recovery="Cleared" if ev_type == "cleared" else "Uncleared",
                    source=src,
                )
            )
        total = len(items_all)
        start = (page - 1) * page_size
        end = start + page_size
        return AlarmHistoryResponse(items=items_all[start:end], total=total, page=page, page_size=page_size)

    base = _scoped_base(db, current_user)
    since = datetime.utcnow() - (timedelta(hours=24) if range_key == "24h" else timedelta(days=7))
    base = base.where(DeviceAlarm.created_at >= since)

    if device_id is not None:
        base = base.where(DeviceAlarm.device_id == device_id)
    if severity:
        base = base.where(DeviceAlarm.level == severity)
    if alarm_type:
        base = base.where(DeviceAlarm.rule_code == alarm_type)
    if source:
        base = base.where(DeviceAlarm.source == source)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Device.name.ilike(like), Device.code.ilike(like), DeviceAlarm.title.ilike(like)))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(DeviceAlarm.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = []
    for alarm, device in rows:
        duration = None
        if alarm.cleared_at:
            duration = max(0, int((alarm.cleared_at - alarm.created_at).total_seconds()))
        elif not alarm.is_active:
            duration = 0
        items.append(
            AlarmHistoryItem(
                id=alarm.id,
                time=alarm.created_at,
                device_id=alarm.device_id,
                device_code=device.code,
                device_name=device.name,
                alarm_type=alarm.rule_code,
                severity=alarm.level,
                duration_seconds=duration,
                recovery="Cleared" if not alarm.is_active else "Uncleared",
                source=alarm.source,
            )
        )

    return AlarmHistoryResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/rules", response_model=AlarmRuleListResponse)
def list_alarm_rules(
    db: Session = Depends(get_db_dep),
    _: User = Depends(get_current_user),
) -> AlarmRuleListResponse:
    rows = db.scalars(select(AlarmRule).order_by(AlarmRule.rule_code.asc())).all()
    items = [
        AlarmRuleItem(
            id=r.id,
            rule_code=r.rule_code,
            name=r.name,
            target=r.target,
            operator=r.operator,
            threshold=r.threshold,
            hold_seconds=r.hold_seconds,
            severity=r.severity,
            enabled=r.enabled,
            scope_type=r.scope_type,
            scope_value=r.scope_value,
            updated_at=r.updated_at,
            updated_by=r.updated_by,
        )
        for r in rows
    ]
    return AlarmRuleListResponse(items=items, total=len(items))


@router.put("/rules/{rule_id}", response_model=AlarmRuleUpdateOut)
def update_alarm_rule(
    rule_id: int,
    payload: AlarmRuleUpdateIn,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlarmRuleUpdateOut:
    rule = db.scalar(select(AlarmRule).where(AlarmRule.id == rule_id))
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.threshold = payload.threshold
    rule.hold_seconds = payload.hold_seconds
    rule.severity = payload.level
    rule.enabled = payload.enabled
    rule.updated_by = current_user.username
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)
    sync_rule_to_redis(rule)

    return AlarmRuleUpdateOut(
        item=AlarmRuleItem(
            id=rule.id,
            rule_code=rule.rule_code,
            name=rule.name,
            target=rule.target,
            operator=rule.operator,
            threshold=rule.threshold,
            hold_seconds=rule.hold_seconds,
            severity=rule.severity,
            enabled=rule.enabled,
            scope_type=rule.scope_type,
            scope_value=rule.scope_value,
            updated_at=rule.updated_at,
            updated_by=rule.updated_by,
        ),
        applied=True,
    )
