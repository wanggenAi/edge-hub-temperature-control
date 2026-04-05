from __future__ import annotations

from datetime import datetime

from app.services.ai.feature_extractor import extract_features
from app.services.ai.problem_classifier import classify_problem
from app.services.ai.schemas import RecommendationGenerateInput, RecommendationGenerateOutput
from app.services.ai.tuning_engine import build_recommendation


class RecommendationService:
    def generate(self, payload: RecommendationGenerateInput) -> RecommendationGenerateOutput:
        features = extract_features(payload)
        problem_type, confidence, rules = classify_problem(payload, features)
        current_params, recommended_params, delta, risk_level, requires_confirmation, expected_effect = build_recommendation(
            problem_type, payload.current_params
        )

        evidence: dict[str, float | int | str | bool | None] = {
            "rule_saturation_limited": rules.get("saturation_limited", False),
            "rule_oscillation": rules.get("oscillation", False),
            "rule_overshoot_high": rules.get("overshoot_high", False),
            "rule_steady_state_error": rules.get("steady_state_error", False),
            "rule_slow_response": rules.get("slow_response", False),
            "mean_error": round(features.mean_error, 4),
            "mean_abs_error": round(features.mean_abs_error, 4),
            "error_std": round(features.error_std, 4),
            "temp_swing": round(features.temp_swing, 4),
            "pwm_mean": round(features.pwm_mean, 4),
            "pwm_max": round(features.pwm_max, 4),
            "zero_crossings": features.zero_crossings,
            "in_band_ratio": round(features.in_band_ratio, 4),
            "overshoot_pct": round(features.overshoot_pct, 4),
            "settling_sec": None if features.settling_sec is None else round(features.settling_sec, 4),
            "saturation_ratio": round(features.saturation_ratio, 4),
        }

        return RecommendationGenerateOutput(
            problem_type=problem_type,
            confidence=round(confidence, 4),
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            current_params=current_params,
            recommended_params=recommended_params,
            delta=delta,
            expected_effect=expected_effect,
            evidence=evidence,
            generated_at=datetime.utcnow(),
        )
