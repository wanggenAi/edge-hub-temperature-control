from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_accessible_device_ids, get_current_user, get_db_dep, get_user_roles
from app.models.entities import Device, DeviceAlarm, User
from app.schemas.alarm import AlarmListItem, AlarmListResponse

router = APIRouter(prefix="/alarms", tags=["alarms"])


@router.get("", response_model=AlarmListResponse)
def list_alarms(
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> AlarmListResponse:
    roles = set(get_user_roles(current_user))
    base = select(DeviceAlarm, Device).join(Device, DeviceAlarm.device_id == Device.id)

    if "admin" not in roles:
        ids = get_accessible_device_ids(db, current_user)
        if not ids:
            return AlarmListResponse(items=[], total=0, page=page, page_size=page_size)
        base = base.where(DeviceAlarm.device_id.in_(ids))

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

    severity_order = case(
        (DeviceAlarm.level == "critical", 0),
        (DeviceAlarm.level == "warning", 1),
        else_=2,
    )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.execute(
        base.order_by(DeviceAlarm.created_at.desc(), severity_order.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        AlarmListItem(
            id=alarm.id,
            device_id=alarm.device_id,
            device_code=device.code,
            device_name=device.name,
            level=alarm.level,
            title=alarm.title,
            message=alarm.message,
            is_active=alarm.is_active,
            created_at=alarm.created_at,
        )
        for alarm, device in rows
    ]

    return AlarmListResponse(items=items, total=total, page=page, page_size=page_size)
