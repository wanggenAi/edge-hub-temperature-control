from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.services.ai.recommendation_ranker import RecommendationRanker, RecommendationRankingContext
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import PIDParams, RecommendationGenerateInput, RecommendationGenerateOutput


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass
class RecommendationOrchestrationResult:
    output: RecommendationGenerateOutput
    runtime_decision: dict[str, Any]


class RecommendationOrchestrator:
    """Three-layer online orchestration:
    1) rule diagnosis
    2) rule base tuning (rule_center)
    3) optional model-based candidate ranking
    """

    def __init__(self, recommendation_service: RecommendationService) -> None:
        self.recommendation_service = recommendation_service
        self._ranker: Optional[RecommendationRanker] = None
        self._default_candidate_limit = 6

    def _artifact_candidates(self, *paths: str) -> list[Path]:
        root = _repo_root()
        return [root / p for p in paths]

    def _first_existing(self, paths: list[Path]) -> Optional[Path]:
        for path in paths:
            if path.exists() and path.is_file():
                return path
        return None

    def _load_ranker(self) -> RecommendationRanker:
        if self._ranker is not None:
            return self._ranker
        try:
            import joblib  # type: ignore
        except Exception as exc:  # pragma: no cover - env dependent
            raise RuntimeError(f"joblib_import_failed: {exc}") from exc

        success_path = self._first_existing(
            self._artifact_candidates(
                "hmi/backend/artifacts/active/recommendation_success_tree.joblib",
                "hmi/backend/artifacts/active/recommendation_success_baseline.joblib",
                "hmi/backend/artifacts/recommendation_success/recommendation_success_tree.joblib",
                "hmi/backend/artifacts/recommendation_success/recommendation_success_baseline.joblib",
            )
        )
        gap_path = self._first_existing(
            self._artifact_candidates(
                "hmi/backend/artifacts/active/preview_gap_tree.joblib",
                "hmi/backend/artifacts/active/preview_gap_baseline.joblib",
                "hmi/backend/artifacts/preview_gap/preview_gap_tree.joblib",
                "hmi/backend/artifacts/preview_gap/preview_gap_baseline.joblib",
            )
        )
        if success_path is None or gap_path is None:
            raise RuntimeError("ranker_model_not_found")

        try:
            success_model = joblib.load(success_path)
            preview_gap_model = joblib.load(gap_path)
            self._ranker = RecommendationRanker(success_model=success_model, preview_gap_model=preview_gap_model)
            return self._ranker
        except Exception as exc:
            raise RuntimeError(f"ranker_model_load_failed: {exc}") from exc

    @staticmethod
    def _to_pid_dict(params: PIDParams) -> dict[str, float]:
        return {
            "kp": float(params.kp),
            "ki": float(params.ki),
            "kd": float(params.kd),
        }

    def generate_ranked_recommendation(
        self,
        *,
        payload: RecommendationGenerateInput,
        runtime_source: str,
        fallback_used: bool,
        fallback_reason: Optional[str] = None,
    ) -> RecommendationOrchestrationResult:
        # Layer 1 + 2: authoritative rule diagnosis and rule-base tuning.
        base_output = self.recommendation_service.generate(payload)
        final_output = base_output.model_copy(deep=True)

        runtime_decision: dict[str, Any] = {
            "runtime_source": runtime_source,
            "fallback_used": bool(fallback_used),
            "diagnosis_source": "rule_classifier",
            "base_recommendation_source": "rule_tuning_engine",
            "primary_problem_type": base_output.primary_problem_type.value,
            "secondary_problem_types": [item.value for item in base_output.secondary_problem_types],
            "problem_flags": {str(k): bool(v) for k, v in (base_output.problem_flags or {}).items()},
            "ranking_used": False,
            "ranking_fallback_used": False,
            "base_candidate_id": "rule_center",
            "base_recommended_params": self._to_pid_dict(base_output.recommended_params),
            "selected_candidate_id": "rule_center",
            "candidate_count": 1,
            "evaluated_candidate_count": 1,
            "configured_candidate_limit": int(self._default_candidate_limit),
        }
        if fallback_reason:
            runtime_decision["fallback_reason"] = str(fallback_reason)

        # Layer 3: optional ranking enhancement around rule_center.
        try:
            ranker = self._load_ranker()
            context = RecommendationRankingContext(
                recommendation_id=0,
                device_id=int(payload.device.id),
                device_code=str(payload.device.code),
                baseline_params=base_output.current_params,
                base_recommended_params=base_output.recommended_params,
                evidence=base_output.evidence,
                current_temp=float(payload.current_state.current_temp),
                target_temp=float(payload.current_state.target_temp),
                target_band=float(payload.target_band),
                pwm_saturation_threshold=float(payload.pwm_saturation_threshold),
                control_mode="pid_control",
                predicted_problem_type=base_output.primary_problem_type.value,
                secondary_problem_types=[item.value for item in base_output.secondary_problem_types],
                problem_flags={str(k): bool(v) for k, v in (base_output.problem_flags or {}).items()},
            )
            ranked = ranker.rank_candidates(context=context)
            if not ranked:
                raise RuntimeError("ranker_no_candidates")
            top = ranked[0]
            rec = top.get("recommended_params") if isinstance(top.get("recommended_params"), dict) else {}
            selected_params = PIDParams(
                kp=float(rec.get("kp")),
                ki=float(rec.get("ki")),
                kd=float(rec.get("kd")),
            )
            final_output.recommended_params = selected_params
            final_output.delta = PIDParams(
                kp=float(selected_params.kp) - float(final_output.current_params.kp),
                ki=float(selected_params.ki) - float(final_output.current_params.ki),
                kd=float(selected_params.kd) - float(final_output.current_params.kd),
            )
            runtime_decision.update(
                {
                    "ranking_used": True,
                    "ranking_fallback_used": False,
                    "selected_candidate_id": str(top.get("candidate_id") or "rule_center"),
                    "candidate_count": int(len(ranked)),
                    "evaluated_candidate_count": int(len(ranked)),
                    "configured_candidate_limit": int(getattr(ranker, "candidate_count", self._default_candidate_limit)),
                    "top_score": float(top.get("total_score", 0.0)),
                    "top_success_score": float((top.get("success_model") or {}).get("success_score", 0.0)),
                    "top_gap_score": float((top.get("preview_gap_model") or {}).get("gap_score", 0.0)),
                    "ranked_candidates": ranked,
                    "top_1_candidate_id": str(top.get("candidate_id") or "rule_center"),
                    "top_1_candidate": {
                        "candidate_id": str(top.get("candidate_id") or "rule_center"),
                        "total_score": float(top.get("total_score", 0.0)),
                        "success_score": float((top.get("success_model") or {}).get("success_score", 0.0)),
                        "preview_gap_score": float((top.get("preview_gap_model") or {}).get("gap_score", 0.0)),
                    },
                }
            )
        except Exception as exc:
            # Ranking is optional; keep rule_center as final on any ranking failure.
            runtime_decision.update(
                {
                    "ranking_used": False,
                    "ranking_fallback_used": True,
                    "ranking_fallback_reason": str(exc),
                    "selected_candidate_id": "rule_center",
                    "candidate_count": int(runtime_decision.get("candidate_count") or 1),
                    "evaluated_candidate_count": int(runtime_decision.get("candidate_count") or 1),
                }
            )

        final_output.ai_decision = runtime_decision
        return RecommendationOrchestrationResult(output=final_output, runtime_decision=runtime_decision)
