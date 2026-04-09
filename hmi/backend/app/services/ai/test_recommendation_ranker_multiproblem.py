from __future__ import annotations

import unittest

from app.services.ai.recommendation_ranker import RecommendationRanker, RecommendationRankingContext
from app.services.ai.schemas import PIDParams


class RecommendationRankerMultiProblemTests(unittest.TestCase):
    def _ranker(self) -> RecommendationRanker:
        # generate_candidates() does not use model inference.
        return RecommendationRanker(success_model=object(), preview_gap_model=object(), candidate_count=8)

    def _context(
        self,
        *,
        primary: str,
        secondary: list[str] | None = None,
        flags: dict[str, bool] | None = None,
    ) -> RecommendationRankingContext:
        return RecommendationRankingContext(
            recommendation_id=1,
            device_id=1,
            device_code="UT-DEV",
            baseline_params=PIDParams(kp=2.0, ki=0.30, kd=0.10),
            base_recommended_params=PIDParams(kp=2.4, ki=0.36, kd=0.14),
            evidence={},
            current_temp=36.8,
            target_temp=37.0,
            predicted_problem_type=primary,
            secondary_problem_types=secondary or [],
            problem_flags=flags or {},
        )

    def _candidate_map(self, ranked: list) -> dict[str, object]:
        return {c.candidate_id: c for c in ranked}

    def test_oscillation_with_overshoot_secondary_adds_overshoot_aware_compromise(self) -> None:
        ranker = self._ranker()
        ctx = self._context(primary="oscillation", secondary=["overshoot_high"])
        candidates = ranker.generate_candidates(context=ctx)
        ids = [c.candidate_id for c in candidates]
        self.assertIn("rule_center", ids)
        self.assertIn("overshoot_guard", ids)
        self.assertIn("oscillation_overshoot_balance", ids)

    def test_sse_with_slow_response_adds_balance_candidate(self) -> None:
        ranker = self._ranker()
        ctx = self._context(primary="steady_state_error", secondary=["slow_response"])
        candidates = ranker.generate_candidates(context=ctx)
        ids = [c.candidate_id for c in candidates]
        self.assertIn("rule_center", ids)
        self.assertIn("sse_speed_balance", ids)

    def test_saturation_flags_reduce_aggressiveness_and_add_safe_candidate(self) -> None:
        ranker = self._ranker()
        base_ctx = self._context(primary="slow_response")
        sat_ctx = self._context(primary="slow_response", flags={"saturation_limited": True})
        base_map = self._candidate_map(ranker.generate_candidates(context=base_ctx))
        sat_map = self._candidate_map(ranker.generate_candidates(context=sat_ctx))
        base_aggressive = base_map["aggressive"]
        sat_aggressive = sat_map["aggressive"]
        # With saturation constraints, aggressive candidate should not be more aggressive on Kp/Ki.
        self.assertLessEqual(float(sat_aggressive.recommended_params.kp), float(base_aggressive.recommended_params.kp))
        self.assertLessEqual(float(sat_aggressive.recommended_params.ki), float(base_aggressive.recommended_params.ki))
        self.assertIn("saturation_safe_recovery", sat_map)

    def test_rule_center_always_present(self) -> None:
        ranker = self._ranker()
        for ctx in [
            self._context(primary="oscillation", secondary=["overshoot_high"]),
            self._context(primary="steady_state_error", secondary=["slow_response"]),
            self._context(primary="slow_response", secondary=["steady_state_error"]),
            self._context(primary="normal"),
        ]:
            ids = [c.candidate_id for c in ranker.generate_candidates(context=ctx)]
            self.assertIn("rule_center", ids)

    def test_secondary_refines_but_primary_direction_remains(self) -> None:
        ranker = self._ranker()
        ctx = self._context(primary="slow_response", secondary=["steady_state_error"])
        cmap = self._candidate_map(ranker.generate_candidates(context=ctx))
        rule_center = cmap["rule_center"]
        aggressive = cmap["aggressive"]
        balance = cmap["sse_speed_balance"]
        # Primary slow_response keeps speed-up direction: aggressive Kp still above rule-center.
        self.assertGreater(float(aggressive.recommended_params.kp), float(rule_center.recommended_params.kp))
        # Secondary steady-state_error adds Ki-aware compromise candidate.
        self.assertGreater(float(balance.recommended_params.ki), float(rule_center.recommended_params.ki))


if __name__ == "__main__":
    unittest.main()

