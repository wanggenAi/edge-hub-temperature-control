from __future__ import annotations

from app.services.ai.enums import ProblemType
from app.services.ai.schemas import FeatureSet, RecommendationGenerateInput


def classify_problem(payload: RecommendationGenerateInput, features: FeatureSet) -> tuple[ProblemType, float, dict[str, bool]]:
    rules: dict[str, bool] = {
        # Saturation is evaluated first because actuator headroom is already limited.
        "saturation_limited": features.saturation_ratio >= payload.saturation_warn_ratio,
        # Frequent zero crossings with high error spread indicate oscillation behavior.
        "oscillation": features.zero_crossings >= 6 and features.error_std >= payload.target_band,
        # Overshoot exceeds configured limit.
        "overshoot_high": features.overshoot_pct > payload.overshoot_limit_pct,
        # Mean error remains biased and in-band ratio stays low.
        "steady_state_error": abs(features.mean_error) > payload.target_band and features.in_band_ratio < 0.6,
        # Large absolute error and no fast settling indicate slow response.
        "slow_response": features.mean_abs_error > payload.target_band
        and (features.settling_sec is None or features.settling_sec > 300),
    }

    if rules["saturation_limited"]:
        return ProblemType.SATURATION_LIMITED, 0.86, rules
    if rules["oscillation"]:
        return ProblemType.OSCILLATION, 0.82, rules
    if rules["overshoot_high"]:
        return ProblemType.OVERSHOOT_HIGH, 0.8, rules
    if rules["steady_state_error"]:
        return ProblemType.STEADY_STATE_ERROR, 0.76, rules
    if rules["slow_response"]:
        return ProblemType.SLOW_RESPONSE, 0.72, rules

    return ProblemType.NORMAL, 0.9, rules
