from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AIRecommendation, Device, DeviceParameter
from app.services.ai.schemas import PIDParams
from app.services.ai.recommendation_service import RecommendationService


@dataclass
class RecommendationFeedbackDatasetSummary:
    total_recommendation_records: int = 0
    unique_recommendation_ids: int = 0
    duplicate_recommendation_ids_count: int = 0
    applied_recommendation_records: int = 0
    evaluated_recommendation_records: int = 0
    insufficient_data_count: int = 0
    trainable_samples_count: int = 0
    improved_count: int = 0
    unchanged_count: int = 0
    worse_count: int = 0
    pending_count: int = 0
    average_confidence: Optional[float] = None
    average_delta_kp: Optional[float] = None
    average_delta_ki: Optional[float] = None
    average_delta_kd: Optional[float] = None
    preview_gap_low_count: int = 0
    preview_gap_medium_count: int = 0
    preview_gap_high_count: int = 0


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


def _as_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _derive_effect_outcome(comparison_before: Optional[dict[str, Any]]) -> str:
    if not isinstance(comparison_before, dict):
        return "pending"

    weighted_deltas: list[int] = []

    in_band = _as_float(comparison_before.get("in_band_ratio_delta"))
    if in_band is not None:
        if in_band > 0.0001:
            weighted_deltas.append(1)
        elif in_band < -0.0001:
            weighted_deltas.append(-1)

    for key in (
        "overshoot_c_delta",
        "settling_sec_delta",
        "mean_abs_error_delta",
        "saturation_ratio_delta",
        "temp_swing_delta",
    ):
        value = _as_float(comparison_before.get(key))
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


def _normalize_history_state(raw: object, *, applied_at: Optional[datetime], actual_effect_evaluated: bool) -> str:
    state = str(raw or "").strip().lower()
    if state in {"generated", "previewed", "applied", "dismissed", "expired"}:
        return state
    if applied_at is not None or actual_effect_evaluated:
        return "applied"
    return "generated"


