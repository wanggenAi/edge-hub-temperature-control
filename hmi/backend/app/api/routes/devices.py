from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    AIRecommendationHistoryItemOut,
    AIRecommendationHistoryResponseOut,
    AIRecommendationHistoryStatsOut,
    AIRecommendationOut,
    AITelemetryComparisonOut,
    AITelemetryComparisonPointOut,
    AlarmOut,
    AIPidParamsOut,
    AIPostEffectComparisonOut,
    AIPostEffectMetricsOut,
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
from app.services.ai.ai_runtime_service import get_ai_runtime_service
from app.services.ai.post_effect_evaluator import ObservedTelemetryPoint, PostEffectEvaluator
from app.services.ai.preview_simulator import (
    PREVIEW_DEFAULT_AMBIENT_TEMP,
    PREVIEW_DEFAULT_COOLING_COEFF,
    PREVIEW_DEFAULT_HEATING_GAIN,
    PREVIEW_DEFAULT_HORIZON_SEC,
    PREVIEW_DEFAULT_STEP_SEC,
    PreviewSimulationConfig,
    RecommendationPreviewSimulator,
)
from app.services.ai.schemas import (
    CurrentState,
    DeviceIdentity,
    HistoryPoint,
    HistoryWindow,
    PIDParams,
    RecommendationGenerateInput,
    RecommendationGenerateOutput,
    RecommendationActualEvaluationOutput,
    RecommendationActualEvaluationRequest,
    RecommendationPreviewOutput,
    PreviewMetrics,
)
from app.services.tdengine_client import TdengineClient

router = APIRouter(prefix="/devices", tags=["devices"])
tdengine = TdengineClient()
mqtt_publisher = MqttPublisher()
recommendation_service = RecommendationService()
ai_runtime_service = get_ai_runtime_service()
preview_simulator = RecommendationPreviewSimulator()
post_effect_evaluator = PostEffectEvaluator()
logger = logging.getLogger(__name__)


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


def _wait_latest_params_ack(device_code: str, *, after_ms: int, timeout_ms: int = 5000) -> Optional[dict]:
    if not tdengine.enabled():
        return None
    # When producer/consumer clocks are slightly skewed, strict ts>=after_ms may miss
    # a valid ack. Keep a bounded fallback check by matching latest ack payload values.
    strict_after_ms = int(after_ms)
    deadline = time.monotonic() + max(0.5, timeout_ms / 1000.0)
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        sql = (
            f"SELECT ts, ack_type, success, reason, kp, ki, kd, control_mode "
            f"FROM {_tdb()}.params_ack WHERE device_id='{device_code}' AND ts >= {strict_after_ms} "
            f"ORDER BY ts DESC LIMIT 1"
        )
        result = tdengine.query(sql)
        if result.rows:
            row = tdengine.row_to_dict(result.columns, result.rows[0])
            logger.warning(
                "[ACK-STRICT] device=%s matched ts>=%s ack_ts=%s success=%s attempts=%s",
                device_code,
                strict_after_ms,
                row.get("ts"),
                row.get("success"),
                attempts,
            )
            return row
        time.sleep(0.15)
    logger.warning("[ACK-STRICT] device=%s timeout waiting ts>=%s attempts=%s", device_code, strict_after_ms, attempts)
    return None


def _wait_latest_params_ack_relaxed(
    *,
    device_code: str,
    after_ms: int,
    expected_kp: float,
    expected_ki: float,
    expected_kd: float,
    expected_control_mode: Optional[str],
    timeout_ms: int = 5000,
    max_clock_skew_ms: int = 120000,
) -> Optional[dict]:
    ack = _wait_latest_params_ack(device_code, after_ms=after_ms, timeout_ms=timeout_ms)
    if ack is not None:
        return ack
    if not tdengine.enabled():
        return None

    # Fallback: accept latest ack if values match target params and row is recent.
    sql = (
        f"SELECT ts, ack_type, success, reason, kp, ki, kd, control_mode "
        f"FROM {_tdb()}.params_ack WHERE device_id='{device_code}' ORDER BY ts DESC LIMIT 1"
    )
    result = tdengine.query(sql)
    if not result.rows:
        logger.warning("[ACK-RELAX] device=%s no latest ack row", device_code)
        return None
    row = tdengine.row_to_dict(result.columns, result.rows[0])
    ts_ms = _ts_value_to_ms(row.get("ts"))
    lower_bound = int(after_ms) - max(0, int(max_clock_skew_ms))
    if ts_ms < lower_bound:
        logger.warning(
            "[ACK-RELAX] device=%s latest ack too old ack_ts=%s lower_bound=%s",
            device_code,
            ts_ms,
            lower_bound,
        )
        return None

    kp = float(row.get("kp") or 0.0)
    ki = float(row.get("ki") or 0.0)
    kd = float(row.get("kd") or 0.0)
    tol = max(0.001, float(settings.recommendation_float_tolerance))
    same_params = (
        abs(kp - float(expected_kp)) <= tol
        and abs(ki - float(expected_ki)) <= tol
        and abs(kd - float(expected_kd)) <= tol
    )
    if not same_params:
        logger.warning(
            "[ACK-RELAX] device=%s latest ack param mismatch expected=(%.4f,%.4f,%.4f) got=(%.4f,%.4f,%.4f)",
            device_code,
            float(expected_kp),
            float(expected_ki),
            float(expected_kd),
            kp,
            ki,
            kd,
        )
        return None

    if expected_control_mode:
        got_mode = _normalize_control_mode(str(row.get("control_mode") or "")) or ""
        exp_mode = _normalize_control_mode(expected_control_mode) or ""
        if got_mode and exp_mode and got_mode != exp_mode:
            logger.warning(
                "[ACK-RELAX] device=%s latest ack mode mismatch expected=%s got=%s",
                device_code,
                exp_mode,
                got_mode,
            )
            return None
    logger.warning(
        "[ACK-RELAX] device=%s fallback matched ack_ts=%s success=%s",
        device_code,
        row.get("ts"),
        row.get("success"),
    )
    return row


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


def _coerce_post_effect_metrics(value: object) -> Optional[AIPostEffectMetricsOut]:
    if not isinstance(value, dict):
        return None
    try:
        return AIPostEffectMetricsOut.model_validate(value)
    except Exception:
        return None


def _coerce_post_effect_comparison(value: object) -> Optional[AIPostEffectComparisonOut]:
    if not isinstance(value, dict):
        return None
    try:
        return AIPostEffectComparisonOut.model_validate(value)
    except Exception:
        return None


def _derive_effect_outcome(comparison: Optional[AIPostEffectComparisonOut]) -> str:
    if comparison is None:
        return "pending"

    weighted_deltas: list[int] = []
    if comparison.in_band_ratio_delta is not None:
        if comparison.in_band_ratio_delta > 0.0001:
            weighted_deltas.append(1)
        elif comparison.in_band_ratio_delta < -0.0001:
            weighted_deltas.append(-1)
    for value in (
        comparison.overshoot_c_delta,
        comparison.settling_sec_delta,
        comparison.mean_abs_error_delta,
        comparison.saturation_ratio_delta,
        comparison.temp_swing_delta,
    ):
        if value is None:
            continue
        if value < -0.0001:
            weighted_deltas.append(1)
        elif value > 0.0001:
            weighted_deltas.append(-1)

    if not weighted_deltas:
        return "unchanged"
    score = sum(weighted_deltas)
    if score > 0:
        return "improved"
    if score < 0:
        return "worse"
    return "unchanged"


