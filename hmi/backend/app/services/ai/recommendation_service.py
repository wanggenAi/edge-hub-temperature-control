from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Optional, Union

from app.services.ai.feature_extractor import extract_features
from app.services.ai.problem_classifier import classify_problem
from app.services.ai.schemas import PIDParams, RecommendationGenerateInput, RecommendationGenerateOutput
from app.services.ai.tuning_engine import build_recommendation


class RecommendationService:
    _LEGACY_GAIN_PATTERN = re.compile(r"(Kp|Ki|Kd)\s*:\s*([+-]?\d+(?:\.\d+)?)")

    def generate(self, payload: RecommendationGenerateInput) -> RecommendationGenerateOutput:
        features = extract_features(payload)
        problem_type, confidence, rules = classify_problem(payload, features)
        current_params, recommended_params, delta, risk_level, requires_confirmation, expected_effect = build_recommendation(
            problem_type, payload.current_params
        )

        evidence: dict[str, Union[float, int, str, bool, None]] = {
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

    def to_storage_fields(self, output: RecommendationGenerateOutput) -> tuple[str, str, str]:
        reason = f"{output.problem_type.value}; effect={output.expected_effect.value}"
        risk = f"{output.risk_level.value}; requires_confirmation={output.requires_confirmation}"
        recommended = output.recommended_params.model_dump(mode="json")
        delta = output.delta.model_dump(mode="json")
        suggestion = json.dumps(
            {
                "f": "ai_rec",
                "v": "1",
                "p": {
                    "t": output.problem_type.value,
                    "e": output.expected_effect.value,
                    "r": output.risk_level.value,
                    "c": round(output.confidence, 4),
                    "rc": output.requires_confirmation,
                    "rp": {
                        "kp": round(float(recommended["kp"]), 4),
                        "ki": round(float(recommended["ki"]), 4),
                        "kd": round(float(recommended["kd"]), 4),
                    },
                    "d": {
                        "kp": round(float(delta["kp"]), 4),
                        "ki": round(float(delta["ki"]), 4),
                        "kd": round(float(delta["kd"]), 4),
                    },
                },
            },
            separators=(",", ":"),
        )
        return reason, suggestion, risk

    def parse_recommended_params(self, suggestion: str, current_params: PIDParams) -> Optional[PIDParams]:
        if not suggestion:
            return None

        try:
            body = json.loads(suggestion)
            if isinstance(body, dict) and body.get("f") == "ai_rec":
                compact_payload = body.get("p")
                if isinstance(compact_payload, dict):
                    rec = compact_payload.get("rp")
                    if isinstance(rec, dict):
                        return PIDParams(
                            kp=float(rec.get("kp", current_params.kp)),
                            ki=float(rec.get("ki", current_params.ki)),
                            kd=float(rec.get("kd", current_params.kd)),
                        )
                    delta = compact_payload.get("d")
                    if isinstance(delta, dict):
                        return PIDParams(
                            kp=round(current_params.kp + float(delta.get("kp", 0.0)), 4),
                            ki=round(current_params.ki + float(delta.get("ki", 0.0)), 4),
                            kd=round(current_params.kd + float(delta.get("kd", 0.0)), 4),
                        )

            payload = body.get("payload") if isinstance(body, dict) else None
            if isinstance(payload, dict):
                rec = payload.get("recommended_params")
                if isinstance(rec, dict):
                    return PIDParams(
                        kp=float(rec.get("kp", current_params.kp)),
                        ki=float(rec.get("ki", current_params.ki)),
                        kd=float(rec.get("kd", current_params.kd)),
                    )
                delta = payload.get("delta")
                if isinstance(delta, dict):
                    return PIDParams(
                        kp=round(current_params.kp + float(delta.get("kp", 0.0)), 4),
                        ki=round(current_params.ki + float(delta.get("ki", 0.0)), 4),
                        kd=round(current_params.kd + float(delta.get("kd", 0.0)), 4),
                    )
        except (ValueError, TypeError):
            pass

        updates: dict[str, float] = {}
        for key, value in self._LEGACY_GAIN_PATTERN.findall(suggestion):
            updates[key.lower()] = float(value)
        if not updates:
            return None
        return PIDParams(
            kp=round(current_params.kp + updates.get("kp", 0.0), 4),
            ki=round(current_params.ki + updates.get("ki", 0.0), 4),
            kd=round(current_params.kd + updates.get("kd", 0.0), 4),
        )
