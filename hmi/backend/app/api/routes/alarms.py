from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import logging
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
from app.services.mqtt_publisher import MqttPublisher
from app.services.tdengine_client import TdengineClient

router = APIRouter(prefix="/alarms", tags=["alarms"])
tdengine = TdengineClient()
mqtt_publisher = MqttPublisher()
log = logging.getLogger(__name__)


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


def _td_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "1", "yes", "y"}:
        return True
    if text in {"false", "f", "0", "no", "n"}:
        return False
    return None


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


def _load_latest_telemetry_alarm_state(device_codes: set[str]) -> dict[str, dict[str, bool]]:
    if not tdengine.enabled() or not device_codes:
        return {}
    code_list = ",".join(f"'{code}'" for code in sorted(device_codes))
    sql = (
        "SELECT device_id, ts, error_c, pwm_duty, saturation_state, sensor_valid, sensor_status, "
        "fault_latched, safety_output_forced_off, fault_reason, sensor_temp_c, software_max_safe_temp_c "
        f"FROM {_tdb()}.telemetry WHERE device_id IN ({code_list}) ORDER BY device_id ASC, ts DESC LIMIT 5000"
    )
    result = tdengine.query(sql)
    latest_by_device: dict[str, dict[str, Any]] = {}
    for row_raw in result.rows:
        row = tdengine.row_to_dict(result.columns, row_raw)
        device_code = str(row.get("device_id") or "")
        if device_code and device_code not in latest_by_device:
            latest_by_device[device_code] = row

    states: dict[str, dict[str, bool]] = {}
    for device_code, row in latest_by_device.items():
        error_c = float(row.get("error_c") or 0.0)
        pwm_duty = float(row.get("pwm_duty") or 0.0)
        saturation_state = str(row.get("saturation_state") or "").strip().lower()
        sensor_valid = _td_bool(row.get("sensor_valid"))
        sensor_status = str(row.get("sensor_status") or "ok").strip().lower()
        fault_latched = bool(_td_bool(row.get("fault_latched")) is True)
        forced_off = bool(_td_bool(row.get("safety_output_forced_off")) is True)
        fault_reason = str(row.get("fault_reason") or "").strip().lower()
        sensor_temp = row.get("sensor_temp_c")
        max_safe = row.get("software_max_safe_temp_c")
        over_temperature = "over_temperature" in fault_reason
        if sensor_temp is not None and max_safe is not None:
            over_temperature = over_temperature or float(sensor_temp) > float(max_safe)
        states[device_code] = {
            "out_of_band": abs(error_c) > 0.5,
            "high_saturation": pwm_duty >= 85.0 or saturation_state in {"high", "saturated"},
            "sensor_invalid": sensor_valid is False or sensor_status not in {"", "ok", "normal", "valid"},
            "fault_latched": fault_latched,
            "safety_output_forced_off": forced_off,
            "over_temperature": over_temperature,
        }
    return states


def _postgres_active_alarm_items(
    *,
    db: Session,
    current_user: User,
    status: str,
    q: Optional[str],
) -> list[ActiveAlarmItem]:
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
    rows = db.execute(base.order_by(DeviceAlarm.created_at.desc(), severity_order.asc())).all()
    return [
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


def _active_alarm_stats(items: list[ActiveAlarmItem]) -> ActiveAlarmStats:
    active_items = [item for item in items if item.status == "Active"]
    return ActiveAlarmStats(
        active_total=len(active_items),
        critical=sum(1 for item in active_items if item.severity == "critical"),
        warning=sum(1 for item in active_items if item.severity == "warning"),
    )


def _sort_alarm_items(items: list[ActiveAlarmItem]) -> list[ActiveAlarmItem]:
    severity_rank = {"critical": 0, "warning": 1}
    return sorted(
        items,
        key=lambda item: (
            0 if item.status == "Active" else 1,
            severity_rank.get(item.severity, 2),
            -item.triggered_at.timestamp(),
        ),
    )


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
            f"SELECT device_id, rule_code, severity, source, reason, ts, alarm_event_type AS alarm_ev_type "
            f"FROM {_tdb()}.alarm_events "
            f"ORDER BY ts DESC LIMIT 5000"
        )
        result = tdengine.query(sql)
        latest_by_key: dict[tuple[str, str], dict] = {}
        for row_raw in result.rows:
            row = tdengine.row_to_dict(result.columns, row_raw)
            device_code = str(row.get("device_id") or "")
            rule_code = str(row.get("rule_code") or "")
            if not device_code or not rule_code:
                continue
            key = (device_code, rule_code)
            # Result is already ordered by ts DESC, keep first as latest.
            if key not in latest_by_key:
                latest_by_key[key] = row

        latest_states = _load_latest_telemetry_alarm_state({device_code for device_code, _rule in latest_by_key})
        all_items: list[ActiveAlarmItem] = []
        for idx, row in enumerate(latest_by_key.values()):
            device_code = str(row.get("device_id") or "")
            rule_code = str(row.get("rule_code") or "alarm")
            event_active = str(row.get("alarm_ev_type") or "").lower() == "triggered"
            is_active = latest_states.get(device_code, {}).get(rule_code, event_active)
            if status == "active" and not is_active:
                continue
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
                    alarm_name=rule_code,
                    severity=severity,
                    triggered_at=tdengine.to_datetime(row.get("ts")),
                    status="Active" if is_active else "Cleared",
                    reason=str(row.get("reason") or "") if is_active else "Current telemetry is back within normal range.",
                    acknowledged=False,
                )
            )

        # TDengine stores the event stream, while the HMI/device API also keeps
        # latched safety alarms in PostgreSQL. Merge both sources so seeded
        # safety scenarios (DEF-110/DEF-111) remain visible when TDengine is on.
        seen_keys = {(item.device_code, item.alarm_name.lower(), item.status) for item in all_items}
        for item in _postgres_active_alarm_items(db=db, current_user=current_user, status=status, q=q):
            key = (item.device_code, item.alarm_name.lower(), item.status)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_items.append(item)

        all_items = _sort_alarm_items(all_items)
        stats = _active_alarm_stats(all_items)
        start = (page - 1) * page_size
        end = start + page_size
        return ActiveAlarmResponse(
            stats=stats,
            items=all_items[start:end],
            total=len(all_items),
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
            f"SELECT ts, device_id, rule_code, severity, source, reason, alarm_event_type AS alarm_ev_type, duration_seconds "
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
            ev_type = str(row.get("alarm_ev_type") or "").lower()
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
    try:
        mqtt_publisher.publish_json(
            topic="edgehub/config/alarm-rules/updated",
            payload_obj={
                "entity": "alarm_rule",
                "action": "updated",
                "rule_id": rule.id,
                "rule_code": rule.rule_code,
                "scope_type": rule.scope_type,
                "scope_value": rule.scope_value,
                "updated_at": rule.updated_at.isoformat(),
                "updated_by": rule.updated_by,
            },
        )
    except Exception:  # noqa: BLE001
        log.exception("failed to publish alarm rule update notification rule_id=%s", rule.id)

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