def _build_ai_history_item(
    *,
    rec: AIRecommendation,
    device: Device,
    fallback_current_params: PIDParams,
) -> AIRecommendationHistoryItemOut:
    parsed = recommendation_service.build_output_from_storage(
        reason=rec.reason,
        suggestion=rec.suggestion,
        risk=rec.risk,
        confidence=float(rec.confidence),
        generated_at=rec.last_run_at,
        fallback_current_params=fallback_current_params,
    )
    meta = recommendation_service.read_storage_metadata(rec.suggestion)
    summary = _coerce_post_effect_metrics(meta.get("pe"))
    comparison_before = _coerce_post_effect_comparison(meta.get("pecb"))
    comparison_preview = _coerce_post_effect_comparison(meta.get("pecp"))
    actual_effect_evaluated = bool(meta.get("aee") or summary is not None)
    insufficient_data = bool(meta.get("pei") is True)
    observation_window_minutes = None
    if isinstance(meta.get("pew"), (int, float, str)):
        try:
            observation_window_minutes = int(meta.get("pew"))
        except (TypeError, ValueError):
            observation_window_minutes = None
    evaluated_at = _parse_iso_utc(meta.get("pea"))

    problem_type = parsed.problem_type.value if parsed else (recommendation_service.parse_reason_fields(rec.reason)[0] or "unknown")
    expected_effect = parsed.expected_effect.value if parsed else recommendation_service.parse_reason_fields(rec.reason)[1]
    risk_level = parsed.risk_level.value if parsed else recommendation_service.parse_risk_fields(rec.risk)[0]
    history_state_raw = parsed.history_state if parsed else (str(meta.get("hs")) if meta.get("hs") is not None else None)
    history_state = str(history_state_raw or "").strip().lower()
    if history_state not in {"generated", "previewed", "applied", "dismissed", "expired"}:
        history_state = ""
    applied_at = _parse_iso_utc(meta.get("apa"))
    if applied_at is None and history_state == "applied" and not actual_effect_evaluated:
        applied_at = parsed.last_accessed_at if parsed else _parse_iso_utc(meta.get("la"))
    if not history_state:
        if applied_at is not None or actual_effect_evaluated:
            history_state = "applied"
        else:
            history_state = "generated"
    effect_outcome = _derive_effect_outcome(comparison_before)
    if history_state != "applied" and not actual_effect_evaluated:
        effect_outcome = "pending"

    return AIRecommendationHistoryItemOut(
        recommendation_id=rec.id,
        device_id=device.id,
        device_code=device.code,
        device_name=device.name,
        device_line=device.line,
        device_location=device.location,
        problem_type=problem_type,
        expected_effect=expected_effect,
        risk_level=risk_level,
        confidence=float(rec.confidence),
        requires_confirmation=bool(parsed.requires_confirmation) if parsed else False,
        history_state=history_state,
        generated_at=rec.last_run_at,
        fingerprint=parsed.fingerprint if parsed else (str(meta.get("fp")) if meta.get("fp") is not None else None),
        reused_count=int(parsed.reused_count or 0) if parsed else int(meta.get("rc") or 0),
        last_generate_reused=parsed.last_generate_reused if parsed else (bool(meta.get("lgr")) if isinstance(meta.get("lgr"), bool) else None),
        last_accessed_at=parsed.last_accessed_at if parsed else _parse_iso_utc(meta.get("la")),
        applied_at=applied_at,
        current_params=None
        if not parsed
        else AIPidParamsOut(kp=float(parsed.current_params.kp), ki=float(parsed.current_params.ki), kd=float(parsed.current_params.kd)),
        recommended_params=None
        if not parsed
        else AIPidParamsOut(
            kp=float(parsed.recommended_params.kp),
            ki=float(parsed.recommended_params.ki),
            kd=float(parsed.recommended_params.kd),
        ),
        delta=None
        if not parsed
        else AIPidParamsOut(kp=float(parsed.delta.kp), ki=float(parsed.delta.ki), kd=float(parsed.delta.kd)),
        actual_effect_evaluated=actual_effect_evaluated,
        insufficient_data=insufficient_data,
        evaluated_at=evaluated_at,
        observation_window_minutes=observation_window_minutes,
        post_effect_summary=summary,
        comparison_to_before=comparison_before,
        comparison_to_preview=comparison_preview,
        effect_outcome=effect_outcome,
    )


def _find_recent_success_ack_for_target(
    *,
    device_code: str,
    target: PIDParams,
    expected_control_mode: Optional[str],
    tolerance: float,
    lookback_ms: int = 20 * 60 * 1000,
    limit: int = 50,
) -> Optional[dict]:
    if not tdengine.enabled():
        return None
    now_ms = int(time.time() * 1000)
    min_ts = max(0, now_ms - max(1000, int(lookback_ms)))
    sql = (
        f"SELECT ts, ack_type, success, reason, target_temp_c, kp, ki, kd, control_mode "
        f"FROM {_tdb()}.params_ack WHERE device_id='{device_code}' AND ts >= {min_ts} "
        f"ORDER BY ts DESC LIMIT {max(1, int(limit))}"
    )
    result = tdengine.query(sql)
    if not result.rows:
        return None
    tol = max(0.001, float(tolerance))
    exp_mode = _normalize_control_mode(expected_control_mode) if expected_control_mode else None
    for raw in result.rows:
        row = tdengine.row_to_dict(result.columns, raw)
        if not bool(row.get("success") is True):
            continue
        kp = float(row.get("kp") or 0.0)
        ki = float(row.get("ki") or 0.0)
        kd = float(row.get("kd") or 0.0)
        if abs(kp - float(target.kp)) > tol or abs(ki - float(target.ki)) > tol or abs(kd - float(target.kd)) > tol:
            continue
        if exp_mode:
            got_mode = _normalize_control_mode(str(row.get("control_mode") or ""))
            if got_mode and got_mode != exp_mode:
                continue
        return row
    return None


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


def _utc_naive_from_ms(ms: int) -> datetime:
    # Use timezone-aware conversion to avoid deprecated utcfromtimestamp,
    # then normalize to naive UTC to match current DB datetime column semantics.
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def _utc_naive_from_sec(sec: float) -> datetime:
    return datetime.fromtimestamp(float(sec), tz=timezone.utc).replace(tzinfo=None)


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
    # Fallback to relational history when TDengine has no rows for this device/window.
    if not points:
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
                DeviceMetric.timestamp >= _utc_naive_from_ms(start_ms),
                DeviceMetric.timestamp <= _utc_naive_from_ms(end_ms),
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


def _pid_is_effectively_applied(
    *,
    current: PIDParams,
    target: PIDParams,
    tolerance: float,
) -> bool:
    tol = max(0.0, float(tolerance))
    return (
        abs(float(current.kp) - float(target.kp)) <= tol
        and abs(float(current.ki) - float(target.ki)) <= tol
        and abs(float(current.kd) - float(target.kd)) <= tol
    )


def _recommendation_has_actionable_delta(output: RecommendationGenerateOutput, *, tolerance: float) -> bool:
    if output.problem_type.value == "normal":
        return False
    delta = output.delta
    tol = max(0.0, float(tolerance))
    return bool(
        abs(float(delta.kp)) > tol
        or abs(float(delta.ki)) > tol
        or abs(float(delta.kd)) > tol
    )


