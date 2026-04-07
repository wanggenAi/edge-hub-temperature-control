from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from app.services.ai.preview_simulator import PreviewSimulationConfig, RecommendationPreviewSimulator
from app.services.ai.schemas import PIDParams


@dataclass
class RecommendationRankingContext:
    recommendation_id: int
    device_id: int
    device_code: str
    baseline_params: PIDParams
    base_recommended_params: PIDParams
    evidence: dict[str, Any]
    current_temp: float
    target_temp: float
    target_band: float = 0.5
    pwm_saturation_threshold: float = 85.0
    horizon_sec: int = 900
    step_sec: int = 30
    control_mode: str = "pid_control"


@dataclass
class CandidateRecommendation:
    candidate_id: str
    baseline_params: PIDParams
    recommended_params: PIDParams
    delta: PIDParams
    strategy_note: str


@dataclass
class CandidateScore:
    p_improved: float
    p_unchanged: float
    p_worse: float
    p_low: float
    p_medium: float
    p_high: float
    success_score: float
    gap_score: float
    total_score: float


class RecommendationRanker:
    FEATURE_COLUMNS = [
        "baseline_kp",
        "baseline_ki",
        "baseline_kd",
        "recommended_kp",
        "recommended_ki",
        "recommended_kd",
        "delta_kp",
        "delta_ki",
        "delta_kd",
        "mean_error",
        "mean_abs_error",
        "error_std",
        "temp_swing",
        "pwm_mean",
        "pwm_max",
        "zero_crossings",
        "in_band_ratio",
        "overshoot_pct",
        "settling_sec",
        "saturation_ratio",
        "preview_in_band_ratio",
        "preview_overshoot_c",
        "preview_settling_sec",
        "preview_mean_abs_error",
        "preview_saturation_ratio",
        "preview_temp_swing",
    ]

    def __init__(
        self,
        *,
        success_model: Any,
        preview_gap_model: Any,
        preview_simulator: Optional[RecommendationPreviewSimulator] = None,
    ) -> None:
        self.success_model = success_model
        self.preview_gap_model = preview_gap_model
        self.preview_simulator = preview_simulator or RecommendationPreviewSimulator()

    @staticmethod
    def _clamp_nonnegative(value: float) -> float:
        return max(0.0, float(value))

    @staticmethod
    def _build_delta(*, baseline: PIDParams, recommended: PIDParams) -> PIDParams:
        return PIDParams(
            kp=round(float(recommended.kp) - float(baseline.kp), 6),
            ki=round(float(recommended.ki) - float(baseline.ki), 6),
            kd=round(float(recommended.kd) - float(baseline.kd), 6),
        )

    def generate_candidates(self, *, context: RecommendationRankingContext) -> list[CandidateRecommendation]:
        baseline = context.baseline_params
        base_rec = context.base_recommended_params
        base_delta = self._build_delta(baseline=baseline, recommended=base_rec)

        def build_from_multiplier(
            *,
            candidate_id: str,
            m_kp: float,
            m_ki: float,
            m_kd: float,
            strategy_note: str,
        ) -> CandidateRecommendation:
            delta = PIDParams(
                kp=round(float(base_delta.kp) * m_kp, 6),
                ki=round(float(base_delta.ki) * m_ki, 6),
                kd=round(float(base_delta.kd) * m_kd, 6),
            )
            rec = PIDParams(
                kp=round(self._clamp_nonnegative(float(baseline.kp) + float(delta.kp)), 6),
                ki=round(self._clamp_nonnegative(float(baseline.ki) + float(delta.ki)), 6),
                kd=round(self._clamp_nonnegative(float(baseline.kd) + float(delta.kd)), 6),
            )
            return CandidateRecommendation(
                candidate_id=candidate_id,
                baseline_params=baseline,
                recommended_params=rec,
                delta=self._build_delta(baseline=baseline, recommended=rec),
                strategy_note=strategy_note,
            )

        def build_from_delta(
            *,
            candidate_id: str,
            delta_kp: float,
            delta_ki: float,
            delta_kd: float,
            strategy_note: str,
        ) -> CandidateRecommendation:
            rec = PIDParams(
                kp=round(self._clamp_nonnegative(float(baseline.kp) + float(delta_kp)), 6),
                ki=round(self._clamp_nonnegative(float(baseline.ki) + float(delta_ki)), 6),
                kd=round(self._clamp_nonnegative(float(baseline.kd) + float(delta_kd)), 6),
            )
            return CandidateRecommendation(
                candidate_id=candidate_id,
                baseline_params=baseline,
                recommended_params=rec,
                delta=self._build_delta(baseline=baseline, recommended=rec),
                strategy_note=strategy_note,
            )

        # Ensure overshoot-guard behavior is consistent with its name.
        # We always make Kp/Ki more conservative than rule_center, and force Kd
        # to be at least as damped as rule_center (never lower than baseline).
        overshoot_delta_kp = float(base_delta.kp) * 0.80
        overshoot_delta_ki = float(base_delta.ki) * 0.70
        if float(base_rec.kd) >= float(baseline.kd):
            overshoot_delta_kd = max(float(base_delta.kd), abs(float(base_delta.kd)) * 1.35)
        else:
            overshoot_delta_kd = abs(float(base_delta.kd)) * 0.35

        return [
            build_from_multiplier(
                candidate_id="rule_center",
                m_kp=1.0,
                m_ki=1.0,
                m_kd=1.0,
                strategy_note="Keep the current rule recommendation as the center candidate.",
            ),
            build_from_multiplier(
                candidate_id="conservative",
                m_kp=0.65,
                m_ki=0.65,
                m_kd=1.10,
                strategy_note="Smaller Kp/Ki adjustment with slightly stronger Kd damping.",
            ),
            build_from_multiplier(
                candidate_id="aggressive",
                m_kp=1.35,
                m_ki=1.25,
                m_kd=0.90,
                strategy_note="Larger Kp/Ki adjustment to chase stronger improvement.",
            ),
            build_from_delta(
                candidate_id="overshoot_guard",
                delta_kp=overshoot_delta_kp,
                delta_ki=overshoot_delta_ki,
                delta_kd=overshoot_delta_kd,
                strategy_note="Bias toward overshoot suppression (lower Kp/Ki, higher Kd damping).",
            ),
            build_from_multiplier(
                candidate_id="settling_focus",
                m_kp=1.20,
                m_ki=1.00,
                m_kd=0.95,
                strategy_note="Bias toward faster settling with moderate Kp boost.",
            ),
            build_from_multiplier(
                candidate_id="baseline_hold",
                m_kp=0.0,
                m_ki=0.0,
                m_kd=0.0,
                strategy_note="Hold baseline PID to quantify no-change reference.",
            ),
        ]

    def _simulate_preview_summary(
        self,
        *,
        context: RecommendationRankingContext,
        candidate: CandidateRecommendation,
    ) -> dict[str, Optional[float]]:
        preview = self.preview_simulator.run(
            current_temp=float(context.current_temp),
            target_temp=float(context.target_temp),
            baseline_params=context.baseline_params,
            recommended_params=candidate.recommended_params,
            config=PreviewSimulationConfig(
                horizon_sec=int(context.horizon_sec),
                step_sec=int(context.step_sec),
                target_band=float(context.target_band),
                pwm_saturation_threshold=float(context.pwm_saturation_threshold),
                control_mode=str(context.control_mode),
            ),
        )
        m = preview.recommended_metrics
        return {
            "preview_in_band_ratio": float(m.in_band_ratio),
            "preview_overshoot_c": float(m.overshoot_c),
            "preview_settling_sec": float(m.settling_sec) if m.settling_sec is not None else None,
            "preview_mean_abs_error": float(m.mean_abs_error),
            "preview_saturation_ratio": float(m.saturation_ratio),
            "preview_temp_swing": float(m.temp_swing),
        }

    def _build_features(
        self,
        *,
        context: RecommendationRankingContext,
        candidate: CandidateRecommendation,
        preview_summary: dict[str, Optional[float]],
    ) -> dict[str, Any]:
        evidence = context.evidence or {}
        return {
            "baseline_kp": float(candidate.baseline_params.kp),
            "baseline_ki": float(candidate.baseline_params.ki),
            "baseline_kd": float(candidate.baseline_params.kd),
            "recommended_kp": float(candidate.recommended_params.kp),
            "recommended_ki": float(candidate.recommended_params.ki),
            "recommended_kd": float(candidate.recommended_params.kd),
            "delta_kp": float(candidate.delta.kp),
            "delta_ki": float(candidate.delta.ki),
            "delta_kd": float(candidate.delta.kd),
            "mean_error": evidence.get("mean_error"),
            "mean_abs_error": evidence.get("mean_abs_error"),
            "error_std": evidence.get("error_std"),
            "temp_swing": evidence.get("temp_swing"),
            "pwm_mean": evidence.get("pwm_mean"),
            "pwm_max": evidence.get("pwm_max"),
            "zero_crossings": evidence.get("zero_crossings"),
            "in_band_ratio": evidence.get("in_band_ratio"),
            "overshoot_pct": evidence.get("overshoot_pct"),
            "settling_sec": evidence.get("settling_sec"),
            "saturation_ratio": evidence.get("saturation_ratio"),
            "preview_in_band_ratio": preview_summary.get("preview_in_band_ratio"),
            "preview_overshoot_c": preview_summary.get("preview_overshoot_c"),
            "preview_settling_sec": preview_summary.get("preview_settling_sec"),
            "preview_mean_abs_error": preview_summary.get("preview_mean_abs_error"),
            "preview_saturation_ratio": preview_summary.get("preview_saturation_ratio"),
            "preview_temp_swing": preview_summary.get("preview_temp_swing"),
        }

    @staticmethod
    def _predict_proba_map(model: Any, features_df: pd.DataFrame) -> dict[str, float]:
        probs = model.predict_proba(features_df)[0]
        clf = getattr(model, "named_steps", {}).get("clf", model)
        classes = [str(c) for c in getattr(clf, "classes_", [])]
        return {k: float(v) for k, v in zip(classes, probs)}

    @staticmethod
    def _compute_total_score(
        *,
        p_improved: float,
        p_unchanged: float,
        p_worse: float,
        p_low: float,
        p_medium: float,
        p_high: float,
        alpha: float = 0.65,
        beta: float = 0.35,
    ) -> CandidateScore:
        success_score = p_improved - 0.50 * p_unchanged - 1.00 * p_worse
        gap_score = p_low - 0.50 * p_medium - 1.00 * p_high
        total_score = alpha * success_score + beta * gap_score
        return CandidateScore(
            p_improved=float(p_improved),
            p_unchanged=float(p_unchanged),
            p_worse=float(p_worse),
            p_low=float(p_low),
            p_medium=float(p_medium),
            p_high=float(p_high),
            success_score=float(success_score),
            gap_score=float(gap_score),
            total_score=float(total_score),
        )

    def score_candidate(
        self,
        *,
        context: RecommendationRankingContext,
        candidate: CandidateRecommendation,
    ) -> dict[str, Any]:
        preview_summary = self._simulate_preview_summary(context=context, candidate=candidate)
        features = self._build_features(context=context, candidate=candidate, preview_summary=preview_summary)
        features_df = pd.DataFrame([{k: features.get(k) for k in self.FEATURE_COLUMNS}])

        success_proba = self._predict_proba_map(self.success_model, features_df)
        gap_proba = self._predict_proba_map(self.preview_gap_model, features_df)

        score = self._compute_total_score(
            p_improved=success_proba.get("improved", 0.0),
            p_unchanged=success_proba.get("unchanged", 0.0),
            p_worse=success_proba.get("worse", 0.0),
            p_low=gap_proba.get("low", 0.0),
            p_medium=gap_proba.get("medium", 0.0),
            p_high=gap_proba.get("high", 0.0),
        )

        return {
            "candidate_id": candidate.candidate_id,
            "strategy_note": candidate.strategy_note,
            "baseline_params": {
                "kp": float(candidate.baseline_params.kp),
                "ki": float(candidate.baseline_params.ki),
                "kd": float(candidate.baseline_params.kd),
            },
            "recommended_params": {
                "kp": float(candidate.recommended_params.kp),
                "ki": float(candidate.recommended_params.ki),
                "kd": float(candidate.recommended_params.kd),
            },
            "delta": {
                "kp": float(candidate.delta.kp),
                "ki": float(candidate.delta.ki),
                "kd": float(candidate.delta.kd),
            },
            "preview_summary": preview_summary,
            "success_model": {
                "p_improved": score.p_improved,
                "p_unchanged": score.p_unchanged,
                "p_worse": score.p_worse,
                "success_score": score.success_score,
            },
            "preview_gap_model": {
                "p_low": score.p_low,
                "p_medium": score.p_medium,
                "p_high": score.p_high,
                "gap_score": score.gap_score,
            },
            "total_score": score.total_score,
        }

    def rank_candidates(self, *, context: RecommendationRankingContext) -> list[dict[str, Any]]:
        scored = [self.score_candidate(context=context, candidate=c) for c in self.generate_candidates(context=context)]
        scored.sort(key=lambda item: float(item.get("total_score", 0.0)), reverse=True)
        for idx, item in enumerate(scored, start=1):
            item["rank"] = idx
        return scored
