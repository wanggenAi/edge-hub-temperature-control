from __future__ import annotations

from app.services.ai.enums import ProblemType
from app.services.ai.schemas import FeatureSet, RecommendationGenerateInput


def _compute_problem_flags(payload: RecommendationGenerateInput, features: FeatureSet) -> dict[str, bool]:
    severe_saturation = features.saturation_ratio >= payload.saturation_high_ratio
    return {
        # Saturation is evaluated first because actuator headroom is already limited.
        "saturation_limited": features.saturation_ratio >= payload.saturation_warn_ratio,
        "severe_saturation": severe_saturation,
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


def _derive_labels(flags: dict[str, bool]) -> tuple[ProblemType, list[ProblemType], float]:
    primary_priority: list[tuple[str, ProblemType, float]] = [
        ("severe_saturation", ProblemType.SATURATION_LIMITED, 0.9),
        ("oscillation", ProblemType.OSCILLATION, 0.82),
        ("overshoot_high", ProblemType.OVERSHOOT_HIGH, 0.8),
        ("steady_state_error", ProblemType.STEADY_STATE_ERROR, 0.76),
        ("slow_response", ProblemType.SLOW_RESPONSE, 0.72),
        ("saturation_limited", ProblemType.SATURATION_LIMITED, 0.74),
    ]
    secondary_priority: list[tuple[str, ProblemType]] = [
        ("oscillation", ProblemType.OSCILLATION),
        ("overshoot_high", ProblemType.OVERSHOOT_HIGH),
        ("steady_state_error", ProblemType.STEADY_STATE_ERROR),
        ("slow_response", ProblemType.SLOW_RESPONSE),
        ("severe_saturation", ProblemType.SATURATION_LIMITED),
        ("saturation_limited", ProblemType.SATURATION_LIMITED),
    ]

    primary = ProblemType.NORMAL
    confidence = 0.9
    for key, problem, score in primary_priority:
        if flags.get(key):
            primary = problem
            confidence = score
            break

    secondary: list[ProblemType] = []
    seen: set[ProblemType] = {primary}
    for key, problem in secondary_priority:
        if not flags.get(key):
            continue
        if problem in seen:
            continue
        secondary.append(problem)
        seen.add(problem)
    return primary, secondary, confidence


def classify_problem(
    payload: RecommendationGenerateInput,
    features: FeatureSet,
) -> tuple[ProblemType, list[ProblemType], dict[str, bool], float]:
    flags = _compute_problem_flags(payload, features)
    primary, secondary, confidence = _derive_labels(flags)
    return primary, secondary, flags, confidence