def _is_demo_preview_device(device_code: str) -> bool:
    code = str(device_code or "").upper()
    return code.startswith("TC-PREVIEW-")


def _build_demo_mock_recommendation(*, device: Device, params: DeviceParameter) -> RecommendationGenerateOutput:
    code = str(device.code or "").upper()
    current = PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd))
    if "SLOW" in code:
        recommended = PIDParams(
            kp=round(max(1.5, current.kp * 1.9), 4),
            ki=round(max(0.08, current.ki * 1.75), 4),
            kd=round(max(0.08, current.kd + 0.12), 4),
        )
        problem_type = "slow_response"
        expected_effect = "speed_up_response"
        risk_level = "Medium"
        confidence = 0.88
        requires_confirmation = True
        evidence = {
            "rule_slow_response": True,
            "rule_steady_state_error": True,
            "rule_oscillation": False,
            "rule_overshoot_high": False,
            "rule_saturation_limited": False,
            "mean_error": -3.85,
            "mean_abs_error": 4.12,
            "error_std": 0.74,
            "temp_swing": 2.16,
            "pwm_mean": 89.4,
            "pwm_max": 100.0,
            "zero_crossings": 0,
            "in_band_ratio": 0.06,
            "overshoot_pct": 0.0,
            "settling_sec": None,
            "saturation_ratio": 0.64,
        }
    elif "OSC" in code:
        recommended = PIDParams(
            kp=round(max(0.8, current.kp * 0.72), 4),
            ki=round(max(0.03, current.ki * 0.55), 4),
            kd=round(max(0.2, current.kd + 0.18), 4),
        )
        problem_type = "oscillation"
        expected_effect = "reduce_oscillation"
        risk_level = "Medium"
        confidence = 0.84
        requires_confirmation = True
        evidence = {
            "rule_slow_response": False,
            "rule_steady_state_error": False,
            "rule_oscillation": True,
            "rule_overshoot_high": True,
            "rule_saturation_limited": False,
            "mean_error": 0.11,
            "mean_abs_error": 1.22,
            "error_std": 0.96,
            "temp_swing": 3.48,
            "pwm_mean": 57.9,
            "pwm_max": 91.7,
            "zero_crossings": 29,
            "in_band_ratio": 0.31,
            "overshoot_pct": 5.2,
            "settling_sec": None,
            "saturation_ratio": 0.22,
        }
    else:
        recommended = PIDParams(
            kp=round(max(0.6, current.kp * 1.35), 4),
            ki=round(max(0.05, current.ki * 1.4), 4),
            kd=round(max(0.05, current.kd + 0.08), 4),
        )
        problem_type = "steady_state_error"
        expected_effect = "reduce_steady_state_error"
        risk_level = "Low"
        confidence = 0.82
        requires_confirmation = False
        evidence = {
            "rule_slow_response": False,
            "rule_steady_state_error": True,
            "rule_oscillation": False,
            "rule_overshoot_high": False,
            "rule_saturation_limited": False,
            "mean_error": -1.12,
            "mean_abs_error": 1.2,
            "error_std": 0.42,
            "temp_swing": 1.34,
            "pwm_mean": 73.0,
            "pwm_max": 92.0,
            "zero_crossings": 1,
            "in_band_ratio": 0.44,
            "overshoot_pct": 0.3,
            "settling_sec": None,
            "saturation_ratio": 0.26,
        }
    delta = PIDParams(
        kp=round(recommended.kp - current.kp, 4),
        ki=round(recommended.ki - current.ki, 4),
        kd=round(recommended.kd - current.kd, 4),
    )
    return RecommendationGenerateOutput(
        problem_type=problem_type,
        confidence=confidence,
        risk_level=risk_level,
        requires_confirmation=requires_confirmation,
        current_params=current,
        recommended_params=recommended,
        delta=delta,
        expected_effect=expected_effect,
        evidence=evidence,
        generated_at=datetime.utcnow(),
    )


def _parse_iso_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _load_observed_points(
    *,
    db: Session,
    device: Device,
    start_ms: int,
    end_ms: int,
    limit: int,
) -> list[ObservedTelemetryPoint]:
    points: list[ObservedTelemetryPoint] = []
    if tdengine.enabled():
        sql = (
            f"SELECT ts, sensor_temp_c, target_temp_c, error_c, pwm_duty, saturation_state "
            f"FROM {_tdb()}.telemetry WHERE device_id='{device.code}' "
            f"AND ts >= {int(start_ms)} AND ts <= {int(end_ms)} "
            f"ORDER BY ts ASC LIMIT {int(limit)}"
        )
        result = tdengine.query(sql)
        for row_raw in result.rows:
            row = tdengine.row_to_dict(result.columns, row_raw)
            temp = float(row.get("sensor_temp_c") or 0.0)
            target = float(row.get("target_temp_c") or 0.0)
            error_raw = row.get("error_c")
            error = float(error_raw) if error_raw is not None else (target - temp)
            points.append(
                ObservedTelemetryPoint(
                    ts_ms=_ts_value_to_ms(row.get("ts")),
                    temp=temp,
                    target_temp=target,
                    error=error,
                    pwm_output=float(row.get("pwm_duty") or 0.0),
                    saturation_state=(None if row.get("saturation_state") is None else str(row.get("saturation_state"))),
                )
            )
    if points:
        return points

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
            DeviceMetric.timestamp >= _utc_naive_from_ms(start_ms),
            DeviceMetric.timestamp <= _utc_naive_from_ms(end_ms),
        )
        .order_by(DeviceMetric.timestamp.asc())
        .limit(limit)
    ).all()
    for ts, temp, target, err, pwm in rows:
        temp_v = float(temp or 0.0)
        target_v = float(target or 0.0)
        error_v = float(err) if err is not None else (target_v - temp_v)
        points.append(
            ObservedTelemetryPoint(
                ts_ms=int(ts.timestamp() * 1000),
                temp=temp_v,
                target_temp=target_v,
                error=error_v,
                pwm_output=float(pwm or 0.0),
                saturation_state=None,
            )
        )
    return points


def _downsample_points(points: list[ObservedTelemetryPoint], limit: int) -> list[ObservedTelemetryPoint]:
    if limit <= 0 or len(points) <= limit:
        return points
    if limit == 1:
        return [points[-1]]
    step = (len(points) - 1) / float(limit - 1)
    sampled: list[ObservedTelemetryPoint] = []
    for idx in range(limit):
        source_idx = int(round(idx * step))
        source_idx = max(0, min(len(points) - 1, source_idx))
        sampled.append(points[source_idx])
    return sampled


def _curve_point_from_observed(point: ObservedTelemetryPoint, *, anchor_ms: int) -> AITelemetryComparisonPointOut:
    return AITelemetryComparisonPointOut(
        relative_time_min=round((int(point.ts_ms) - int(anchor_ms)) / 60000.0, 4),
        temp=float(point.temp),
        target_temp=float(point.target_temp),
        timestamp=_utc_naive_from_ms(int(point.ts_ms)),
    )


