from __future__ import annotations

from app.services.ai.enums import ExpectedEffect, ProblemType, RiskLevel
from app.services.ai.schemas import PIDParams


MAX_STEP_RATIO = 0.2


def _round_params(params: PIDParams) -> PIDParams:
    return PIDParams(kp=round(params.kp, 4), ki=round(params.ki, 4), kd=round(params.kd, 4))


def _bounded_step(value: float, ratio: float) -> float:
    return max(0.01, abs(value) * min(MAX_STEP_RATIO, ratio))


def _derive_recommended(problem_type: ProblemType, current: PIDParams) -> tuple[PIDParams, ExpectedEffect]:
    kp, ki, kd = current.kp, current.ki, current.kd

    if problem_type == ProblemType.NORMAL:
        return _round_params(current), ExpectedEffect.KEEP_STABLE

    if problem_type == ProblemType.SLOW_RESPONSE:
        return _round_params(
            PIDParams(
                kp=kp + _bounded_step(kp, 0.12),
                ki=ki + _bounded_step(ki, 0.08),
                kd=max(0.0, kd - _bounded_step(kd, 0.06)),
            )
        ), ExpectedEffect.SPEED_UP_RESPONSE

    if problem_type == ProblemType.STEADY_STATE_ERROR:
        return _round_params(
            PIDParams(
                kp=kp,
                ki=ki + _bounded_step(ki, 0.15),
                kd=kd,
            )
        ), ExpectedEffect.REDUCE_STEADY_STATE_ERROR

    if problem_type == ProblemType.OVERSHOOT_HIGH:
        return _round_params(
            PIDParams(
                kp=max(0.0, kp - _bounded_step(kp, 0.1)),
                ki=max(0.0, ki - _bounded_step(ki, 0.08)),
                kd=kd + _bounded_step(kd, 0.12),
            )
        ), ExpectedEffect.REDUCE_OVERSHOOT

    if problem_type == ProblemType.OSCILLATION:
        return _round_params(
            PIDParams(
                kp=max(0.0, kp - _bounded_step(kp, 0.12)),
                ki=max(0.0, ki - _bounded_step(ki, 0.1)),
                kd=kd + _bounded_step(kd, 0.15),
            )
        ), ExpectedEffect.REDUCE_OSCILLATION

    return _round_params(
        PIDParams(
            kp=kp + _bounded_step(kp, 0.05),
            ki=ki,
            kd=kd,
        )
    ), ExpectedEffect.LIMITED_GAIN_EXPECTED


def build_recommendation(
    problem_type: ProblemType,
    current_params: PIDParams,
) -> tuple[PIDParams, PIDParams, PIDParams, RiskLevel, bool, ExpectedEffect]:
    recommended, effect = _derive_recommended(problem_type, current_params)
    delta = PIDParams(
        kp=round(recommended.kp - current_params.kp, 4),
        ki=round(recommended.ki - current_params.ki, 4),
        kd=round(recommended.kd - current_params.kd, 4),
    )

    risk = RiskLevel.LOW
    if problem_type in {ProblemType.OVERSHOOT_HIGH, ProblemType.OSCILLATION}:
        risk = RiskLevel.MEDIUM
    if problem_type == ProblemType.SATURATION_LIMITED:
        # Saturation-limited systems have reduced tuning headroom and higher execution risk.
        risk = RiskLevel.HIGH

    requires_confirmation = risk != RiskLevel.LOW
    if problem_type == ProblemType.NORMAL:
        requires_confirmation = False

    return current_params, recommended, delta, risk, requires_confirmation, effect
