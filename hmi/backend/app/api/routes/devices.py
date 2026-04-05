from __future__ import annotations

from datetime import datetime
import time
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
    ControlEvalOut,
    DeviceCreate,
    DeviceListResponse,
    DeviceOut,
    DeviceUpdate,
    MetricOut,
    MetricWindowStatsOut,
    ParameterOut,
    ParameterUpdate,
)
from app.services.mqtt_publisher import MqttPublisher
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import (
    CurrentState,
    DeviceIdentity,
    HistoryPoint,
    HistoryWindow,
    PIDParams,
    RecommendationGenerateInput,
    RecommendationGenerateOutput,
)
from app.services.tdengine_client import TdengineClient

router = APIRouter(prefix="/devices", tags=["devices"])
tdengine = TdengineClient()
mqtt_publisher = MqttPublisher()
recommendation_service = RecommendationService()


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


def _normalize_control_mode(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    mode = str(value).strip().lower()
    if mode in {"pid", "pid_control"}:
        return "pid_control"
    if mode in {"pi", "pi_control"}:
        return "pi_control"
    if mode in {"p", "p_control"}:
        return "p_control"
    return mode


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


def _wait_latest_params_ack(device_code: str, *, after_ms: int, timeout_ms: int = 7000) -> Optional[dict]:
    if not tdengine.enabled():
        return None
    deadline = time.monotonic() + max(0.5, timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        sql = (
            f"SELECT ts, ack_type, success, reason, kp, ki, kd, control_mode "
            f"FROM {_tdb()}.params_ack WHERE device_id='{device_code}' AND ts >= {int(after_ms)} "
            f"ORDER BY ts DESC LIMIT 1"
        )
        result = tdengine.query(sql)
        if result.rows:
            return tdengine.row_to_dict(result.columns, result.rows[0])
        time.sleep(0.3)
    return None


def _latest_params_ack(device_code: str) -> Optional[dict]:
    if not tdengine.enabled():
        return None
    sql = (
        f"SELECT ts, ack_type, success, reason, target_temp_c, kp, ki, kd, control_mode "
        f"FROM {_tdb()}.params_ack WHERE device_id='{device_code}' ORDER BY ts DESC LIMIT 1"
    )
    result = tdengine.query(sql)
    if not result.rows:
        return None
    return tdengine.row_to_dict(result.columns, result.rows[0])


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


def _calc_metric_window_stats(points: list[tuple[int, float]], band: float, steady_window: int) -> MetricWindowStatsOut:
    if len(points) < 2:
        return MetricWindowStatsOut(
            samples=len(points),
            in_band_ratio=0.0,
            total_stable_sec=0,
            longest_stable_sec=0,
            since_last_stable_sec=None,
            has_stable_window=False,
        )

    deltas = [max(0.0, (points[i][0] - points[i - 1][0]) / 1000.0) for i in range(1, len(points))]
    avg_step = sum(deltas) / max(1, len(deltas))
    step_sec = max(1, int(round(avg_step)))

    in_band_count = 0
    total_stable_sec = 0
    longest_stable_sec = 0
    last_stable_end_ms: Optional[int] = None
    run_start = -1

    for i, (_ts_ms, err) in enumerate(points):
        in_band = abs(err) <= band
        if in_band:
            in_band_count += 1
            if run_start < 0:
                run_start = i
            continue
        if run_start >= 0:
            run_len = i - run_start
            if run_len >= steady_window:
                start_ms = points[run_start][0]
                end_ms = points[i - 1][0]
                sec = max(step_sec, int(round((end_ms - start_ms) / 1000.0)) + step_sec)
                total_stable_sec += sec
                longest_stable_sec = max(longest_stable_sec, sec)
                last_stable_end_ms = end_ms
            run_start = -1

    if run_start >= 0:
        run_len = len(points) - run_start
        if run_len >= steady_window:
            start_ms = points[run_start][0]
            end_ms = points[-1][0]
            sec = max(step_sec, int(round((end_ms - start_ms) / 1000.0)) + step_sec)
            total_stable_sec += sec
            longest_stable_sec = max(longest_stable_sec, sec)
            last_stable_end_ms = end_ms

    since_last = None
    if last_stable_end_ms is not None:
        since_last = max(0, int((datetime.utcnow().timestamp() * 1000 - last_stable_end_ms) / 1000))

    return MetricWindowStatsOut(
        samples=len(points),
        in_band_ratio=in_band_count / len(points),
        total_stable_sec=total_stable_sec,
        longest_stable_sec=longest_stable_sec,
        since_last_stable_sec=since_last,
        has_stable_window=total_stable_sec > 0,
    )


def _ts_value_to_ms(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    return int(tdengine.to_datetime(value).timestamp() * 1000)


def _calc_control_eval(
    points: list[tuple[int, float, float, float, float]],
    *,
    current_temp: float,
    target_temp: float,
    pwm_output: float,
    band: float,
    steady_window: int,
    pwm_threshold: float,
    saturation_warn: float,
    saturation_high: float,
    overshoot_limit: float,
) -> ControlEvalOut:
    if points:
        latest = points[-1]
        current_temp = float(latest[1])
        target_temp = float(latest[2])
        pwm_output = float(latest[4])

    error = current_temp - target_temp
    in_band = abs(error) <= band

    window = points[-steady_window:] if steady_window > 0 else points
    steady_window_samples = len(window)
    steady_in_band_samples = sum(1 for _, _, _, err, _ in window if abs(err) <= band)
    steady = steady_window_samples >= steady_window and steady_in_band_samples == steady_window_samples

    overshoot_pct = 0.0
    observed_settling_sec: Optional[float] = None
    saturation_ratio = 0.0
    if points:
        overshoot_pct = max(
            max(0.0, ((temp - target) / max(target, 0.001)) * 100.0) for _, temp, target, _err, _pwm in points
        )
        if window:
            saturation_ratio = sum(1 for _ts, _temp, _target, _err, pwm in window if pwm >= pwm_threshold) / len(window)
        settle_idx = -1
        for i in range(len(points)):
            if all(abs(p[3]) <= band for p in points[i:]):
                settle_idx = i
                break
        if settle_idx > 0:
            observed_settling_sec = max(0.0, (points[settle_idx][0] - points[0][0]) / 1000.0)

    if saturation_ratio >= saturation_high:
        saturation_risk = "High"
    elif saturation_ratio >= saturation_warn:
        saturation_risk = "Medium"
    else:
        saturation_risk = "Low"

    tune_advice = "Keep" if in_band and steady and saturation_risk == "Low" else "Tune"
    if in_band and steady and saturation_risk == "Low" and overshoot_pct <= overshoot_limit:
        result = "On Target"
    elif in_band or saturation_risk != "High":
        result = "Critical"
    else:
        result = "Not Met"

    return ControlEvalOut(
        current_temp=current_temp,
        target_temp=target_temp,
        pwm_output=pwm_output,
        error=error,
        in_band=in_band,
        steady=steady,
        steady_window_samples=steady_window_samples,
        steady_in_band_samples=steady_in_band_samples,
        observed_settling_sec=observed_settling_sec,
        overshoot_pct=overshoot_pct,
        saturation_ratio=saturation_ratio,
        saturation_risk=saturation_risk,
        tune_advice=tune_advice,
        result=result,
    )


def _build_recommendation_input(
    *,
    db: Session,
    device: Device,
    params: DeviceParameter,
    start_ms: int,
    end_ms: int,
    limit: int,
) -> RecommendationGenerateInput:
    points: list[HistoryPoint] = []
    if tdengine.enabled():
        sql = (
            f"SELECT ts, sensor_temp_c, target_temp_c, error_c, pwm_duty "
            f"FROM {_tdb()}.telemetry WHERE device_id='{device.code}' "
            f"AND ts >= {int(start_ms)} AND ts <= {int(end_ms)} "
            f"ORDER BY ts ASC LIMIT {int(limit)}"
        )
        result = tdengine.query(sql)
        for row_raw in result.rows:
            row = tdengine.row_to_dict(result.columns, row_raw)
            points.append(
                HistoryPoint(
                    ts_ms=_ts_value_to_ms(row.get("ts")),
                    current_temp=float(row.get("sensor_temp_c") or 0.0),
                    target_temp=float(row.get("target_temp_c") or 0.0),
                    error=float(row.get("error_c") or 0.0),
                    pwm_output=float(row.get("pwm_duty") or 0.0),
                )
            )
    else:
        rows = db.execute(
            select(
                DeviceMetric.timestamp,
                DeviceMetric.current_temp,
                DeviceMetric.target_temp,
                DeviceMetric.error,
                DeviceMetric.pwm_output,
            )
            .where(
                DeviceMetric.device_id == device.id,
                DeviceMetric.timestamp >= datetime.utcfromtimestamp(start_ms / 1000.0),
                DeviceMetric.timestamp <= datetime.utcfromtimestamp(end_ms / 1000.0),
            )
            .order_by(DeviceMetric.timestamp.asc())
            .limit(limit)
        ).all()
        for ts, temp, target, err, pwm in rows:
            points.append(
                HistoryPoint(
                    ts_ms=int(ts.timestamp() * 1000),
                    current_temp=float(temp or 0.0),
                    target_temp=float(target or 0.0),
                    error=float(err or 0.0),
                    pwm_output=float(pwm or 0.0),
                )
            )

    return RecommendationGenerateInput(
        device=DeviceIdentity(id=device.id, code=device.code, name=device.name),
        current_state=CurrentState(
            current_temp=float(device.current_temp or 0.0),
            target_temp=float(device.target_temp or 0.0),
            pwm_output=float(device.pwm_output or 0.0),
        ),
        current_params=PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd)),
        history_window=HistoryWindow(start_ms=start_ms, end_ms=end_ms, points=points),
        target_band=float(params.target_band),
        steady_window_samples=int(params.steady_window_samples),
        overshoot_limit_pct=float(params.overshoot_limit_pct),
        pwm_saturation_threshold=float(params.pwm_saturation_threshold),
        saturation_warn_ratio=float(params.saturation_warn_ratio),
        saturation_high_ratio=float(params.saturation_high_ratio),
    )


def _dispatch_and_confirm_parameter_update(
    *,
    db: Session,
    device: Device,
    param: DeviceParameter,
    updated_by: str,
    control_mode_for_publish: Optional[str] = None,
) -> DeviceParameter:
    if not mqtt_publisher.enabled():
        raise HTTPException(status_code=503, detail="MQTT publish is disabled; cannot dispatch runtime parameters")

    param.updated_by = updated_by
    param.updated_at = datetime.utcnow()

    dispatch_ms = int(time.time() * 1000)
    publish_result = mqtt_publisher.publish_params_set(
        device_id=device.code,
        target_temp_c=device.target_temp,
        kp=param.kp,
        ki=param.ki,
        kd=param.kd,
        control_mode=control_mode_for_publish,
        control_period_ms=param.sampling_period_ms,
        apply_immediately=True,
    )
    if not publish_result.enabled:
        raise HTTPException(status_code=503, detail="MQTT publish is disabled; parameter dispatch skipped")

    ack = _wait_latest_params_ack(device.code, after_ms=dispatch_ms)
    if ack is None:
        raise HTTPException(status_code=504, detail="Parameter ack timeout: no params_ack received from device")
    if not bool(ack.get("success") is True):
        reason = str(ack.get("reason") or "unknown_reason")
        ack_type = str(ack.get("ack_type") or "unknown_ack_type")
        raise HTTPException(status_code=409, detail=f"Parameter ack failed: {ack_type} ({reason})")

    # Persist runtime-confirmed values so UI and DB reflect actual device state immediately.
    if ack.get("kp") is not None:
        param.kp = float(ack.get("kp") or param.kp)
    if ack.get("ki") is not None:
        param.ki = float(ack.get("ki") or param.ki)
    if ack.get("kd") is not None:
        param.kd = float(ack.get("kd") or param.kd)
    if ack.get("control_mode"):
        param.control_mode = _normalize_control_mode(str(ack.get("control_mode"))) or param.control_mode
    if ack.get("target_temp_c") is not None:
        device.target_temp = float(ack.get("target_temp_c") or device.target_temp)

    db.commit()
    db.refresh(param)
    return param


def _hydrate_runtime_parameters(device: Device, param: DeviceParameter) -> None:
    if not tdengine.enabled():
        return

    # Prefer runtime-confirmed params_ack values to keep UI and AI inputs aligned with device runtime state.
    ack = _latest_params_ack(device.code)
    if ack and bool(ack.get("success") is True):
        if ack.get("kp") is not None:
            param.kp = float(ack.get("kp") or param.kp)
        if ack.get("ki") is not None:
            param.ki = float(ack.get("ki") or param.ki)
        if ack.get("kd") is not None:
            param.kd = float(ack.get("kd") or param.kd)
        if ack.get("control_mode"):
            param.control_mode = _normalize_control_mode(str(ack.get("control_mode"))) or param.control_mode
        if ack.get("target_temp_c") is not None:
            device.target_temp = float(ack.get("target_temp_c") or device.target_temp)
        return

    # Fallback to latest telemetry snapshot when params_ack stream is unavailable.
    sql = (
        f"SELECT ts, target_temp_c, kp, ki, kd, control_mode "
        f"FROM {_tdb()}.telemetry WHERE device_id='{device.code}' ORDER BY ts DESC LIMIT 1"
    )
    result = tdengine.query(sql)
    if not result.rows:
        return
    row = tdengine.row_to_dict(result.columns, result.rows[0])
    if row.get("kp") is not None:
        param.kp = float(row.get("kp") or param.kp)
    if row.get("ki") is not None:
        param.ki = float(row.get("ki") or param.ki)
    if row.get("kd") is not None:
        param.kd = float(row.get("kd") or param.kd)
    if row.get("control_mode"):
        param.control_mode = _normalize_control_mode(str(row.get("control_mode"))) or param.control_mode
    if row.get("target_temp_c") is not None:
        device.target_temp = float(row.get("target_temp_c") or device.target_temp)


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
    start_ms: Optional[int] = Query(default=None, ge=0),
    end_ms: Optional[int] = Query(default=None, ge=0),
    limit: int = Query(default=1000, ge=1, le=20000),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> list[DeviceMetric]:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if start_ms is not None and end_ms is not None and start_ms > end_ms:
        raise HTTPException(status_code=400, detail="start_ms must be <= end_ms")
    if tdengine.enabled():
        where_parts = [f"device_id='{device.code}'"]
        if start_ms is not None:
            where_parts.append(f"ts >= {int(start_ms)}")
        if end_ms is not None:
            where_parts.append(f"ts <= {int(end_ms)}")
        where_sql = " AND ".join(where_parts)
        sql = (
            f"SELECT ts, sensor_temp_c, target_temp_c, error_c, pwm_duty, sensor_valid, fault_latched "
            f"FROM {_tdb()}.telemetry WHERE {where_sql} ORDER BY ts ASC LIMIT {int(limit)}"
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
    query = select(DeviceMetric).where(DeviceMetric.device_id == device_id)
    if start_ms is not None:
        query = query.where(DeviceMetric.timestamp >= datetime.utcfromtimestamp(start_ms / 1000.0))
    if end_ms is not None:
        query = query.where(DeviceMetric.timestamp <= datetime.utcfromtimestamp(end_ms / 1000.0))
    return db.scalars(query.order_by(DeviceMetric.timestamp.asc()).limit(limit)).all()


@router.get("/{device_id}/metrics/stats", response_model=MetricWindowStatsOut)
def get_metric_window_stats(
    device_id: int,
    start_ms: int = Query(..., ge=0),
    end_ms: int = Query(..., ge=0),
    band: float = Query(default=0.5, gt=0, le=20),
    steady_window: int = Query(default=12, ge=1, le=10000),
    limit: int = Query(default=20000, ge=1, le=200000),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> MetricWindowStatsOut:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if start_ms > end_ms:
        raise HTTPException(status_code=400, detail="start_ms must be <= end_ms")

    points: list[tuple[int, float]] = []
    if tdengine.enabled():
        sql = (
            f"SELECT ts, error_c FROM {_tdb()}.telemetry "
            f"WHERE device_id='{device.code}' AND ts >= {int(start_ms)} AND ts <= {int(end_ms)} "
            f"ORDER BY ts ASC LIMIT {int(limit)}"
        )
        result = tdengine.query(sql)
        for row_raw in result.rows:
            row = tdengine.row_to_dict(result.columns, row_raw)
            points.append((_ts_value_to_ms(row.get("ts")), float(row.get("error_c") or 0.0)))
    else:
        rows = db.execute(
            select(DeviceMetric.timestamp, DeviceMetric.error)
            .where(
                DeviceMetric.device_id == device_id,
                DeviceMetric.timestamp >= datetime.utcfromtimestamp(start_ms / 1000.0),
                DeviceMetric.timestamp <= datetime.utcfromtimestamp(end_ms / 1000.0),
            )
            .order_by(DeviceMetric.timestamp.asc())
            .limit(limit)
        ).all()
        for ts, err in rows:
            points.append((int(ts.timestamp() * 1000), float(err or 0.0)))

    return _calc_metric_window_stats(points, band=band, steady_window=steady_window)


@router.get("/{device_id}/control-eval", response_model=ControlEvalOut)
def get_control_eval(
    device_id: int,
    start_ms: Optional[int] = Query(default=None, ge=0),
    end_ms: Optional[int] = Query(default=None, ge=0),
    band: Optional[float] = Query(default=None, gt=0, le=20),
    steady_window: Optional[int] = Query(default=None, ge=1, le=10000),
    pwm_threshold: Optional[float] = Query(default=None, ge=0, le=100),
    saturation_warn: Optional[float] = Query(default=None, ge=0, le=1),
    saturation_high: Optional[float] = Query(default=None, ge=0, le=1),
    overshoot_limit: Optional[float] = Query(default=None, ge=0, le=200),
    limit: int = Query(default=20000, ge=1, le=200000),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> ControlEvalOut:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    band_final = float(band if band is not None else (params.target_band if params else 0.5))
    steady_window_final = int(
        steady_window if steady_window is not None else (params.steady_window_samples if params else 12)
    )
    pwm_threshold_final = float(
        pwm_threshold if pwm_threshold is not None else (params.pwm_saturation_threshold if params else 85.0)
    )
    saturation_warn_final = float(
        saturation_warn if saturation_warn is not None else (params.saturation_warn_ratio if params else 0.3)
    )
    saturation_high_final = float(
        saturation_high if saturation_high is not None else (params.saturation_high_ratio if params else 0.6)
    )
    overshoot_limit_final = float(
        overshoot_limit if overshoot_limit is not None else (params.overshoot_limit_pct if params else 3.0)
    )

    end_ms_final = int(end_ms if end_ms is not None else datetime.utcnow().timestamp() * 1000)
    start_ms_final = int(start_ms if start_ms is not None else end_ms_final - 6 * 60 * 60 * 1000)
    if start_ms_final > end_ms_final:
        raise HTTPException(status_code=400, detail="start_ms must be <= end_ms")

    points: list[tuple[int, float, float, float, float]] = []
    current_temp = float(device.current_temp or 0.0)
    target_temp = float(device.target_temp or 0.0)
    pwm_output = float(device.pwm_output or 0.0)

    if tdengine.enabled():
        sql = (
            f"SELECT ts, sensor_temp_c, target_temp_c, error_c, pwm_duty "
            f"FROM {_tdb()}.telemetry WHERE device_id='{device.code}' "
            f"AND ts >= {start_ms_final} AND ts <= {end_ms_final} "
            f"ORDER BY ts ASC LIMIT {int(limit)}"
        )
        result = tdengine.query(sql)
        for row_raw in result.rows:
            row = tdengine.row_to_dict(result.columns, row_raw)
            points.append(
                (
                    _ts_value_to_ms(row.get("ts")),
                    float(row.get("sensor_temp_c") or 0.0),
                    float(row.get("target_temp_c") or 0.0),
                    float(row.get("error_c") or 0.0),
                    float(row.get("pwm_duty") or 0.0),
                )
            )
    else:
        rows = db.execute(
            select(
                DeviceMetric.timestamp,
                DeviceMetric.current_temp,
                DeviceMetric.target_temp,
                DeviceMetric.error,
                DeviceMetric.pwm_output,
            )
            .where(
                DeviceMetric.device_id == device_id,
                DeviceMetric.timestamp >= datetime.utcfromtimestamp(start_ms_final / 1000.0),
                DeviceMetric.timestamp <= datetime.utcfromtimestamp(end_ms_final / 1000.0),
            )
            .order_by(DeviceMetric.timestamp.asc())
            .limit(limit)
        ).all()
        for ts, temp, target, err, pwm in rows:
            points.append(
                (
                    int(ts.timestamp() * 1000),
                    float(temp or 0.0),
                    float(target or 0.0),
                    float(err or 0.0),
                    float(pwm or 0.0),
                )
            )

    return _calc_control_eval(
        points,
        current_temp=current_temp,
        target_temp=target_temp,
        pwm_output=pwm_output,
        band=band_final,
        steady_window=steady_window_final,
        pwm_threshold=pwm_threshold_final,
        saturation_warn=saturation_warn_final,
        saturation_high=saturation_high_final,
        overshoot_limit=overshoot_limit_final,
    )


@router.get("/{device_id}/parameters", response_model=ParameterOut)
def get_parameters(
    device_id: int,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> DeviceParameter:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not param:
        raise HTTPException(status_code=404, detail="Parameters not found")
    _hydrate_runtime_parameters(device, param)
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

    payload_data = payload.model_dump(exclude_none=True)
    if "control_mode" in payload_data:
        payload_data["control_mode"] = _normalize_control_mode(str(payload_data["control_mode"]))
    if "target_temp" in payload_data:
        device.target_temp = float(payload_data["target_temp"])
        device.updated_at = datetime.utcnow()
        payload_data.pop("target_temp", None)

    for key, value in payload_data.items():
        setattr(param, key, value)
    return _dispatch_and_confirm_parameter_update(
        db=db,
        device=device,
        param=param,
        updated_by=current_user.username,
        control_mode_for_publish=str(payload_data["control_mode"]) if "control_mode" in payload_data else None,
    )


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
            f"SELECT ts, rule_code, severity, source, reason, alarm_event_type AS alarm_ev_type "
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
                    is_active=str(row.get("alarm_ev_type") or "").lower() != "cleared",
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


@router.post("/{device_id}/ai-recommendation/generate", response_model=RecommendationGenerateOutput)
def generate_ai_recommendation(
    device_id: int,
    window_minutes: int = Query(default=60, ge=5, le=24 * 60),
    end_ms: Optional[int] = Query(default=None, ge=0),
    limit: int = Query(default=20000, ge=1, le=200000),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> RecommendationGenerateOutput:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    _apply_live_snapshot(device)

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not params:
        raise HTTPException(status_code=404, detail="Parameters not found")
    _hydrate_runtime_parameters(device, params)

    end_ms_final = int(end_ms if end_ms is not None else datetime.utcnow().timestamp() * 1000)
    start_ms_final = int(end_ms_final - max(1, window_minutes) * 60 * 1000)
    if start_ms_final > end_ms_final:
        raise HTTPException(status_code=400, detail="start_ms must be <= end_ms")

    request_payload = _build_recommendation_input(
        db=db,
        device=device,
        params=params,
        start_ms=start_ms_final,
        end_ms=end_ms_final,
        limit=limit,
    )
    generated = recommendation_service.generate(request_payload)

    reason, suggestion, risk = recommendation_service.to_storage_fields(generated)
    rec = AIRecommendation(
        device_id=device_id,
        reason=reason,
        suggestion=suggestion,
        confidence=float(generated.confidence),
        risk=risk,
        last_run_at=generated.generated_at,
    )
    db.add(rec)
    db.commit()

    return generated


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
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

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
    _hydrate_runtime_parameters(device, params)

    current = PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd))
    recommended = recommendation_service.parse_recommended_params(rec.suggestion, current)
    if not recommended:
        params.updated_by = f"{current_user.username}:ai-noop"
        params.updated_at = datetime.utcnow()
        rec.last_run_at = datetime.utcnow()
        db.commit()
        db.refresh(params)
        return params

    params.kp = round(float(recommended.kp), 4)
    params.ki = round(float(recommended.ki), 4)
    params.kd = round(float(recommended.kd), 4)
    rec.last_run_at = datetime.utcnow()

    return _dispatch_and_confirm_parameter_update(
        db=db,
        device=device,
        param=params,
        updated_by=f"{current_user.username}:ai",
    )
