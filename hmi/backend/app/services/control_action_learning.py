from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AIRecommendation,
    ControlAction,
    ControlActionEvalJob,
    ControlActionFeedbackSample,
    Device,
    DeviceMetric,
    DeviceParameter,
)
from app.services.ai.post_effect_evaluator import ObservedTelemetryPoint, PostEffectEvaluator
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import PIDParams, PostEffectComparison, PreviewMetrics


@dataclass(frozen=True)
class ControlActionLearningThresholds:
    min_points_required: int = 5
    target_temp_change_tolerance: float = 0.2
    offline_ratio_reject_threshold: float = 0.25
    preview_gap_low_max: float = 0.33
    preview_gap_medium_max: float = 0.66


THRESHOLDS = ControlActionLearningThresholds()


@dataclass
class ControlActionEvaluationResult:
    status: str
    insufficient_data: bool
    sample_id: Optional[int] = None
    reason: Optional[str] = None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_preview_metrics(raw: Any) -> Optional[PreviewMetrics]:
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("recommended_metrics"), dict):
        raw = raw.get("recommended_metrics")
    if not isinstance(raw, dict):
        return None
    fields = {
        "in_band_ratio": _safe_float(raw.get("in_band_ratio")),
        "overshoot_c": _safe_float(raw.get("overshoot_c")),
        "settling_sec": _safe_float(raw.get("settling_sec")),
        "mean_abs_error": _safe_float(raw.get("mean_abs_error")),
        "saturation_ratio": _safe_float(raw.get("saturation_ratio")),
        "temp_swing": _safe_float(raw.get("temp_swing")),
    }
    required = ("in_band_ratio", "overshoot_c", "mean_abs_error", "saturation_ratio", "temp_swing")
    if any(fields[k] is None for k in required):
        return None
    return PreviewMetrics(
        in_band_ratio=float(fields["in_band_ratio"]),
        overshoot_c=float(fields["overshoot_c"]),
        settling_sec=fields["settling_sec"],
        mean_abs_error=float(fields["mean_abs_error"]),
        saturation_ratio=float(fields["saturation_ratio"]),
        temp_swing=float(fields["temp_swing"]),
    )


def _derive_actual_effect_label(comparison: Optional[PostEffectComparison]) -> str:
    if comparison is None:
        return "unchanged"
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


def _derive_preview_gap_label(comparison: Optional[PostEffectComparison]) -> Optional[str]:
    if comparison is None:
        return None
    score_parts: list[float] = []
    in_band = abs(float(comparison.in_band_ratio_delta or 0.0))
    if in_band > 0:
        score_parts.append(min(1.0, in_band / 0.2))
    overshoot = abs(float(comparison.overshoot_c_delta or 0.0))
    if overshoot > 0:
        score_parts.append(min(1.0, overshoot / 1.0))
    settling = abs(float(comparison.settling_sec_delta or 0.0))
    if settling > 0:
        score_parts.append(min(1.0, settling / 180.0))
    mae = abs(float(comparison.mean_abs_error_delta or 0.0))
    if mae > 0:
        score_parts.append(min(1.0, mae / 0.5))
    saturation = abs(float(comparison.saturation_ratio_delta or 0.0))
    if saturation > 0:
        score_parts.append(min(1.0, saturation / 0.3))
    swing = abs(float(comparison.temp_swing_delta or 0.0))
    if swing > 0:
        score_parts.append(min(1.0, swing / 1.5))
    if not score_parts:
        return None
    score = sum(score_parts) / len(score_parts)
    if score < THRESHOLDS.preview_gap_low_max:
        return "low"
    if score < THRESHOLDS.preview_gap_medium_max:
        return "medium"
    return "high"


def _derive_quality(
    *,
    insufficient_data: bool,
    reasons: list[str],
) -> tuple[str, bool, Optional[str]]:
    if insufficient_data:
        return "reject", False, "insufficient_data"
    if not reasons:
        return "high", True, None
    severe = {"conflicting_parameter_change", "device_offline_too_long", "target_temp_changed_mid_window"}
    if any(reason in severe for reason in reasons):
        return "reject", False, ",".join(sorted(set(reasons)))
    if len(reasons) == 1:
        return "medium", True, reasons[0]
    return "low", False, ",".join(sorted(set(reasons)))


