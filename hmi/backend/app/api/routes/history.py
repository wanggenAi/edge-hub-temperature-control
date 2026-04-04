from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_accessible_device_ids, get_current_user, get_db_dep, get_user_roles
from app.models.entities import Device, DeviceMetric, DeviceParameter, DeviceSummary, User
from app.schemas.history import SummaryDetailResponse, SummaryItem, SummaryListResponse

router = APIRouter(prefix="/history", tags=["history"])


def _calc_observed_settling_sec(metrics: list[DeviceMetric], band: float) -> Optional[float]:
    if len(metrics) < 2:
        return None

    settle_idx = -1
    for i in range(len(metrics)):
        if all(abs(m.error) <= band for m in metrics[i:]):
            settle_idx = i
            break
    if settle_idx < 0:
        return None

    start = metrics[0].timestamp
    end = metrics[settle_idx].timestamp
    return max(0.0, (end - start).total_seconds())


def to_summary_item(summary: DeviceSummary, device: Device, observed_settling_sec: Optional[float] = None) -> SummaryItem:
    return SummaryItem(
        id=summary.id,
        device_id=summary.device_id,
        device_code=device.code,
        device_name=device.name,
        window_start=summary.window_start,
        window_end=summary.window_end,
        sample_count=summary.sample_count,
        avg_temp=summary.avg_temp,
        avg_error=summary.avg_error,
        max_overshoot_pct=summary.max_overshoot_pct,
        saturation_ratio=summary.saturation_ratio,
        observed_settling_sec=observed_settling_sec,
        trigger_event=summary.trigger_event,
        created_at=summary.created_at,
    )


@router.get("/summaries", response_model=SummaryListResponse)
def list_summaries(
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(default=None),
    device_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> SummaryListResponse:
    roles = set(get_user_roles(current_user))
    base = select(DeviceSummary, Device).join(Device, DeviceSummary.device_id == Device.id)

    allowed_ids: Optional[list[int]] = None
    if "admin" not in roles:
        allowed_ids = get_accessible_device_ids(db, current_user)
        if not allowed_ids:
            return SummaryListResponse(items=[], total=0, page=page, page_size=page_size)
        base = base.where(DeviceSummary.device_id.in_(allowed_ids))

    if device_id is not None:
        if allowed_ids is not None and device_id not in allowed_ids:
            return SummaryListResponse(items=[], total=0, page=page, page_size=page_size)
        base = base.where(DeviceSummary.device_id == device_id)

    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                Device.name.ilike(like),
                Device.code.ilike(like),
                DeviceSummary.trigger_event.ilike(like),
            )
        )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(DeviceSummary.window_end.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items: list[SummaryItem] = []
    for summary, device in rows:
        param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == summary.device_id))
        band = param.target_band if param else 0.5
        metrics = db.scalars(
            select(DeviceMetric)
            .where(
                DeviceMetric.device_id == summary.device_id,
                DeviceMetric.timestamp >= summary.window_start,
                DeviceMetric.timestamp <= summary.window_end,
            )
            .order_by(DeviceMetric.timestamp.asc())
        ).all()
        observed_settling_sec = _calc_observed_settling_sec(metrics, band)
        items.append(to_summary_item(summary, device, observed_settling_sec=observed_settling_sec))
    return SummaryListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/summaries/{summary_id}", response_model=SummaryDetailResponse)
def get_summary_details(
    summary_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> SummaryDetailResponse:
    row = db.execute(
        select(DeviceSummary, Device)
        .join(Device, DeviceSummary.device_id == Device.id)
        .where(DeviceSummary.id == summary_id)
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Summary not found")

    summary, device = row
    roles = set(get_user_roles(current_user))
    if "admin" not in roles:
        ids = get_accessible_device_ids(db, current_user)
        if summary.device_id not in ids:
            raise HTTPException(status_code=403, detail="No access to this summary")

    metrics = db.scalars(
        select(DeviceMetric)
        .where(
            DeviceMetric.device_id == summary.device_id,
            DeviceMetric.timestamp >= summary.window_start,
            DeviceMetric.timestamp <= summary.window_end,
        )
        .order_by(DeviceMetric.timestamp.asc())
    ).all()

    param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == summary.device_id))
    band = param.target_band if param else 0.5
    observed_settling_sec = _calc_observed_settling_sec(metrics, band)
    return SummaryDetailResponse(summary=to_summary_item(summary, device, observed_settling_sec=observed_settling_sec), metrics=metrics)