def _resolve_post_effect_summary(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    # Support compact keys produced by suggestion size trimming.
    if "in_band_ratio_after" in raw or "point_count" in raw:
        return raw

    return {
        "in_band_ratio_after": raw.get("ib"),
        "overshoot_c_after": raw.get("ov"),
        "settling_sec_after": raw.get("st"),
        "mean_abs_error_after": raw.get("ma"),
        "saturation_ratio_after": raw.get("sr"),
        "temp_swing_after": raw.get("sw"),
        "point_count": raw.get("pc"),
        "observed_window_start": raw.get("ws"),
        "observed_window_end": raw.get("we"),
    }


def _resolve_preview_summary(raw: object) -> tuple[dict[str, Any], Optional[str]]:
    if not isinstance(raw, dict):
        return {}, None

    preview_source = None
    if isinstance(raw.get("preview_source"), str):
        preview_source = str(raw.get("preview_source"))
    elif isinstance(raw.get("source"), str):
        preview_source = str(raw.get("source"))

    recommended = raw.get("recommended_metrics")
    if isinstance(recommended, dict):
        return recommended, preview_source

    # Compact recommendation metadata shape for varchar(255)-safe payloads.
    if any(k in raw for k in ("ib", "ov", "st", "ma", "sr", "sw")):
        return {
            "in_band_ratio": raw.get("ib"),
            "overshoot_c": raw.get("ov"),
            "settling_sec": raw.get("st"),
            "mean_abs_error": raw.get("ma"),
            "saturation_ratio": raw.get("sr"),
            "temp_swing": raw.get("sw"),
        }, preview_source

    # Fallback for already-flattened legacy shapes.
    if any(k in raw for k in ("in_band_ratio", "overshoot_c", "mean_abs_error", "saturation_ratio", "temp_swing")):
        return raw, preview_source

    return {}, preview_source


def _resolve_comparison(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    if any(
        key in raw
        for key in (
            "in_band_ratio_delta",
            "overshoot_c_delta",
            "settling_sec_delta",
            "mean_abs_error_delta",
            "saturation_ratio_delta",
            "temp_swing_delta",
        )
    ):
        return raw
    # Compact metadata keys used by demo seed to fit varchar(255) constraints.
    return {
        "in_band_ratio_delta": raw.get("ib"),
        "overshoot_c_delta": raw.get("ov"),
        "settling_sec_delta": raw.get("st"),
        "mean_abs_error_delta": raw.get("ma"),
        "saturation_ratio_delta": raw.get("sr"),
        "temp_swing_delta": raw.get("sw"),
    }


def _derive_preview_gap_level(comparison_preview: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(comparison_preview, dict):
        return None

    # Inference heuristic: evaluate magnitude of preview-vs-actual gap across key metrics.
    score_parts: list[float] = []
    in_band = abs(_as_float(comparison_preview.get("in_band_ratio_delta")) or 0.0)
    if in_band > 0:
        score_parts.append(min(1.0, in_band / 0.2))

    overshoot = abs(_as_float(comparison_preview.get("overshoot_c_delta")) or 0.0)
    if overshoot > 0:
        score_parts.append(min(1.0, overshoot / 1.0))

    settling = abs(_as_float(comparison_preview.get("settling_sec_delta")) or 0.0)
    if settling > 0:
        score_parts.append(min(1.0, settling / 180.0))

    mae = abs(_as_float(comparison_preview.get("mean_abs_error_delta")) or 0.0)
    if mae > 0:
        score_parts.append(min(1.0, mae / 0.5))

    saturation = abs(_as_float(comparison_preview.get("saturation_ratio_delta")) or 0.0)
    if saturation > 0:
        score_parts.append(min(1.0, saturation / 0.3))

    swing = abs(_as_float(comparison_preview.get("temp_swing_delta")) or 0.0)
    if swing > 0:
        score_parts.append(min(1.0, swing / 1.5))

    if not score_parts:
        return None

    score = sum(score_parts) / len(score_parts)
    if score < 0.33:
        return "low"
    if score < 0.66:
        return "medium"
    return "high"


def _safe_pid_value(params: Optional[dict[str, Any]], key: str) -> Optional[float]:
    if not isinstance(params, dict):
        return None
    return _as_float(params.get(key))


class RecommendationFeedbackDatasetBuilder:
    def __init__(self, recommendation_service: Optional[RecommendationService] = None) -> None:
        self.recommendation_service = recommendation_service or RecommendationService()

    def build_feedback_sample(
        self,
        *,
        recommendation: AIRecommendation,
        device: Device,
        fallback_current_params: PIDParams,
    ) -> dict[str, Any]:
        parsed = self.recommendation_service.build_output_from_storage(
            reason=recommendation.reason,
            suggestion=recommendation.suggestion,
            risk=recommendation.risk,
            confidence=float(recommendation.confidence),
            generated_at=recommendation.last_run_at,
            fallback_current_params=fallback_current_params,
        )
        payload = self.recommendation_service.parse_suggestion_payload(recommendation.suggestion) or {}
        metadata = self.recommendation_service.read_storage_metadata(recommendation.suggestion)

        post_effect_summary = _resolve_post_effect_summary(metadata.get("pe"))
        comparison_before = _resolve_comparison(metadata.get("pecb"))
        comparison_preview = _resolve_comparison(metadata.get("pecp"))

        actual_effect_evaluated = bool(metadata.get("aee") or bool(post_effect_summary))
        insufficient_data = bool(metadata.get("pei") is True)
        observation_window_minutes = _as_int(metadata.get("pew"))
        evaluated_at = _parse_iso_utc(metadata.get("pea"))
        applied_at = _parse_iso_utc(metadata.get("apa"))

        if applied_at is None and isinstance(metadata.get("la"), str):
            if str(metadata.get("hs") or "").strip().lower() == "applied" and not actual_effect_evaluated:
                applied_at = _parse_iso_utc(metadata.get("la"))

        history_state = _normalize_history_state(
            parsed.history_state if parsed else metadata.get("hs"),
            applied_at=applied_at,
            actual_effect_evaluated=actual_effect_evaluated,
        )

        problem_type_reason, expected_effect_reason = self.recommendation_service.parse_reason_fields(recommendation.reason)
        risk_level_reason, requires_confirmation_reason = self.recommendation_service.parse_risk_fields(recommendation.risk)

        problem_type = parsed.problem_type.value if parsed else (problem_type_reason or "unknown")
        expected_effect = parsed.expected_effect.value if parsed else expected_effect_reason
        risk_level = parsed.risk_level.value if parsed else risk_level_reason
        requires_confirmation = (
            bool(parsed.requires_confirmation)
            if parsed is not None
            else bool(requires_confirmation_reason) if requires_confirmation_reason is not None else False
        )

        current_params = payload.get("current_params") if isinstance(payload.get("current_params"), dict) else None
        recommended_params = payload.get("recommended_params") if isinstance(payload.get("recommended_params"), dict) else None
        delta_params = payload.get("delta") if isinstance(payload.get("delta"), dict) else None

        if parsed is not None:
            current_params = {
                "kp": float(parsed.current_params.kp),
                "ki": float(parsed.current_params.ki),
                "kd": float(parsed.current_params.kd),
            }
            recommended_params = {
                "kp": float(parsed.recommended_params.kp),
                "ki": float(parsed.recommended_params.ki),
                "kd": float(parsed.recommended_params.kd),
            }
            delta_params = {
                "kp": float(parsed.delta.kp),
                "ki": float(parsed.delta.ki),
                "kd": float(parsed.delta.kd),
            }

        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}

        preview_metrics, preview_source = _resolve_preview_summary(metadata.get("pvs"))

        effect_outcome = _derive_effect_outcome(comparison_before if comparison_before else None)
        if history_state != "applied" and not actual_effect_evaluated:
            effect_outcome = "pending"
        elif insufficient_data:
            # Insufficient post-apply telemetry means outcome is not reliable yet.
            # Keep it non-completed to avoid mixing with true evaluated outcomes.
            effect_outcome = "pending"

        if history_state != "applied":
            evaluation_status = "not_applied"
        elif insufficient_data:
            # Domain semantic: once marked insufficient_data after apply, this state
            # should outrank pending even when aee/post-effect summary is missing.
            evaluation_status = "insufficient_data"
        elif not actual_effect_evaluated:
            evaluation_status = "pending"
        else:
            evaluation_status = "completed"

        feedback_usable_for_training = bool(
            history_state == "applied"
            and actual_effect_evaluated
            and not insufficient_data
            and bool(comparison_before)
        )

        preview_gap_level = _derive_preview_gap_level(comparison_preview if comparison_preview else None)

        sample = {
            # A. sample identity
            "recommendation_id": recommendation.id,
            "device_id": device.id,
            "device_code": device.code,
            "device_name": device.name,
            "device_line": device.line,
            "device_location": device.location,
            # B. recommendation context
            "generated_at": recommendation.last_run_at,
            "applied_at": applied_at,
            "evaluated_at": evaluated_at,
            "history_state": history_state,
            "observation_window_minutes": observation_window_minutes,
            "actual_effect_evaluated": actual_effect_evaluated,
            "insufficient_data": insufficient_data,
            # C. recommendation semantics
            "problem_type": problem_type,
            "expected_effect": expected_effect,
            "risk_level": risk_level,
            "confidence": float(recommendation.confidence),
            "requires_confirmation": requires_confirmation,
            # D. PID params
            "baseline_kp": _safe_pid_value(current_params, "kp"),
            "baseline_ki": _safe_pid_value(current_params, "ki"),
            "baseline_kd": _safe_pid_value(current_params, "kd"),
            "recommended_kp": _safe_pid_value(recommended_params, "kp"),
            "recommended_ki": _safe_pid_value(recommended_params, "ki"),
            "recommended_kd": _safe_pid_value(recommended_params, "kd"),
            "delta_kp": _safe_pid_value(delta_params, "kp"),
            "delta_ki": _safe_pid_value(delta_params, "ki"),
            "delta_kd": _safe_pid_value(delta_params, "kd"),
            # E. evidence/features from recommendation payload
            "mean_error": _as_float(evidence.get("mean_error")),
            "mean_abs_error": _as_float(evidence.get("mean_abs_error")),
            "error_std": _as_float(evidence.get("error_std")),
            "temp_swing": _as_float(evidence.get("temp_swing")),
            "pwm_mean": _as_float(evidence.get("pwm_mean")),
            "pwm_max": _as_float(evidence.get("pwm_max")),
            "zero_crossings": _as_int(evidence.get("zero_crossings")),
            "in_band_ratio": _as_float(evidence.get("in_band_ratio")),
            "overshoot_pct": _as_float(evidence.get("overshoot_pct")),
            "settling_sec": _as_float(evidence.get("settling_sec")),
            "saturation_ratio": _as_float(evidence.get("saturation_ratio")),
            "rule_saturation_limited": bool(evidence.get("rule_saturation_limited")) if "rule_saturation_limited" in evidence else None,
            "rule_overshoot_high": bool(evidence.get("rule_overshoot_high")) if "rule_overshoot_high" in evidence else None,
            "rule_slow_response": bool(evidence.get("rule_slow_response")) if "rule_slow_response" in evidence else None,
            "rule_steady_state_error": bool(evidence.get("rule_steady_state_error")) if "rule_steady_state_error" in evidence else None,
            "rule_oscillation": bool(evidence.get("rule_oscillation")) if "rule_oscillation" in evidence else None,
            # F. preview summary
            "preview_in_band_ratio": _as_float(preview_metrics.get("in_band_ratio")),
            "preview_overshoot_c": _as_float(preview_metrics.get("overshoot_c")),
            "preview_settling_sec": _as_float(preview_metrics.get("settling_sec")),
            "preview_mean_abs_error": _as_float(preview_metrics.get("mean_abs_error")),
            "preview_saturation_ratio": _as_float(preview_metrics.get("saturation_ratio")),
            "preview_temp_swing": _as_float(preview_metrics.get("temp_swing")),
            "preview_source": preview_source,
            # G. actual post-effect summary
            "actual_point_count": _as_int(post_effect_summary.get("point_count")),
            "actual_observed_window_start": _parse_iso_utc(post_effect_summary.get("observed_window_start"))
            if isinstance(post_effect_summary.get("observed_window_start"), str)
            else post_effect_summary.get("observed_window_start"),
            "actual_observed_window_end": _parse_iso_utc(post_effect_summary.get("observed_window_end"))
            if isinstance(post_effect_summary.get("observed_window_end"), str)
            else post_effect_summary.get("observed_window_end"),
            "actual_in_band_ratio": _as_float(post_effect_summary.get("in_band_ratio_after")),
            "actual_overshoot_c": _as_float(post_effect_summary.get("overshoot_c_after")),
            "actual_settling_sec": _as_float(post_effect_summary.get("settling_sec_after")),
            "actual_mean_abs_error": _as_float(post_effect_summary.get("mean_abs_error_after")),
            "actual_saturation_ratio": _as_float(post_effect_summary.get("saturation_ratio_after")),
            "actual_temp_swing": _as_float(post_effect_summary.get("temp_swing_after")),
            # H. before vs actual
            "before_in_band_ratio_delta": _as_float(comparison_before.get("in_band_ratio_delta")),
            "before_overshoot_c_delta": _as_float(comparison_before.get("overshoot_c_delta")),
            "before_settling_sec_delta": _as_float(comparison_before.get("settling_sec_delta")),
            "before_mean_abs_error_delta": _as_float(comparison_before.get("mean_abs_error_delta")),
            "before_saturation_ratio_delta": _as_float(comparison_before.get("saturation_ratio_delta")),
            "before_temp_swing_delta": _as_float(comparison_before.get("temp_swing_delta")),
            # I. preview vs actual
            "preview_gap_in_band_ratio": _as_float(comparison_preview.get("in_band_ratio_delta")),
            "preview_gap_overshoot_c": _as_float(comparison_preview.get("overshoot_c_delta")),
            "preview_gap_settling_sec": _as_float(comparison_preview.get("settling_sec_delta")),
            "preview_gap_mean_abs_error": _as_float(comparison_preview.get("mean_abs_error_delta")),
            "preview_gap_saturation_ratio": _as_float(comparison_preview.get("saturation_ratio_delta")),
            "preview_gap_temp_swing": _as_float(comparison_preview.get("temp_swing_delta")),
            # J. labels
            "effect_outcome": effect_outcome,
            "evaluation_status": evaluation_status,
            "preview_gap_level": preview_gap_level,
            "feedback_usable_for_training": feedback_usable_for_training,
        }
        return sample

    def iter_feedback_samples(
        self,
        *,
        db: Session,
        device_id: Optional[int] = None,
        limit: Optional[int] = None,
        only_usable: bool = False,
    ) -> Iterable[dict[str, Any]]:
        # Avoid joining DeviceParameter in the main query: one device may have
        # multiple parameter rows, which can multiply one recommendation into
        # duplicated dataset samples.
        stmt = (
            select(AIRecommendation, Device)
            .join(Device, Device.id == AIRecommendation.device_id)
            .order_by(AIRecommendation.last_run_at.asc(), AIRecommendation.id.asc())
        )
        if device_id is not None:
            stmt = stmt.where(AIRecommendation.device_id == int(device_id))
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))

        rows = db.execute(stmt).all()
        seen_recommendation_ids: set[int] = set()
        latest_params_cache: dict[int, Optional[DeviceParameter]] = {}

        for recommendation, device in rows:
            if recommendation.id in seen_recommendation_ids:
                raise ValueError(
                    f"Duplicate recommendation_id detected during dataset build: {recommendation.id}"
                )
            seen_recommendation_ids.add(recommendation.id)

            params = latest_params_cache.get(device.id)
            if device.id not in latest_params_cache:
                params = db.scalar(
                    select(DeviceParameter)
                    .where(DeviceParameter.device_id == device.id)
                    .order_by(DeviceParameter.updated_at.desc(), DeviceParameter.id.desc())
                    .limit(1)
                )
                latest_params_cache[device.id] = params
            fallback = PIDParams(
                kp=float(params.kp) if params is not None else 0.0,
                ki=float(params.ki) if params is not None else 0.0,
                kd=float(params.kd) if params is not None else 0.0,
            )
            sample = self.build_feedback_sample(
                recommendation=recommendation,
                device=device,
                fallback_current_params=fallback,
            )
            if only_usable and not bool(sample.get("feedback_usable_for_training")):
                continue
            yield sample

    def build_feedback_dataset(
        self,
        *,
        db: Session,
        device_id: Optional[int] = None,
        limit: Optional[int] = None,
        only_usable: bool = False,
    ) -> list[dict[str, Any]]:
        rows = list(
            self.iter_feedback_samples(
                db=db,
                device_id=device_id,
                limit=limit,
                only_usable=only_usable,
            )
        )
        self.validate_feedback_dataset(rows)
        return rows

    def validate_feedback_dataset(self, rows: Iterable[dict[str, Any]]) -> None:
        items = list(rows)
        recommendation_ids = [
            rid
            for rid in (_as_int(r.get("recommendation_id")) for r in items)
            if rid is not None
        ]
        unique_count = len(set(recommendation_ids))
        duplicate_count = len(recommendation_ids) - unique_count
        if duplicate_count > 0:
            raise ValueError(
                f"Duplicate recommendation_id found in feedback dataset: duplicates={duplicate_count}"
            )

        for row in items:
            if bool(row.get("feedback_usable_for_training")) and bool(row.get("insufficient_data")):
                rid = row.get("recommendation_id")
                raise ValueError(
                    f"Invalid feedback sample: recommendation_id={rid} marked usable but insufficient_data=true"
                )

    def summarize_feedback_dataset(self, rows: Iterable[dict[str, Any]]) -> RecommendationFeedbackDatasetSummary:
        items = list(rows)
        summary = RecommendationFeedbackDatasetSummary()
        summary.total_recommendation_records = len(items)
        recommendation_ids = [
            rid
            for rid in (_as_int(r.get("recommendation_id")) for r in items)
            if rid is not None
        ]
        summary.unique_recommendation_ids = len(set(recommendation_ids))
        summary.duplicate_recommendation_ids_count = len(recommendation_ids) - summary.unique_recommendation_ids
        summary.applied_recommendation_records = sum(1 for r in items if r.get("history_state") == "applied")
        summary.evaluated_recommendation_records = sum(1 for r in items if bool(r.get("actual_effect_evaluated")))
        summary.insufficient_data_count = sum(1 for r in items if bool(r.get("insufficient_data")))
        summary.trainable_samples_count = sum(1 for r in items if bool(r.get("feedback_usable_for_training")))

        summary.improved_count = sum(1 for r in items if r.get("effect_outcome") == "improved")
        summary.unchanged_count = sum(1 for r in items if r.get("effect_outcome") == "unchanged")
        summary.worse_count = sum(1 for r in items if r.get("effect_outcome") == "worse")
        summary.pending_count = sum(1 for r in items if r.get("effect_outcome") == "pending")

        summary.preview_gap_low_count = sum(1 for r in items if r.get("preview_gap_level") == "low")
        summary.preview_gap_medium_count = sum(1 for r in items if r.get("preview_gap_level") == "medium")
        summary.preview_gap_high_count = sum(1 for r in items if r.get("preview_gap_level") == "high")

        confidences = [v for v in (_as_float(r.get("confidence")) for r in items) if v is not None]
        delta_kp = [v for v in (_as_float(r.get("delta_kp")) for r in items) if v is not None]
        delta_ki = [v for v in (_as_float(r.get("delta_ki")) for r in items) if v is not None]
        delta_kd = [v for v in (_as_float(r.get("delta_kd")) for r in items) if v is not None]

        if confidences:
            summary.average_confidence = sum(confidences) / len(confidences)
        if delta_kp:
            summary.average_delta_kp = sum(delta_kp) / len(delta_kp)
        if delta_ki:
            summary.average_delta_ki = sum(delta_ki) / len(delta_ki)
        if delta_kd:
            summary.average_delta_kd = sum(delta_kd) / len(delta_kd)

        return summary