def _extract_preview_curve_from_meta(meta: dict[str, object], *, anchor_ms: int) -> list[AITelemetryComparisonPointOut]:
    pvs = meta.get("pvs")
    if not isinstance(pvs, dict):
        return []

    raw_curve = pvs.get("recommended_curve")
    if not isinstance(raw_curve, list):
        raw_curve = pvs.get("preview_curve")
    if not isinstance(raw_curve, list):
        raw_curve = pvs.get("curve")
    if not isinstance(raw_curve, list):
        return []

    out: list[AITelemetryComparisonPointOut] = []
    for item in raw_curve:
        if not isinstance(item, dict):
            continue
        time_s = _as_float_or_none(item.get("time_s"))
        if time_s is None:
            time_s = _as_float_or_none(item.get("time_sec"))
        if time_s is None:
            time_min = _as_float_or_none(item.get("relative_time_min"))
            if time_min is not None:
                time_s = float(time_min) * 60.0
        temp = _as_float_or_none(item.get("temp"))
        if temp is None:
            continue
        target = _as_float_or_none(item.get("target_temp"))
        ts_ms = int(anchor_ms + max(0.0, float(time_s or 0.0)) * 1000.0)
        out.append(
            AITelemetryComparisonPointOut(
                relative_time_min=round(max(0.0, float(time_s or 0.0)) / 60.0, 4),
                temp=float(temp),
                target_temp=None if target is None else float(target),
                timestamp=_utc_naive_from_ms(ts_ms),
            )
        )
    return out


def _build_preview_curve_fallback(
    *,
    rec: AIRecommendation,
    meta: dict[str, object],
    device: Device,
    params: DeviceParameter,
    anchor_ms: int,
    observation_window_minutes: int,
    baseline_points: list[ObservedTelemetryPoint],
) -> list[AITelemetryComparisonPointOut]:
    parsed = recommendation_service.parse_suggestion_payload(rec.suggestion) or {}
    parsed_current = parsed.get("current_params")
    baseline_params = PIDParams(
        kp=float(parsed_current.get("kp")) if isinstance(parsed_current, dict) and parsed_current.get("kp") is not None else float(params.kp),
        ki=float(parsed_current.get("ki")) if isinstance(parsed_current, dict) and parsed_current.get("ki") is not None else float(params.ki),
        kd=float(parsed_current.get("kd")) if isinstance(parsed_current, dict) and parsed_current.get("kd") is not None else float(params.kd),
    )
    recommended_params = recommendation_service.parse_recommended_params(rec.suggestion, baseline_params)
    if recommended_params is None:
        return []

    initial_temp = float(baseline_points[-1].temp) if baseline_points else float(device.current_temp)
    target_temp = float(baseline_points[-1].target_temp) if baseline_points else float(device.target_temp)

    horizon_sec = max(120, int(observation_window_minutes) * 60)
    step_sec = 10
    cfg = PreviewSimulationConfig(
        horizon_sec=horizon_sec,
        step_sec=step_sec,
        ambient_temp=float(meta.get("preview_ambient_temp") or PREVIEW_DEFAULT_AMBIENT_TEMP),
        heating_gain=float(meta.get("preview_heating_gain") or PREVIEW_DEFAULT_HEATING_GAIN),
        cooling_coeff=float(meta.get("preview_cooling_coeff") or PREVIEW_DEFAULT_COOLING_COEFF),
        target_band=float(params.target_band),
        pwm_saturation_threshold=float(params.pwm_saturation_threshold),
        control_mode=str(params.control_mode or "pid_control"),
    )
    preview_output = preview_simulator.run(
        current_temp=initial_temp,
        target_temp=target_temp,
        baseline_params=baseline_params,
        recommended_params=recommended_params,
        config=cfg,
    )
    out: list[AITelemetryComparisonPointOut] = []
    for point in preview_output.recommended_curve:
        ts_ms = int(anchor_ms + int(point.time_s) * 1000)
        out.append(
            AITelemetryComparisonPointOut(
                relative_time_min=round(float(point.time_s) / 60.0, 4),
                temp=float(point.temp),
                target_temp=float(point.target_temp),
                timestamp=_utc_naive_from_ms(ts_ms),
            )
        )
    return out


