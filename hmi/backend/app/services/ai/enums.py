from __future__ import annotations

from enum import Enum


class ProblemType(str, Enum):
    NORMAL = "normal"
    SLOW_RESPONSE = "slow_response"
    STEADY_STATE_ERROR = "steady_state_error"
    OVERSHOOT_HIGH = "overshoot_high"
    OSCILLATION = "oscillation"
    SATURATION_LIMITED = "saturation_limited"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class ExpectedEffect(str, Enum):
    KEEP_STABLE = "keep_stable"
    SPEED_UP_RESPONSE = "speed_up_response"
    REDUCE_STEADY_STATE_ERROR = "reduce_steady_state_error"
    REDUCE_OVERSHOOT = "reduce_overshoot"
    REDUCE_OSCILLATION = "reduce_oscillation"
    LIMITED_GAIN_EXPECTED = "limited_gain_expected"
