from __future__ import annotations

import unittest
from datetime import datetime

from app.services.ai.enums import ExpectedEffect, ProblemType, RiskLevel
from app.services.ai.problem_classifier import classify_problem
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import (
    CurrentState,
    DeviceIdentity,
    FeatureSet,
    HistoryWindow,
    PIDParams,
    RecommendationGenerateInput,
    RecommendationGenerateOutput,
)


class ProblemClassifierMultilabelTests(unittest.TestCase):
    def test_classify_problem_returns_primary_secondary_and_flags(self) -> None:
        payload = RecommendationGenerateInput(
            device=DeviceIdentity(id=1, code="TC-T", name="Test"),
            current_state=CurrentState(current_temp=30.0, target_temp=37.0, pwm_output=92.0),
            current_params=PIDParams(kp=2.4, ki=0.3, kd=0.1),
            history_window=HistoryWindow(start_ms=0, end_ms=1, points=[]),
        )
        features = FeatureSet(
            mean_error=0.1,
            mean_abs_error=1.1,
            error_std=0.9,
            temp_swing=2.2,
            pwm_mean=88.0,
            pwm_max=100.0,
            zero_crossings=22,
            in_band_ratio=0.25,
            overshoot_pct=5.1,
            settling_sec=None,
            saturation_ratio=0.65,
        )

        primary, secondary, flags, confidence = classify_problem(payload, features)
        self.assertEqual(primary, ProblemType.SATURATION_LIMITED)
        self.assertIn(ProblemType.OSCILLATION, secondary)
        self.assertIn(ProblemType.OVERSHOOT_HIGH, secondary)
        self.assertTrue(flags["severe_saturation"])
        self.assertTrue(flags["oscillation"])
        self.assertAlmostEqual(confidence, 0.9)

    def test_storage_roundtrip_preserves_new_problem_fields(self) -> None:
        service = RecommendationService()
        output = RecommendationGenerateOutput(
            problem_type=ProblemType.OSCILLATION,
            primary_problem_type=ProblemType.OSCILLATION,
            secondary_problem_types=[ProblemType.OVERSHOOT_HIGH],
            problem_flags={
                "saturation_limited": False,
                "severe_saturation": False,
                "oscillation": True,
                "overshoot_high": True,
                "steady_state_error": False,
                "slow_response": False,
            },
            confidence=0.84,
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=True,
            current_params=PIDParams(kp=2.2, ki=0.32, kd=0.1),
            recommended_params=PIDParams(kp=1.7, ki=0.2, kd=0.28),
            delta=PIDParams(kp=-0.5, ki=-0.12, kd=0.18),
            expected_effect=ExpectedEffect.REDUCE_OSCILLATION,
            evidence={"rule_oscillation": True, "rule_overshoot_high": True, "error_std": 0.88},
            generated_at=datetime.utcnow(),
        )

        reason, suggestion, risk = service.to_storage_fields(output)
        parsed = service.build_output_from_storage(
            reason=reason,
            suggestion=suggestion,
            risk=risk,
            confidence=output.confidence,
            generated_at=output.generated_at,
            fallback_current_params=output.current_params,
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.problem_type, ProblemType.OSCILLATION)
        self.assertEqual(parsed.primary_problem_type, ProblemType.OSCILLATION)
        self.assertEqual(parsed.secondary_problem_types, [ProblemType.OVERSHOOT_HIGH])
        self.assertTrue(parsed.problem_flags.get("oscillation"))


if __name__ == "__main__":
    unittest.main()