def _as_float_or_none(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_metrics_from_evidence(evidence: Optional[dict[str, object]]) -> Optional[PreviewMetrics]:
    if not isinstance(evidence, dict) or not evidence:
        return None
    in_band_ratio = _as_float_or_none(evidence.get("in_band_ratio"))
    mean_abs_error = _as_float_or_none(evidence.get("mean_abs_error"))
    saturation_ratio = _as_float_or_none(evidence.get("saturation_ratio"))
    temp_swing = _as_float_or_none(evidence.get("temp_swing"))
    if in_band_ratio is None or mean_abs_error is None or saturation_ratio is None or temp_swing is None:
        return None
    overshoot_c = _as_float_or_none(evidence.get("overshoot_c"))
    if overshoot_c is None:
        overshoot_c = 0.0
    settling_sec = _as_float_or_none(evidence.get("settling_sec"))
    return PreviewMetrics(
        in_band_ratio=float(in_band_ratio),
        overshoot_c=float(overshoot_c),
        settling_sec=None if settling_sec is None else float(settling_sec),
        mean_abs_error=float(mean_abs_error),
        saturation_ratio=float(saturation_ratio),
        temp_swing=float(temp_swing),
    )


def _extract_preview_recommended_metrics(meta: dict[str, object]) -> Optional[PreviewMetrics]:
    preview_summary = meta.get("pvs")
    if not isinstance(preview_summary, dict):
        return None
    recommended = preview_summary.get("recommended_metrics")
    if not isinstance(recommended, dict):
        return None
    in_band_ratio = _as_float_or_none(recommended.get("in_band_ratio"))
    overshoot_c = _as_float_or_none(recommended.get("overshoot_c"))
    mean_abs_error = _as_float_or_none(recommended.get("mean_abs_error"))
    saturation_ratio = _as_float_or_none(recommended.get("saturation_ratio"))
    temp_swing = _as_float_or_none(recommended.get("temp_swing"))
    if (
        in_band_ratio is None
        or overshoot_c is None
        or mean_abs_error is None
        or saturation_ratio is None
        or temp_swing is None
    ):
        return None
    settling_sec = _as_float_or_none(recommended.get("settling_sec"))
    return PreviewMetrics(
        in_band_ratio=float(in_band_ratio),
        overshoot_c=float(overshoot_c),
        settling_sec=None if settling_sec is None else float(settling_sec),
        mean_abs_error=float(mean_abs_error),
        saturation_ratio=float(saturation_ratio),
        temp_swing=float(temp_swing),
    )


def _dispatch_and_confirm_parameter_update(
    *,
    db: Session,
    device: Device,
    param: DeviceParameter,
    updated_by: str,
    control_mode_for_publish: Optional[str] = None,
) -> DeviceParameter:
    flow_t0 = time.monotonic()
    if not mqtt_publisher.enabled():
        raise HTTPException(status_code=503, detail="MQTT publish is disabled; cannot dispatch runtime parameters")

    param.updated_by = updated_by
    param.updated_at = datetime.utcnow()

    dispatch_ms = int(time.time() * 1000)
    logger.warning(
        "[APPLY-DISPATCH] device=%s dispatch_ms=%s target=(%.4f,%.4f,%.4f) mode=%s",
        device.code,
        dispatch_ms,
        float(param.kp),
        float(param.ki),
        float(param.kd),
        str(control_mode_for_publish or param.control_mode or "pid_control"),
    )
    publish_t0 = time.monotonic()
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
    logger.warning(
        "[APPLY-DISPATCH] device=%s publish_done enabled=%s topic=%s elapsed_ms=%s",
        device.code,
        publish_result.enabled,
        publish_result.topic,
        int((time.monotonic() - publish_t0) * 1000),
    )
    if not publish_result.enabled:
        logger.warning("[APPLY-DISPATCH] device=%s mqtt publish disabled", device.code)
        raise HTTPException(status_code=503, detail="MQTT publish is disabled; parameter dispatch skipped")

    ack_wait_t0 = time.monotonic()
    ack = _wait_latest_params_ack_relaxed(
        device_code=device.code,
        after_ms=dispatch_ms,
        expected_kp=float(param.kp),
        expected_ki=float(param.ki),
        expected_kd=float(param.kd),
        expected_control_mode=control_mode_for_publish or str(param.control_mode or "pid_control"),
    )
    logger.warning(
        "[APPLY-ACK] device=%s wait_done elapsed_ms=%s",
        device.code,
        int((time.monotonic() - ack_wait_t0) * 1000),
    )
    if ack is None:
        logger.warning("[APPLY-ACK] device=%s timeout after dispatch_ms=%s", device.code, dispatch_ms)
        raise HTTPException(status_code=504, detail="Parameter ack timeout: no params_ack received from device")
    if not bool(ack.get("success") is True):
        reason = str(ack.get("reason") or "unknown_reason")
        ack_type = str(ack.get("ack_type") or "unknown_ack_type")
        logger.warning("[APPLY-ACK] device=%s failed ack_type=%s reason=%s", device.code, ack_type, reason)
        raise HTTPException(status_code=409, detail=f"Parameter ack failed: {ack_type} ({reason})")
    logger.warning(
        "[APPLY-ACK] device=%s success ack_ts=%s ack_type=%s kp=%s ki=%s kd=%s mode=%s",
        device.code,
        ack.get("ts"),
        ack.get("ack_type"),
        ack.get("kp"),
        ack.get("ki"),
        ack.get("kd"),
        ack.get("control_mode"),
    )
    logger.warning("[APPLY] device=%s total_elapsed_ms=%s", device.code, int((time.monotonic() - flow_t0) * 1000))

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
        query = query.where(DeviceMetric.timestamp >= _utc_naive_from_ms(start_ms))
    if end_ms is not None:
        query = query.where(DeviceMetric.timestamp <= _utc_naive_from_ms(end_ms))
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
                DeviceMetric.timestamp >= _utc_naive_from_ms(start_ms),
                DeviceMetric.timestamp <= _utc_naive_from_ms(end_ms),
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
                DeviceMetric.timestamp >= _utc_naive_from_ms(start_ms_final),
                DeviceMetric.timestamp <= _utc_naive_from_ms(end_ms_final),
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


@router.get("/ai/recommendations/history", response_model=AIRecommendationHistoryResponseOut)
def list_ai_recommendation_history(
    limit: int = Query(default=100, ge=1, le=500),
    device_id: Optional[int] = Query(default=None, ge=1),
    start_ms: Optional[int] = Query(default=None, ge=0),
    end_ms: Optional[int] = Query(default=None, ge=0),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> AIRecommendationHistoryResponseOut:
    roles = set(get_user_roles(current_user))
    if device_id is not None:
        require_device_access(device_id, db, current_user)

    stmt = (
        select(AIRecommendation, Device)
        .join(Device, Device.id == AIRecommendation.device_id)
        .order_by(AIRecommendation.last_run_at.desc())
        .limit(limit)
    )
    if start_ms is not None:
        stmt = stmt.where(AIRecommendation.last_run_at >= _utc_naive_from_sec(start_ms / 1000.0))
    if end_ms is not None:
        stmt = stmt.where(AIRecommendation.last_run_at <= _utc_naive_from_sec(end_ms / 1000.0))
    if device_id is not None:
        stmt = stmt.where(AIRecommendation.device_id == device_id)
    elif "admin" not in roles:
        accessible_ids = get_accessible_device_ids(db, current_user)
        if not accessible_ids:
            return AIRecommendationHistoryResponseOut(
                items=[],
                stats=AIRecommendationHistoryStatsOut(
                    total=0,
                    applied=0,
                    evaluated=0,
                    improved=0,
                    unchanged=0,
                    worse=0,
                    pending_evaluation=0,
                ),
            )
        stmt = stmt.where(AIRecommendation.device_id.in_(accessible_ids))

    rows = db.execute(stmt).all()
    device_ids = sorted({device.id for _, device in rows})
    param_rows = (
        db.scalars(select(DeviceParameter).where(DeviceParameter.device_id.in_(device_ids))).all()
        if device_ids
        else []
    )
    fallback_by_device = {
        row.device_id: PIDParams(kp=float(row.kp), ki=float(row.ki), kd=float(row.kd))
        for row in param_rows
    }

    items: list[AIRecommendationHistoryItemOut] = []
    for rec, device in rows:
        fallback = fallback_by_device.get(device.id) or PIDParams(kp=0.0, ki=0.0, kd=0.0)
        items.append(_build_ai_history_item(rec=rec, device=device, fallback_current_params=fallback))

    stats = AIRecommendationHistoryStatsOut(
        total=len(items),
        applied=sum(1 for item in items if item.history_state == "applied"),
        evaluated=sum(1 for item in items if item.actual_effect_evaluated),
        improved=sum(1 for item in items if item.effect_outcome == "improved"),
        unchanged=sum(1 for item in items if item.effect_outcome == "unchanged"),
        worse=sum(1 for item in items if item.effect_outcome == "worse"),
        pending_evaluation=sum(1 for item in items if item.history_state == "applied" and not item.actual_effect_evaluated),
    )
    return AIRecommendationHistoryResponseOut(items=items, stats=stats)


@router.post("/{device_id}/ai-recommendation/generate", response_model=RecommendationGenerateOutput)
def generate_ai_recommendation(
    device_id: int,
    request: Request,
    window_minutes: int = Query(default=60, ge=5, le=24 * 60),
    end_ms: Optional[int] = Query(default=None, ge=0),
    limit: int = Query(default=20000, ge=1, le=200000),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> RecommendationGenerateOutput:
    logger.debug("[GEN-REQ] method=%s url=%s device_id=%s", request.method, str(request.url), device_id)
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
    if _is_demo_preview_device(device.code):
        generated = _build_demo_mock_recommendation(device=device, params=params)
        logger.debug("[GEN-MOCK] device=%s using demo mocked recommendation", device.code)
    else:
        generated = recommendation_service.generate(request_payload)

    try:
        runtime_decision = ai_runtime_service.build_recommendation_decision(
            payload=request_payload,
            base_output=generated,
            recommendation_id=0,
        )
    except Exception as exc:  # noqa: BLE001
        runtime_decision = {
            "fallback_used": True,
            "fallback_reason": f"ai runtime orchestration failed: {exc}",
            "enabled_models": {},
            "model_status": ai_runtime_service.model_status(),
            "candidate_count": 0,
            "ranked_candidates": [],
            "top_1_candidate_id": None,
            "top_1_candidate": None,
            "scoring_formula": {},
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        }

    generated = ai_runtime_service.apply_decision_to_recommendation(
        output=generated,
        decision=runtime_decision,
    )
    ai_runtime_service.remember_decision(device_id=device_id, decision=runtime_decision)

    generated_fp = recommendation_service.build_recommendation_fingerprint(generated)
    generated.fingerprint = generated_fp

    latest = db.scalar(
        select(AIRecommendation)
        .where(AIRecommendation.device_id == device_id)
        .order_by(AIRecommendation.last_run_at.desc())
    )
    previous_output = None
    elapsed_sec = None
    if latest:
        previous_output = recommendation_service.build_output_from_storage(
            reason=latest.reason,
            suggestion=latest.suggestion,
            risk=latest.risk,
            confidence=float(latest.confidence),
            generated_at=latest.last_run_at,
            fallback_current_params=generated.current_params,
        )
        elapsed_sec = max(0.0, (generated.generated_at - latest.last_run_at).total_seconds())

    tolerance = max(0.0, float(settings.recommendation_float_tolerance))
    cooldown_sec = max(0, int(settings.recommendation_generate_cooldown_sec))
    new_record_after_sec = max(cooldown_sec, int(settings.recommendation_generate_new_record_after_sec))
    same_as_latest = bool(
        previous_output
        and recommendation_service.is_effectively_same_recommendation(
            generated,
            previous_output,
            tolerance=tolerance,
        )
    )
    within_new_record_window = elapsed_sec is not None and elapsed_sec < float(new_record_after_sec)
    should_reuse = bool(latest and same_as_latest and within_new_record_window)
    if should_reuse and latest and previous_output:
        # Reuse existing formal history record for idempotency / anti-spam.
        latest.suggestion = recommendation_service.update_storage_metadata(
            latest.suggestion,
            fingerprint=previous_output.fingerprint or generated_fp,
            last_generate_reused=True,
            increment_reused_count=True,
            last_accessed_at=generated.generated_at,
            runtime_decision=runtime_decision,
        )
        db.commit()
        reused = previous_output.model_copy(deep=True)
        reused.recommendation_id = latest.id
        reused.is_new_record = False
        reused.reused_existing = True
        reused.reused_recommendation_id = latest.id
        reused.generated_at = latest.last_run_at
        reused.fingerprint = previous_output.fingerprint or generated_fp
        reused.history_state = previous_output.history_state or "generated"
        reused.last_generate_reused = True
        reused.reused_count = int(previous_output.reused_count or 0) + 1
        reused.last_accessed_at = generated.generated_at
        reused.ai_decision = runtime_decision
        return reused

    # Demo-only fallback:
    # If realtime window currently looks normal/no-change, preview demo devices can
    # reuse a recent actionable recommendation so demo/apply flow is not blocked.
    # Real business devices must preserve strict generate semantics.
    if _is_demo_preview_device(device.code) and not _recommendation_has_actionable_delta(generated, tolerance=tolerance):
        recent = db.scalars(
            select(AIRecommendation)
            .where(AIRecommendation.device_id == device_id)
            .order_by(AIRecommendation.last_run_at.desc())
            .limit(20)
        ).all()
        for cand in recent:
            cand_output = recommendation_service.build_output_from_storage(
                reason=cand.reason,
                suggestion=cand.suggestion,
                risk=cand.risk,
                confidence=float(cand.confidence),
                generated_at=cand.last_run_at,
                fallback_current_params=generated.current_params,
            )
            if cand_output is None:
                continue
            if not _recommendation_has_actionable_delta(cand_output, tolerance=tolerance):
                continue
            cand.suggestion = recommendation_service.update_storage_metadata(
                cand.suggestion,
                fingerprint=cand_output.fingerprint or generated_fp,
                last_generate_reused=True,
                increment_reused_count=True,
                last_accessed_at=generated.generated_at,
                runtime_decision=runtime_decision,
            )
            db.commit()
            reused = cand_output.model_copy(deep=True)
            reused.recommendation_id = cand.id
            reused.is_new_record = False
            reused.reused_existing = True
            reused.reused_recommendation_id = cand.id
            reused.generated_at = cand.last_run_at
            reused.fingerprint = cand_output.fingerprint or generated_fp
            reused.history_state = cand_output.history_state or "generated"
            reused.last_generate_reused = True
            reused.reused_count = int(cand_output.reused_count or 0) + 1
            reused.last_accessed_at = generated.generated_at
            reused.ai_decision = runtime_decision
            logger.debug(
                "[GEN-FALLBACK] device=%s generated=no-change -> reused actionable recommendation_id=%s",
                device.code,
                cand.id,
            )
            return reused

    reason, suggestion, risk = recommendation_service.to_storage_fields(
        generated,
        fingerprint=generated_fp,
        history_state="generated",
        last_generate_reused=False,
        reused_count=0,
        last_accessed_at=generated.generated_at,
        runtime_decision=runtime_decision,
    )
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
    db.refresh(rec)

    generated.recommendation_id = rec.id
    generated.is_new_record = True
    generated.reused_existing = False
    generated.reused_recommendation_id = None
    generated.fingerprint = generated_fp
    generated.history_state = "generated"
    generated.last_generate_reused = False
    generated.reused_count = 0
    generated.last_accessed_at = generated.generated_at
    generated.ai_decision = runtime_decision
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
    request: Request,
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> DeviceParameter:
    logger.warning(
        "[APPLY-REQ] method=%s url=%s device_id=%s user=%s",
        request.method,
        str(request.url),
        device_id,
        current_user.username,
    )
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        logger.warning("[APPLY-REQ] device_id=%s device not found", device_id)
        raise HTTPException(status_code=404, detail="Device not found")

    rec = db.scalar(
        select(AIRecommendation)
        .where(AIRecommendation.device_id == device_id)
        .order_by(AIRecommendation.last_run_at.desc())
    )
    if not rec:
        logger.warning("[APPLY-REQ] device_id=%s no recommendation found", device_id)
        raise HTTPException(status_code=404, detail="AI recommendation not found")

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not params:
        logger.warning("[APPLY-REQ] device_id=%s no parameters found", device_id)
        raise HTTPException(status_code=404, detail="Parameters not found")
    _hydrate_runtime_parameters(device, params)

    current = PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd))
    recommended = recommendation_service.parse_recommended_params(rec.suggestion, current)
    if not recommended:
        logger.warning("[APPLY-REQ] device_id=%s recommendation parse failed -> dismiss", device_id)
        params.updated_by = f"{current_user.username}:ai-noop"
        params.updated_at = datetime.utcnow()
        rec.last_run_at = datetime.utcnow()
        rec.suggestion = recommendation_service.update_storage_metadata(
            rec.suggestion,
            history_state="dismissed",
            last_accessed_at=datetime.utcnow(),
        )
        db.commit()
        db.refresh(params)
        return params

    # If a recent successful ACK already matches current recommendation target,
    # treat this apply as already completed and skip MQTT re-dispatch.
    matched_ack = _find_recent_success_ack_for_target(
        device_code=device.code,
        target=recommended,
        expected_control_mode=str(params.control_mode or "pid_control"),
        tolerance=float(settings.recommendation_float_tolerance),
    )
    if matched_ack is not None:
        logger.warning(
            "[APPLY-ACK-SHORTCUT] device=%s ack_ts=%s kp=%s ki=%s kd=%s mode=%s",
            device.code,
            matched_ack.get("ts"),
            matched_ack.get("kp"),
            matched_ack.get("ki"),
            matched_ack.get("kd"),
            matched_ack.get("control_mode"),
        )
        params.kp = round(float(recommended.kp), 4)
        params.ki = round(float(recommended.ki), 4)
        params.kd = round(float(recommended.kd), 4)
        params.updated_by = f"{current_user.username}:ai-ack-shortcut"
        applied_at = datetime.utcnow()
        params.updated_at = applied_at
        rec.last_run_at = applied_at
        rec.suggestion = recommendation_service.update_storage_metadata(
            rec.suggestion,
            history_state="applied",
            last_accessed_at=applied_at,
            applied_at=applied_at,
        )
        db.commit()
        db.refresh(params)
        return params

    # Idempotency guard:
    # If latest runtime params already match recommendation target (for example,
    # previous apply succeeded later than client timeout), skip re-dispatch.
    if _pid_is_effectively_applied(
        current=current,
        target=recommended,
        tolerance=float(settings.recommendation_float_tolerance),
    ):
        logger.warning("[APPLY-REQ] device_id=%s idempotent hit (already applied)", device_id)
        params.updated_by = f"{current_user.username}:ai-idempotent"
        applied_at = datetime.utcnow()
        params.updated_at = applied_at
        rec.last_run_at = applied_at
        rec.suggestion = recommendation_service.update_storage_metadata(
            rec.suggestion,
            history_state="applied",
            last_accessed_at=applied_at,
            applied_at=applied_at,
        )
        db.commit()
        db.refresh(params)
        return params

    params.kp = round(float(recommended.kp), 4)
    params.ki = round(float(recommended.ki), 4)
    params.kd = round(float(recommended.kd), 4)
    applied_at = datetime.utcnow()
    rec.last_run_at = applied_at
    rec.suggestion = recommendation_service.update_storage_metadata(
        rec.suggestion,
        history_state="applied",
        last_accessed_at=applied_at,
        applied_at=applied_at,
    )

    return _dispatch_and_confirm_parameter_update(
        db=db,
        device=device,
        param=params,
        updated_by=f"{current_user.username}:ai",
    )


@router.post("/{device_id}/ai-recommendation/preview", response_model=RecommendationPreviewOutput)
def preview_ai_recommendation(
    device_id: int,
    horizon_sec: int = Query(default=PREVIEW_DEFAULT_HORIZON_SEC, ge=30, le=7200),
    step_sec: int = Query(default=PREVIEW_DEFAULT_STEP_SEC, ge=1, le=10),
    ambient_temp: float = Query(default=PREVIEW_DEFAULT_AMBIENT_TEMP, ge=-40, le=80),
    heating_gain: float = Query(default=PREVIEW_DEFAULT_HEATING_GAIN, gt=0, le=1),
    cooling_coeff: float = Query(default=PREVIEW_DEFAULT_COOLING_COEFF, gt=0, le=1),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> RecommendationPreviewOutput:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    _apply_live_snapshot(device)

    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not params:
        raise HTTPException(status_code=404, detail="Parameters not found")
    _hydrate_runtime_parameters(device, params)

    rec = db.scalar(
        select(AIRecommendation)
        .where(AIRecommendation.device_id == device_id)
        .order_by(AIRecommendation.last_run_at.desc())
    )
    if not rec:
        raise HTTPException(status_code=404, detail="AI recommendation not found")

    baseline_params = PIDParams(kp=float(params.kp), ki=float(params.ki), kd=float(params.kd))
    recommended_params = recommendation_service.parse_recommended_params(rec.suggestion, baseline_params)
    if not recommended_params:
        raise HTTPException(status_code=409, detail="AI recommendation cannot be parsed into PID parameters")

    cfg = PreviewSimulationConfig(
        horizon_sec=horizon_sec,
        step_sec=step_sec,
        ambient_temp=float(ambient_temp),
        heating_gain=float(heating_gain),
        cooling_coeff=float(cooling_coeff),
        target_band=float(params.target_band),
        pwm_saturation_threshold=float(params.pwm_saturation_threshold),
        control_mode=str(params.control_mode or "pid_control"),
    )
    preview_output = preview_simulator.run(
        current_temp=float(device.current_temp),
        target_temp=float(device.target_temp),
        baseline_params=baseline_params,
        recommended_params=recommended_params,
        config=cfg,
    )

    rec_meta = recommendation_service.read_storage_metadata(rec.suggestion)
    current_state = str(rec_meta.get("hs") or "generated")
    next_state = current_state if current_state in {"applied", "dismissed", "expired"} else "previewed"
    rec.suggestion = recommendation_service.update_storage_metadata(
        rec.suggestion,
        history_state=next_state,
        last_accessed_at=datetime.utcnow(),
    )
    db.commit()
    return preview_output


@router.post(
    "/{device_id}/ai-recommendation/{recommendation_id}/evaluate-actual",
    response_model=RecommendationActualEvaluationOutput,
)
def evaluate_ai_recommendation_actual(
    device_id: int,
    recommendation_id: int,
    payload: RecommendationActualEvaluationRequest = RecommendationActualEvaluationRequest(),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> RecommendationActualEvaluationOutput:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not params:
        raise HTTPException(status_code=404, detail="Parameters not found")
    _hydrate_runtime_parameters(device, params)

    rec = db.scalar(
        select(AIRecommendation).where(AIRecommendation.id == recommendation_id, AIRecommendation.device_id == device_id)
    )
    if not rec:
        raise HTTPException(status_code=404, detail="AI recommendation not found")

    meta = recommendation_service.read_storage_metadata(rec.suggestion)
    history_state = str(meta.get("hs") or "generated")
    if history_state != "applied":
        raise HTTPException(status_code=409, detail="Recommendation has not been applied yet")

    apply_at = _parse_iso_utc(meta.get("la")) or rec.last_run_at
    now_dt = datetime.utcnow()
    if now_dt <= apply_at:
        rec.suggestion = recommendation_service.update_storage_metadata(
            rec.suggestion,
            last_accessed_at=now_dt,
            insufficient_data=True,
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Not enough post-apply telemetry data yet.")

    window_minutes = int(payload.observation_window_minutes)
    observation_start_ms = int(apply_at.timestamp() * 1000)
    observation_end_dt = min(now_dt, _utc_naive_from_sec(observation_start_ms / 1000.0 + window_minutes * 60))
    observation_end_ms = int(observation_end_dt.timestamp() * 1000)

    observed_points = _load_observed_points(
        db=db,
        device=device,
        start_ms=observation_start_ms,
        end_ms=observation_end_ms,
        limit=200000,
    )
    if len(observed_points) < 5:
        rec.suggestion = recommendation_service.update_storage_metadata(
            rec.suggestion,
            last_accessed_at=datetime.utcnow(),
            insufficient_data=True,
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Not enough post-apply telemetry data yet.")

    target_band = float(params.target_band)
    pwm_threshold = float(params.pwm_saturation_threshold)
    actual_metrics = post_effect_evaluator.calc_metrics(
        points=observed_points,
        target_band=target_band,
        pwm_saturation_threshold=pwm_threshold,
    )
    if actual_metrics is None:
        rec.suggestion = recommendation_service.update_storage_metadata(
            rec.suggestion,
            last_accessed_at=datetime.utcnow(),
            insufficient_data=True,
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Not enough post-apply telemetry data yet.")

    before_start_ms = observation_start_ms - window_minutes * 60 * 1000
    before_end_ms = observation_start_ms - 1
    before_points = _load_observed_points(
        db=db,
        device=device,
        start_ms=before_start_ms,
        end_ms=before_end_ms,
        limit=200000,
    )
    baseline_metrics = post_effect_evaluator.calc_metrics(
        points=before_points,
        target_band=target_band,
        pwm_saturation_threshold=pwm_threshold,
    )
    if baseline_metrics is None:
        parsed = recommendation_service.parse_suggestion_payload(rec.suggestion)
        evidence = parsed.get("evidence") if isinstance(parsed, dict) else None
        baseline_metrics = _extract_metrics_from_evidence(evidence if isinstance(evidence, dict) else None)

    preview_metrics = _extract_preview_recommended_metrics(meta)
    actual_summary = post_effect_evaluator.build_actual_summary(points=observed_points, metrics=actual_metrics)
    comparison_before = post_effect_evaluator.compare(reference=baseline_metrics, actual=actual_metrics)
    comparison_preview = None
    if preview_metrics is not None:
        comparison_preview = post_effect_evaluator.compare(reference=preview_metrics, actual=actual_metrics)

    evaluated_at = datetime.utcnow()
    rec.suggestion = recommendation_service.update_storage_metadata(
        rec.suggestion,
        last_accessed_at=evaluated_at,
        post_effect_summary=actual_summary.model_dump(mode="json"),
        post_effect_comparison_before=comparison_before.model_dump(mode="json"),
        post_effect_comparison_preview=None if comparison_preview is None else comparison_preview.model_dump(mode="json"),
        actual_effect_evaluated=True,
        insufficient_data=False,
        observation_window_minutes=window_minutes,
        evaluated_at=evaluated_at,
    )
    db.commit()

    return RecommendationActualEvaluationOutput(
        recommendation_id=rec.id,
        history_state=history_state,
        evaluated_at=evaluated_at,
        observation_window_minutes=window_minutes,
        actual_effect_summary=actual_summary,
        comparison_to_before=comparison_before,
        comparison_to_preview=comparison_preview,
    )


@router.get(
    "/{device_id}/ai-recommendation/{recommendation_id}/telemetry-comparison",
    response_model=AITelemetryComparisonOut,
)
def get_ai_recommendation_telemetry_comparison(
    device_id: int,
    recommendation_id: int,
    start_ms: Optional[int] = Query(default=None, ge=0),
    end_ms: Optional[int] = Query(default=None, ge=0),
    baseline_window_minutes: Optional[int] = Query(default=None, ge=1, le=720),
    observation_window_minutes: Optional[int] = Query(default=None, ge=1, le=720),
    max_points: int = Query(default=360, ge=60, le=2000),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> AITelemetryComparisonOut:
    require_device_access(device_id, db, current_user)
    device = db.scalar(select(Device).where(Device.id == device_id))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device_id))
    if not params:
        raise HTTPException(status_code=404, detail="Parameters not found")
    _hydrate_runtime_parameters(device, params)

    rec = db.scalar(
        select(AIRecommendation).where(AIRecommendation.id == recommendation_id, AIRecommendation.device_id == device_id)
    )
    if not rec:
        raise HTTPException(status_code=404, detail="AI recommendation not found")

    meta = recommendation_service.read_storage_metadata(rec.suggestion)
    applied_at = _parse_iso_utc(meta.get("apa")) or rec.last_run_at
    history_state = str(meta.get("hs") or "").strip().lower()
    if history_state not in {"generated", "previewed", "applied", "dismissed", "expired"}:
        history_state = ""
    if not history_state and applied_at is not None:
        history_state = "applied"
    if history_state != "applied":
        raise HTTPException(status_code=409, detail="Recommendation has not been applied yet")

    applied_ms = int(applied_at.timestamp() * 1000)

    now_ms = int(datetime.utcnow().timestamp() * 1000)
    selected_end_ms = int(end_ms) if isinstance(end_ms, int) and end_ms > 0 else now_ms
    if selected_end_ms > now_ms:
        selected_end_ms = now_ms

    selected_start_ms = int(start_ms) if isinstance(start_ms, int) and start_ms >= 0 else applied_ms
    if selected_start_ms > selected_end_ms:
        selected_start_ms = selected_end_ms

    obs_minutes = int(observation_window_minutes or max(1, round((selected_end_ms - selected_start_ms) / 60000.0) or 30))
    base_minutes = int(baseline_window_minutes or obs_minutes)
    obs_minutes = max(1, min(720, obs_minutes))
    base_minutes = max(1, min(720, base_minutes))

    baseline_start_ms = applied_ms - base_minutes * 60 * 1000
    baseline_end_ms = applied_ms
    actual_start_ms = max(selected_start_ms, applied_ms)
    actual_end_ms = max(actual_start_ms, selected_end_ms)

    # Baseline is strictly pre-apply and anchored to applied_at.
    baseline_points = _downsample_points(
        _load_observed_points(
            db=db,
            device=device,
            start_ms=baseline_start_ms,
            end_ms=baseline_end_ms,
            limit=200000,
        ),
        max_points,
    )
    # Actual only includes post-apply telemetry.
    actual_points = _downsample_points(
        _load_observed_points(
            db=db,
            device=device,
            start_ms=actual_start_ms,
            end_ms=actual_end_ms,
            limit=200000,
        ),
        max_points,
    )

    baseline_curve = [_curve_point_from_observed(point, anchor_ms=applied_ms) for point in baseline_points]
    actual_curve = [_curve_point_from_observed(point, anchor_ms=applied_ms) for point in actual_points]

    # Preview is sourced from stored recommendation preview payload when available.
    preview_curve = _extract_preview_curve_from_meta(meta, anchor_ms=applied_ms)
    preview_source = "stored" if preview_curve else "unavailable"
    if not preview_curve:
        # Fallback keeps the chart usable when historical preview points were not persisted.
        preview_curve = _build_preview_curve_fallback(
            rec=rec,
            meta=meta,
            device=device,
            params=params,
            anchor_ms=applied_ms,
            observation_window_minutes=obs_minutes,
            baseline_points=baseline_points,
        )
        if preview_curve:
            preview_source = "reconstructed"

    target_temp = None
    if actual_points:
        target_temp = float(actual_points[-1].target_temp)
    elif baseline_points:
        target_temp = float(baseline_points[-1].target_temp)
    else:
        target_temp = float(device.target_temp)

    post_apply_expected_end_ms = applied_ms + obs_minutes * 60 * 1000
    partial_post_apply_window = bool(selected_start_ms > applied_ms or selected_end_ms < post_apply_expected_end_ms)

    missing_curves: list[str] = []
    if not baseline_curve:
        missing_curves.append("baseline")
    if not preview_curve:
        missing_curves.append("preview")
    if not actual_curve:
        missing_curves.append("actual")

    return AITelemetryComparisonOut(
        recommendation_id=rec.id,
        applied_at=applied_at,
        baseline_window_minutes=base_minutes,
        observation_window_minutes=obs_minutes,
        actual_start=_utc_naive_from_ms(actual_start_ms),
        actual_end=_utc_naive_from_ms(actual_end_ms),
        baseline_curve=baseline_curve,
        preview_curve=preview_curve,
        actual_curve=actual_curve,
        target_temp=target_temp,
        target_band=float(params.target_band),
        preview_source=preview_source,
        partial_post_apply_window=partial_post_apply_window,
        missing_curves=missing_curves,
    )
