from __future__ import annotations

import unittest

from app.services.ai.recommendation_orchestrator import RecommendationOrchestrator
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import (
    CurrentState,
    DeviceIdentity,
    HistoryPoint,
    HistoryWindow,
    PIDParams,
    RecommendationGenerateInput,
)


class _FakeRanker:
    def rank_candidates(self, *, context):  # type: ignore[no-untyped-def]
        baseline = context.baseline_params
        center = context.base_recommended_params
        aggressive = {
            "kp": float(center.kp) * 1.1 + 0.01,
            "ki": float(center.ki) * 1.1 + 0.01,
            "kd": max(0.0, float(center.kd) * 0.95),
        }
        return [
            {
                "candidate_id": "aggressive",
                "recommended_params": aggressive,
                "total_score": 0.91,
                "success_model": {"success_score": 0.44},
                "preview_gap_model": {"gap_score": 0.31},
            },
            {
                "candidate_id": "rule_center",
                "recommended_params": {"kp": float(center.kp), "ki": float(center.ki), "kd": float(center.kd)},
                "total_score": 0.75,
                "success_model": {"success_score": 0.32},
                "preview_gap_model": {"gap_score": 0.22},
            },
            {
                "candidate_id": "baseline_hold",
                "recommended_params": {"kp": float(baseline.kp), "ki": float(baseline.ki), "kd": float(baseline.kd)},
                "total_score": 0.10,
                "success_model": {"success_score": -0.05},
                "preview_gap_model": {"gap_score": 0.06},
            },
        ]


class RecommendationOrchestratorTests(unittest.TestCase):
    def _payload(self) -> RecommendationGenerateInput:
        points = [
            HistoryPoint(ts_ms=1000 * i, current_temp=36.5 + (i % 7) * 0.08, target_temp=37.0, error=-0.5, pwm_output=74.0)
            for i in range(1, 80)
        ]
        return RecommendationGenerateInput(
            device=DeviceIdentity(id=1, code="UT-ORCH-1", name="UT Orchestrator"),
            current_state=CurrentState(current_temp=36.9, target_temp=37.0, pwm_output=71.0),
            current_params=PIDParams(kp=2.4, ki=0.35, kd=0.12),
            history_window=HistoryWindow(start_ms=0, end_ms=80_000, points=points),
            target_band=0.5,
            steady_window_samples=12,
            overshoot_limit_pct=3.0,
            pwm_saturation_threshold=85.0,
            saturation_warn_ratio=0.3,
            saturation_high_ratio=0.6,
        )

    def test_ranking_success_preserves_rule_diagnosis_and_base_recommendation_metadata(self) -> None:
        service = RecommendationService()
        orchestrator = RecommendationOrchestrator(service)
        orchestrator._load_ranker = lambda: _FakeRanker()  # type: ignore[method-assign]

        payload = self._payload()
        base = service.generate(payload)
        result = orchestrator.generate_ranked_recommendation(
            payload=payload,
            runtime_source="ai_runtime_service",
            fallback_used=False,
        )

        # Diagnosis remains rule-driven.
        self.assertEqual(result.output.primary_problem_type, base.primary_problem_type)
        self.assertEqual(result.output.secondary_problem_types, base.secondary_problem_types)
        self.assertEqual(result.output.problem_flags, base.problem_flags)
        # Ranking may change final recommendation.
        self.assertNotEqual(result.output.recommended_params, base.recommended_params)
        # Runtime decision explicitly separates rule diagnosis/base recommendation from ranked selection.
        self.assertEqual(result.runtime_decision.get("diagnosis_source"), "rule_classifier")
        self.assertEqual(result.runtime_decision.get("base_recommendation_source"), "rule_tuning_engine")
        self.assertEqual(result.runtime_decision.get("base_candidate_id"), "rule_center")
        self.assertEqual(result.runtime_decision.get("selected_candidate_id"), "aggressive")
        self.assertTrue(bool(result.runtime_decision.get("ranking_used")))
        self.assertFalse(bool(result.runtime_decision.get("ranking_fallback_used")))
        self.assertEqual(result.runtime_decision.get("candidate_count"), 3)
        self.assertIn("base_recommended_params", result.runtime_decision)
        self.assertEqual(
            result.runtime_decision["base_recommended_params"],
            {"kp": float(base.recommended_params.kp), "ki": float(base.recommended_params.ki), "kd": float(base.recommended_params.kd)},
        )

    def test_ranking_failure_falls_back_to_rule_center(self) -> None:
        service = RecommendationService()
        orchestrator = RecommendationOrchestrator(service)
        orchestrator._load_ranker = lambda: (_ for _ in ()).throw(RuntimeError("model_not_ready"))  # type: ignore[method-assign]

        payload = self._payload()
        base = service.generate(payload)
        result = orchestrator.generate_ranked_recommendation(
            payload=payload,
            runtime_source="local_backend",
            fallback_used=True,
            fallback_reason="runtime_unreachable",
        )

        self.assertEqual(result.output.recommended_params, base.recommended_params)
        self.assertEqual(result.runtime_decision.get("selected_candidate_id"), "rule_center")
        self.assertFalse(bool(result.runtime_decision.get("ranking_used")))
        self.assertTrue(bool(result.runtime_decision.get("ranking_fallback_used")))
        self.assertEqual(result.runtime_decision.get("runtime_source"), "local_backend")
        self.assertTrue(bool(result.runtime_decision.get("fallback_used")))
        self.assertIn("ranking_fallback_reason", result.runtime_decision)

    def test_ranker_failure_does_not_block_future_retry(self) -> None:
        service = RecommendationService()
        orchestrator = RecommendationOrchestrator(service)
        calls = {"n": 0}

        def flaky_loader():  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("ranker_model_not_found")
            return _FakeRanker()

        orchestrator._load_ranker = flaky_loader  # type: ignore[method-assign]
        payload = self._payload()

        first = orchestrator.generate_ranked_recommendation(
            payload=payload,
            runtime_source="ai_runtime_service",
            fallback_used=False,
        )
        self.assertFalse(bool(first.runtime_decision.get("ranking_used")))
        self.assertTrue(bool(first.runtime_decision.get("ranking_fallback_used")))

        second = orchestrator.generate_ranked_recommendation(
            payload=payload,
            runtime_source="ai_runtime_service",
            fallback_used=False,
        )
        self.assertTrue(bool(second.runtime_decision.get("ranking_used")))
        self.assertFalse(bool(second.runtime_decision.get("ranking_fallback_used")))


if __name__ == "__main__":
    unittest.main()
