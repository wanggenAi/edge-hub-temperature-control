from __future__ import annotations

from app.services.ai.enums import ProblemType
from app.services.ai.schemas import FeatureSet, RecommendationGenerateInput


def classify_problem(payload: RecommendationGenerateInput, features: FeatureSet) -> tuple[ProblemType, float, dict[str, bool]]:
    rules: dict[str, bool] = {
        # 饱和优先级最高：当执行器长期贴边时，继续加大增益通常收益有限且风险高。
        "saturation_limited": features.saturation_ratio >= payload.saturation_warn_ratio,
        # 振荡：误差零交叉频繁 + 波动较大，通常是 Kp/Ki 偏高或 Kd 不足。
        "oscillation": features.zero_crossings >= 6 and features.error_std >= payload.target_band,
        # 超调：峰值超调超过参数阈值。
        "overshoot_high": features.overshoot_pct > payload.overshoot_limit_pct,
        # 稳态误差：误差偏置明显且最终未进入目标带。
        "steady_state_error": abs(features.mean_error) > payload.target_band and features.in_band_ratio < 0.6,
        # 慢响应：绝对误差偏大且收敛慢（长时间未稳定）。
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