class ControlActionLearningService:
    def __init__(self) -> None:
        self.recommendation_service = RecommendationService()
        self.post_effect_evaluator = PostEffectEvaluator()

    def create_action_and_eval_job(
        self,
        *,
        db: Session,
        device: Device,
        source: str,
        source_ref_id: Optional[int],
        action_type: str,
        initiated_by: str,
        applied_at: datetime,
        before: dict[str, Any],
        after: dict[str, Any],
        context_snapshot: Optional[dict[str, Any]] = None,
        observation_window_minutes: int = 15,
        scheduled_at: Optional[datetime] = None,
    ) -> tuple[ControlAction, ControlActionEvalJob]:
        action = ControlAction(
            device_id=device.id,
            source=str(source),
            source_ref_id=source_ref_id,
            action_type=str(action_type),
            initiated_by=str(initiated_by),
            applied_at=applied_at,
            status="pending_eval",
            control_mode_before=before.get("control_mode"),
            control_mode_after=after.get("control_mode"),
            target_temp_before=_safe_float(before.get("target_temp")),
            target_temp_after=_safe_float(after.get("target_temp")),
            kp_before=_safe_float(before.get("kp")),
            ki_before=_safe_float(before.get("ki")),
            kd_before=_safe_float(before.get("kd")),
            kp_after=_safe_float(after.get("kp")),
            ki_after=_safe_float(after.get("ki")),
            kd_after=_safe_float(after.get("kd")),
            delta_kp=(_safe_float(after.get("kp")) or 0.0) - (_safe_float(before.get("kp")) or 0.0),
            delta_ki=(_safe_float(after.get("ki")) or 0.0) - (_safe_float(before.get("ki")) or 0.0),
            delta_kd=(_safe_float(after.get("kd")) or 0.0) - (_safe_float(before.get("kd")) or 0.0),
            context_snapshot=context_snapshot or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(action)
        db.flush()

        job = ControlActionEvalJob(
            control_action_id=action.id,
            device_id=device.id,
            status="pending",
            scheduled_at=scheduled_at or applied_at,
            observation_window_minutes=max(1, int(observation_window_minutes)),
            attempt_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(action)
        db.refresh(job)
        return action, job

    def evaluate_control_action(
        self,
        *,
        db: Session,
        control_action: ControlAction,
        observation_window_minutes: int,
        now_dt: Optional[datetime] = None,
    ) -> ControlActionEvaluationResult:
        existing = db.scalar(
            select(ControlActionFeedbackSample)
            .where(ControlActionFeedbackSample.control_action_id == control_action.id)
            .limit(1)
        )
        if existing is not None:
            return ControlActionEvaluationResult(
                status="done",
                insufficient_data=bool(existing.insufficient_data),
                sample_id=existing.id,
                reason="already_evaluated",
            )

        now_dt = now_dt or datetime.utcnow()
        device = db.scalar(select(Device).where(Device.id == control_action.device_id))
        if device is None:
            return ControlActionEvaluationResult(status="failed", insufficient_data=False, reason="device_not_found")

        apply_at = control_action.applied_at
        if now_dt <= apply_at:
            return ControlActionEvaluationResult(status="insufficient_data", insufficient_data=True, reason="future_apply_timestamp")

        window_minutes = max(1, int(observation_window_minutes))
        observation_end = min(now_dt, apply_at + timedelta(minutes=window_minutes))
        observed_rows = db.execute(
            select(
                DeviceMetric.timestamp,
                DeviceMetric.current_temp,
                DeviceMetric.target_temp,
                DeviceMetric.error,
                DeviceMetric.pwm_output,
                DeviceMetric.status,
            )
            .where(
                DeviceMetric.device_id == control_action.device_id,
                DeviceMetric.timestamp >= apply_at,
                DeviceMetric.timestamp <= observation_end,
            )
            .order_by(DeviceMetric.timestamp.asc())
            .limit(200000)
        ).all()
        if len(observed_rows) < THRESHOLDS.min_points_required:
            return ControlActionEvaluationResult(status="insufficient_data", insufficient_data=True, reason="not_enough_post_apply_points")

        observed_points = [
            ObservedTelemetryPoint(
                ts_ms=int(ts.timestamp() * 1000),
                temp=float(temp),
                target_temp=float(target),
                error=float(err),
                pwm_output=float(pwm),
                saturation_state=None,
            )
            for ts, temp, target, err, pwm, _status in observed_rows
        ]
        target_band = 0.5
        pwm_threshold = 85.0
        params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == control_action.device_id))
        if params is not None:
            target_band = float(params.target_band)
            pwm_threshold = float(params.pwm_saturation_threshold)
        actual_metrics = self.post_effect_evaluator.calc_metrics(
            points=observed_points,
            target_band=target_band,
            pwm_saturation_threshold=pwm_threshold,
        )
        if actual_metrics is None:
            return ControlActionEvaluationResult(status="insufficient_data", insufficient_data=True, reason="post_metrics_unavailable")

        before_start = apply_at - timedelta(minutes=window_minutes)
        before_rows = db.execute(
            select(
                DeviceMetric.timestamp,
                DeviceMetric.current_temp,
                DeviceMetric.target_temp,
                DeviceMetric.error,
                DeviceMetric.pwm_output,
            )
            .where(
                DeviceMetric.device_id == control_action.device_id,
                DeviceMetric.timestamp >= before_start,
                DeviceMetric.timestamp < apply_at,
            )
            .order_by(DeviceMetric.timestamp.asc())
            .limit(200000)
        ).all()
        before_points = [
            ObservedTelemetryPoint(
                ts_ms=int(ts.timestamp() * 1000),
                temp=float(temp),
                target_temp=float(target),
                error=float(err),
                pwm_output=float(pwm),
            )
            for ts, temp, target, err, pwm in before_rows
        ]
        baseline_metrics = self.post_effect_evaluator.calc_metrics(
            points=before_points,
            target_band=target_band,
            pwm_saturation_threshold=pwm_threshold,
        )

        rec: Optional[AIRecommendation] = None
        parsed = None
        evidence: dict[str, Any] = {}
        meta: dict[str, Any] = {}
        preview_metrics: Optional[PreviewMetrics] = None
        runtime_decision_summary: Optional[dict[str, Any]] = None
        if control_action.source == "ai_recommendation" and control_action.source_ref_id:
            rec = db.scalar(
                select(AIRecommendation)
                .where(
                    AIRecommendation.id == int(control_action.source_ref_id),
                    AIRecommendation.device_id == control_action.device_id,
                )
            )
            if rec is not None:
                fallback = PIDParams(
                    kp=float(control_action.kp_before or 0.0),
                    ki=float(control_action.ki_before or 0.0),
                    kd=float(control_action.kd_before or 0.0),
                )
                parsed = self.recommendation_service.build_output_from_storage(
                    reason=rec.reason,
                    suggestion=rec.suggestion,
                    risk=rec.risk,
                    confidence=float(rec.confidence),
                    generated_at=rec.last_run_at,
                    fallback_current_params=fallback,
                )
                if parsed is not None:
                    evidence = dict(parsed.evidence or {})
                meta = self.recommendation_service.read_storage_metadata(rec.suggestion)
                preview_metrics = _to_preview_metrics(meta.get("pvs"))
                ard = meta.get("ard")
                if isinstance(ard, dict):
                    top = ard.get("top_1_candidate") if isinstance(ard.get("top_1_candidate"), dict) else {}
                    runtime_decision_summary = {
                        "runtime_source": ard.get("runtime_source"),
                        "candidate_count": _safe_int(ard.get("candidate_count")),
                        "top_1_candidate_id": ard.get("top_1_candidate_id"),
                        "top_1_total_score": _safe_float(top.get("total_score")) if isinstance(top, dict) else None,
                        "top_1_success_score": _safe_float(top.get("success_score")) if isinstance(top, dict) else None,
                        "top_1_gap_score": _safe_float(top.get("preview_gap_score")) if isinstance(top, dict) else None,
                        "fallback_used": bool(ard.get("fallback_used")) if "fallback_used" in ard else False,
                    }

        if baseline_metrics is None and evidence:
            try:
                baseline_metrics = PreviewMetrics(
                    in_band_ratio=float(evidence.get("in_band_ratio")),
                    overshoot_c=float(evidence.get("overshoot_c") or 0.0),
                    settling_sec=None if evidence.get("settling_sec") is None else float(evidence.get("settling_sec")),
                    mean_abs_error=float(evidence.get("mean_abs_error")),
                    saturation_ratio=float(evidence.get("saturation_ratio")),
                    temp_swing=float(evidence.get("temp_swing")),
                )
            except Exception:
                baseline_metrics = None

        actual_summary = self.post_effect_evaluator.build_actual_summary(points=observed_points, metrics=actual_metrics)
        comparison_before = self.post_effect_evaluator.compare(reference=baseline_metrics, actual=actual_metrics)
        comparison_preview = (
            self.post_effect_evaluator.compare(reference=preview_metrics, actual=actual_metrics)
            if preview_metrics is not None
            else None
        )

        reasons: list[str] = []
        if baseline_metrics is None:
            reasons.append("baseline_unavailable")

        if params is not None and params.updated_at is not None and params.updated_at > apply_at and params.updated_at <= observation_end:
            reasons.append("conflicting_parameter_change")

        statuses = [str(status or "").lower() for *_tail, status in observed_rows]
        if statuses:
            offline_ratio = sum(1 for s in statuses if s in {"offline", "disconnected"}) / len(statuses)
            if offline_ratio > THRESHOLDS.offline_ratio_reject_threshold:
                reasons.append("device_offline_too_long")

        targets = [float(target) for _ts, _temp, target, _err, _pwm, _status in observed_rows]
        if targets and (max(targets) - min(targets)) > THRESHOLDS.target_temp_change_tolerance:
            reasons.append("target_temp_changed_mid_window")

        actual_effect_label = _derive_actual_effect_label(comparison_before)
        preview_gap_label = _derive_preview_gap_label(comparison_preview)
        quality, eligible, exclusion = _derive_quality(insufficient_data=False, reasons=reasons)

        sample = ControlActionFeedbackSample(
            control_action_id=control_action.id,
            device_id=control_action.device_id,
            source=control_action.source,
            source_ref_id=control_action.source_ref_id,
            action_type=control_action.action_type,
            initiated_by=control_action.initiated_by,
            generated_at=rec.last_run_at if rec is not None else None,
            applied_at=apply_at,
            evaluated_at=now_dt,
            primary_problem_type=parsed.primary_problem_type.value if parsed is not None else None,
            secondary_problem_types=[item.value for item in parsed.secondary_problem_types] if parsed is not None else [],
            problem_flags=dict(parsed.problem_flags or {}) if parsed is not None else {},
            expected_effect=parsed.expected_effect.value if parsed is not None else None,
            risk_level=parsed.risk_level.value if parsed is not None else None,
            confidence=float(parsed.confidence) if parsed is not None else None,
            control_mode_before=control_action.control_mode_before,
            control_mode_after=control_action.control_mode_after,
            target_temp_before=control_action.target_temp_before,
            target_temp_after=control_action.target_temp_after,
            kp_before=control_action.kp_before,
            ki_before=control_action.ki_before,
            kd_before=control_action.kd_before,
            kp_after=control_action.kp_after,
            ki_after=control_action.ki_after,
            kd_after=control_action.kd_after,
            delta_kp=control_action.delta_kp,
            delta_ki=control_action.delta_ki,
            delta_kd=control_action.delta_kd,
            mean_error=_safe_float(evidence.get("mean_error")) if evidence else None,
            mean_abs_error=_safe_float(evidence.get("mean_abs_error")) if evidence else None,
            error_std=_safe_float(evidence.get("error_std")) if evidence else None,
            temp_swing=_safe_float(evidence.get("temp_swing")) if evidence else None,
            pwm_mean=_safe_float(evidence.get("pwm_mean")) if evidence else None,
            pwm_max=_safe_float(evidence.get("pwm_max")) if evidence else None,
            zero_crossings=_safe_int(evidence.get("zero_crossings")) if evidence else None,
            in_band_ratio=_safe_float(evidence.get("in_band_ratio")) if evidence else None,
            overshoot_pct=_safe_float(evidence.get("overshoot_pct")) if evidence else None,
            settling_sec=_safe_float(evidence.get("settling_sec")) if evidence else None,
            saturation_ratio=_safe_float(evidence.get("saturation_ratio")) if evidence else None,
            runtime_decision_summary=runtime_decision_summary,
            preview_metrics_summary=None if preview_metrics is None else {
                "in_band_ratio": preview_metrics.in_band_ratio,
                "overshoot_c": preview_metrics.overshoot_c,
                "settling_sec": preview_metrics.settling_sec,
                "mean_abs_error": preview_metrics.mean_abs_error,
                "saturation_ratio": preview_metrics.saturation_ratio,
                "temp_swing": preview_metrics.temp_swing,
            },
            actual_metrics_summary=actual_summary.model_dump(mode="json"),
            comparison_to_before=comparison_before.model_dump(mode="json"),
            comparison_to_preview=None if comparison_preview is None else comparison_preview.model_dump(mode="json"),
            actual_effect_label=actual_effect_label,
            preview_gap_label=preview_gap_label,
            insufficient_data=False,
            sample_quality=quality,
            is_training_eligible=bool(eligible and not reasons),
            training_exclusion_reason=exclusion,
            label_source="deterministic_control_action_rules_v1",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(sample)

        control_action.status = "evaluated"
        control_action.updated_at = datetime.utcnow()

        if rec is not None:
            rec.suggestion = self.recommendation_service.update_storage_metadata(
                rec.suggestion,
                last_accessed_at=now_dt,
                post_effect_summary=actual_summary.model_dump(mode="json"),
                post_effect_comparison_before=comparison_before.model_dump(mode="json"),
                post_effect_comparison_preview=None if comparison_preview is None else comparison_preview.model_dump(mode="json"),
                actual_effect_evaluated=True,
                insufficient_data=False,
                observation_window_minutes=window_minutes,
                evaluated_at=now_dt,
            )
        db.commit()
        db.refresh(sample)
        return ControlActionEvaluationResult(status="done", insufficient_data=False, sample_id=sample.id)


control_action_learning_service = ControlActionLearningService()

