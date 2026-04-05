from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_accessible_device_ids, get_current_user, get_db_dep, get_user_roles
from app.core.config import settings
from app.models.entities import Device, DeviceMetric, DeviceParameter, DeviceSummary, User
from app.schemas.device import MetricOut
from app.schemas.history import SummaryDetailResponse, SummaryItem, SummaryListResponse
from app.services.tdengine_client import TdengineClient

router = APIRouter(prefix="/history", tags=["history"])
tdengine = TdengineClient()


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


def _tdb() -> str:
    return settings.tdengine_database


@router.get("/summaries", response_model=SummaryListResponse)
def list_summaries(
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(default=None),
    device_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> SummaryListResponse:
    if tdengine.enabled():
        roles = set(get_user_roles(current_user))
        device_query = select(Device)
        if "admin" not in roles:
            ids = get_accessible_device_ids(db, current_user)
            if not ids:
                return SummaryListResponse(items=[], total=0, page=page, page_size=page_size)
            device_query = device_query.where(Device.id.in_(ids))
        devices = db.scalars(device_query).all()
        device_by_code = {d.code: d for d in devices}
        if not device_by_code:
            return SummaryListResponse(items=[], total=0, page=page, page_size=page_size)
        sql = (
            f"SELECT ts, device_id, run_id, window_start_ts, window_end_ts, sample_count, sensor_temp_avg, error_avg, abs_error_max, pwm_duty_avg, flush_reason "
            f"FROM {_tdb()}.telemetry_summary ORDER BY ts DESC LIMIT 5000"
        )
        result = tdengine.query(sql)
        items_all: list[SummaryItem] = []
        for idx, row_raw in enumerate(result.rows):
            row = tdengine.row_to_dict(result.columns, row_raw)
            code = str(row.get("device_id") or "")
            device = device_by_code.get(code)
            if not device:
                continue
            if device_id is not None and device.id != device_id:
                continue
            if q:
                text = f"{device.code} {device.name} {row.get('flush_reason') or ''} {row.get('run_id') or ''}".lower()
                if q.strip().lower() not in text:
                    continue
            items_all.append(
                SummaryItem(
                    id=idx + 1,
                    device_id=device.id,
                    device_code=device.code,
                    device_name=device.name,
                    window_start=tdengine.to_datetime(row.get("window_start_ts")),
                    window_end=tdengine.to_datetime(row.get("window_end_ts")),
                    sample_count=int(row.get("sample_count") or 0),
                    avg_temp=float(row.get("sensor_temp_avg") or 0.0),
                    avg_error=float(row.get("error_avg") or 0.0),
                    max_overshoot_pct=float(row.get("abs_error_max") or 0.0),
                    saturation_ratio=float(row.get("pwm_duty_avg") or 0.0) / 100.0,
                    observed_settling_sec=None,
                    trigger_event=str(row.get("flush_reason") or "steady_state_window"),
                    created_at=tdengine.to_datetime(row.get("ts")),
                )
            )
        total = len(items_all)
        start = (page - 1) * page_size
        end = start + page_size
        return SummaryListResponse(items=items_all[start:end], total=total, page=page, page_size=page_size)

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
    if tdengine.enabled():
        # In TDengine mode, summary_id maps to current page item id; we return latest matching window by offset.
        roles = set(get_user_roles(current_user))
        device_query = select(Device)
        if "admin" not in roles:
            ids = get_accessible_device_ids(db, current_user)
            if not ids:
                raise HTTPException(status_code=404, detail="Summary not found")
            device_query = device_query.where(Device.id.in_(ids))
        devices = db.scalars(device_query).all()
        device_by_code = {d.code: d for d in devices}
        sql = (
            f"SELECT ts, device_id, run_id, window_start_ts, window_end_ts, sample_count, sensor_temp_avg, error_avg, abs_error_max, pwm_duty_avg, flush_reason "
            f"FROM {_tdb()}.telemetry_summary ORDER BY ts DESC LIMIT 5000"
        )
        summary_result = tdengine.query(sql)
        summary_rows = summary_result.rows
        if summary_id < 1 or summary_id > len(summary_rows):
            raise HTTPException(status_code=404, detail="Summary not found")
        row = tdengine.row_to_dict(summary_result.columns, summary_rows[summary_id - 1])
        code = str(row.get("device_id") or "")
        device = device_by_code.get(code)
        if not device:
            raise HTTPException(status_code=403, detail="No access to this summary")
        win_start = tdengine.to_datetime(row.get("window_start_ts"))
        win_end = tdengine.to_datetime(row.get("window_end_ts"))
        metrics_sql = (
            f"SELECT ts, sensor_temp_c, target_temp_c, error_c, pwm_duty, fault_latched "
            f"FROM {_tdb()}.telemetry WHERE device_id='{device.code}' "
            f"AND ts >= {int(win_start.timestamp() * 1000)} AND ts <= {int(win_end.timestamp() * 1000)} "
            f"ORDER BY ts ASC LIMIT 5000"
        )
        metric_result = tdengine.query(metrics_sql)
        metrics: list[MetricOut] = []
        for idx, mr in enumerate(metric_result.rows):
            m = tdengine.row_to_dict(metric_result.columns, mr)
            metrics.append(
                MetricOut(
                    id=idx + 1,
                    timestamp=tdengine.to_datetime(m.get("ts")),
                    current_temp=float(m.get("sensor_temp_c") or 0.0),
                    target_temp=float(m.get("target_temp_c") or 0.0),
                    error=float(m.get("error_c") or 0.0),
                    pwm_output=float(m.get("pwm_duty") or 0.0),
                    status="active",
                    in_spec=abs(float(m.get("error_c") or 0.0)) <= 0.5,
                    is_alarm=bool(m.get("fault_latched") or False),
                )
            )
        summary = SummaryItem(
            id=summary_id,
            device_id=device.id,
            device_code=device.code,
            device_name=device.name,
            window_start=win_start,
            window_end=win_end,
            sample_count=int(row.get("sample_count") or 0),
            avg_temp=float(row.get("sensor_temp_avg") or 0.0),
            avg_error=float(row.get("error_avg") or 0.0),
            max_overshoot_pct=float(row.get("abs_error_max") or 0.0),
            saturation_ratio=float(row.get("pwm_duty_avg") or 0.0) / 100.0,
            observed_settling_sec=None,
            trigger_event=str(row.get("flush_reason") or "steady_state_window"),
            created_at=tdengine.to_datetime(row.get("ts")),
        )
        return SummaryDetailResponse(summary=summary, metrics=metrics)

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
