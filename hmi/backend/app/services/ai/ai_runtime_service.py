from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.core.config import settings
from app.services.ai.feature_extractor import extract_features
from app.services.ai.preview_simulator import RecommendationPreviewSimulator
from app.services.ai.recommendation_ranker import RecommendationRanker, RecommendationRankingContext
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import PIDParams, RecommendationGenerateInput, RecommendationGenerateOutput

logger = logging.getLogger(__name__)

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[3]


class AIRuntimeService:
    PROBLEM_FEATURE_COLUMNS = [
        "mean_error",
        "mean_abs_error",
        "error_std",
        "temp_swing",
        "pwm_mean",
        "pwm_max",
        "zero_crossings",
        "in_band_ratio",
        "overshoot_pct",
        "overshoot_c",
        "settling_sec",
        "saturation_ratio",
        "rise_slope",
        "abs_error_max",
    ]

    def __init__(
        self,
        *,
        recommendation_service: Optional[RecommendationService] = None,
        preview_simulator: Optional[RecommendationPreviewSimulator] = None,
    ) -> None:
        self.recommendation_service = recommendation_service or RecommendationService()
        self.preview_simulator = preview_simulator or RecommendationPreviewSimulator()
        self._last_decision_by_device: dict[int, dict[str, Any]] = {}
        self._runtime_cfg = self._load_runtime_config()
        self._models: dict[str, Any] = {"problem_classifier": None, "success": None, "preview_gap": None}
        self._model_errors: dict[str, Optional[str]] = {"problem_classifier": None, "success": None, "preview_gap": None}
        self.reload_models()

    @staticmethod
    def _resolve_path(raw: str) -> Path:
        path = Path(raw)
        if path.is_absolute():
            return path
        return (BACKEND_ROOT / path).resolve()

    def _default_runtime_cfg(self) -> dict[str, Any]:
        return {
            "problem_classifier_enabled": bool(settings.problem_classifier_enabled),
            "success_predictor_enabled": bool(settings.success_predictor_enabled),
            "preview_gap_predictor_enabled": bool(settings.preview_gap_predictor_enabled),
            "candidate_ranker_enabled": bool(settings.candidate_ranker_enabled),
            "problem_classifier_model_path": str(self._resolve_path(settings.problem_classifier_model_path)),
            "success_model_path": str(self._resolve_path(settings.success_model_path)),
            "preview_gap_model_path": str(self._resolve_path(settings.preview_gap_model_path)),
            "success_model_variant": str(settings.success_model_variant or "tree"),
            "preview_gap_model_variant": str(settings.preview_gap_model_variant or "baseline"),
            "ranker_alpha": float(settings.ranker_alpha),
            "ranker_beta": float(settings.ranker_beta),
            "high_gap_penalty_threshold": float(settings.high_gap_penalty_threshold),
            "ranker_candidate_count": int(max(3, settings.ranker_candidate_count)),
            "use_problem_classifier_for_candidate_bias": bool(settings.use_problem_classifier_for_candidate_bias),
        }

    def _runtime_config_path(self) -> Path:
        return self._resolve_path(settings.ai_runtime_config_path)

    def _load_runtime_config(self) -> dict[str, Any]:
        cfg = self._default_runtime_cfg()
        path = self._runtime_config_path()
        if not path.exists():
            return cfg
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI runtime config parse failed: %s", exc)
            return cfg
        if isinstance(loaded, dict):
            cfg.update({k: v for k, v in loaded.items() if k in cfg})
        return cfg

    def _save_runtime_config(self) -> None:
        path = self._runtime_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._runtime_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_runtime_config(self) -> dict[str, Any]:
        return dict(self._runtime_cfg)

    def _default_variant_path(self, *, model_group: str, variant: str) -> str:
        v = (variant or "").strip().lower()
        if model_group == "success":
            name = "recommendation_success_tree.joblib" if v == "tree" else "recommendation_success_baseline.joblib"
            return str((BACKEND_ROOT / "artifacts" / "recommendation_success" / name).resolve())
        if model_group == "preview_gap":
            name = "preview_gap_tree.joblib" if v == "tree" else "preview_gap_baseline.joblib"
            return str((BACKEND_ROOT / "artifacts" / "preview_gap" / name).resolve())
        if model_group == "problem_classifier":
            name = "problem_classifier_tree.joblib" if v == "tree" else "problem_classifier_baseline.joblib"
            return str((BACKEND_ROOT / "artifacts" / "problem_classifier" / name).resolve())
        return ""

    def update_runtime_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        next_cfg = dict(self._runtime_cfg)
        for key in list(next_cfg.keys()):
            if key in updates:
                next_cfg[key] = updates[key]

        if "success_model_variant" in updates and "success_model_path" not in updates:
            next_cfg["success_model_path"] = self._default_variant_path(
                model_group="success",
                variant=str(next_cfg.get("success_model_variant") or "baseline"),
            )
        if "preview_gap_model_variant" in updates and "preview_gap_model_path" not in updates:
            next_cfg["preview_gap_model_path"] = self._default_variant_path(
                model_group="preview_gap",
                variant=str(next_cfg.get("preview_gap_model_variant") or "baseline"),
            )

        for key in (
            "problem_classifier_model_path",
            "success_model_path",
            "preview_gap_model_path",
        ):
            if key in next_cfg:
                next_cfg[key] = str(self._resolve_path(str(next_cfg[key])))

        next_cfg["ranker_alpha"] = float(next_cfg.get("ranker_alpha") or 0.65)
        next_cfg["ranker_beta"] = float(next_cfg.get("ranker_beta") or 0.35)
        next_cfg["ranker_candidate_count"] = int(max(3, int(next_cfg.get("ranker_candidate_count") or 6)))
        next_cfg["high_gap_penalty_threshold"] = float(next_cfg.get("high_gap_penalty_threshold") or 0.75)

        self._runtime_cfg = next_cfg
        self._save_runtime_config()
        self.reload_models()
        return self.get_runtime_config()

    def reload_models(self) -> None:
        try:
            import joblib
        except Exception as exc:  # noqa: BLE001
            msg = f"joblib unavailable: {exc}"
            self._model_errors = {"problem_classifier": msg, "success": msg, "preview_gap": msg}
            self._models = {"problem_classifier": None, "success": None, "preview_gap": None}
            return

        def _load(path_str: str, key: str) -> Any:
            path = Path(path_str)
            if not path.exists():
                self._model_errors[key] = f"missing model file: {path}"
                return None
            try:
                model = joblib.load(path)
                self._model_errors[key] = None
                return model
            except Exception as exc:  # noqa: BLE001
                self._model_errors[key] = f"load failed: {exc}"
                return None

        self._models["problem_classifier"] = _load(str(self._runtime_cfg["problem_classifier_model_path"]), "problem_classifier")
        self._models["success"] = _load(str(self._runtime_cfg["success_model_path"]), "success")
        self._models["preview_gap"] = _load(str(self._runtime_cfg["preview_gap_model_path"]), "preview_gap")

    def _predict_proba_map(self, model: Any, features_df: pd.DataFrame) -> dict[str, float]:
        probs = model.predict_proba(features_df)[0]
        clf = getattr(model, "named_steps", {}).get("clf", model)
        classes = [str(c) for c in getattr(clf, "classes_", [])]
        return {k: float(v) for k, v in zip(classes, probs)}

    def model_status(self) -> dict[str, Any]:
        cfg = self.get_runtime_config()
        return {
            "problem_classifier": {
                "enabled": bool(cfg["problem_classifier_enabled"]),
                "path": cfg["problem_classifier_model_path"],
                "loaded": self._models["problem_classifier"] is not None,
                "available": self._models["problem_classifier"] is not None,
                "error": self._model_errors.get("problem_classifier"),
            },
            "success_predictor": {
                "enabled": bool(cfg["success_predictor_enabled"]),
                "variant": cfg.get("success_model_variant"),
                "path": cfg["success_model_path"],
                "loaded": self._models["success"] is not None,
                "available": self._models["success"] is not None,
                "error": self._model_errors.get("success"),
            },
            "preview_gap_predictor": {
                "enabled": bool(cfg["preview_gap_predictor_enabled"]),
                "variant": cfg.get("preview_gap_model_variant"),
                "path": cfg["preview_gap_model_path"],
                "loaded": self._models["preview_gap"] is not None,
                "available": self._models["preview_gap"] is not None,
                "error": self._model_errors.get("preview_gap"),
            },
            "candidate_ranker": {
                "enabled": bool(cfg["candidate_ranker_enabled"]),
                "loaded": bool(self._models["success"] is not None and self._models["preview_gap"] is not None),
                "available": bool(self._models["success"] is not None and self._models["preview_gap"] is not None),
                "error": None
                if self._models["success"] is not None and self._models["preview_gap"] is not None
                else "ranker dependencies unavailable",
            },
        }

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_problem_classifier_features(self, payload: RecommendationGenerateInput) -> dict[str, Optional[float]]:
        features = extract_features(payload)
        points = payload.history_window.points or []
        overshoot_c = 0.0
        rise_slope: Optional[float] = None
        abs_error_max = 0.0
        if points:
            try:
                overshoot_c = max(max(0.0, float(p.current_temp) - float(p.target_temp)) for p in points)
            except Exception:  # noqa: BLE001
                overshoot_c = 0.0
            try:
                abs_error_max = max(abs(float(p.error)) for p in points)
            except Exception:  # noqa: BLE001
                abs_error_max = 0.0
            try:
                dt_s = max(1.0, (int(points[-1].ts_ms) - int(points[0].ts_ms)) / 1000.0)
                rise_slope = (float(points[-1].current_temp) - float(points[0].current_temp)) / dt_s
            except Exception:  # noqa: BLE001
                rise_slope = None

        return {
            "mean_error": float(features.mean_error),
            "mean_abs_error": float(features.mean_abs_error),
            "error_std": float(features.error_std),
            "temp_swing": float(features.temp_swing),
            "pwm_mean": float(features.pwm_mean),
            "pwm_max": float(features.pwm_max),
            "zero_crossings": float(features.zero_crossings),
            "in_band_ratio": float(features.in_band_ratio),
            "overshoot_pct": float(features.overshoot_pct),
            "overshoot_c": float(overshoot_c),
            "settling_sec": self._safe_float(features.settling_sec),
            "saturation_ratio": float(features.saturation_ratio),
            "rise_slope": self._safe_float(rise_slope),
            "abs_error_max": float(abs_error_max),
        }

    def classify_problem_runtime(self, payload: RecommendationGenerateInput) -> dict[str, Any]:
        cfg = self.get_runtime_config()
        if not bool(cfg.get("problem_classifier_enabled")):
            return {"enabled": False, "available": False, "predicted_problem_type": None, "probabilities": {}, "fallback_reason": "disabled"}
        model = self._models.get("problem_classifier")
        if model is None:
            return {"enabled": True, "available": False, "predicted_problem_type": None, "probabilities": {}, "fallback_reason": self._model_errors.get("problem_classifier")}
        feat = self._build_problem_classifier_features(payload)
        frame = pd.DataFrame([{k: feat.get(k) for k in self.PROBLEM_FEATURE_COLUMNS}])
        try:
            probs = self._predict_proba_map(model, frame)
            predicted = max(probs.items(), key=lambda item: item[1])[0] if probs else None
            return {
                "enabled": True,
                "available": True,
                "predicted_problem_type": predicted,
                "probabilities": probs,
                "features": feat,
            }
        except Exception as exc:  # noqa: BLE001
            return {"enabled": True, "available": False, "predicted_problem_type": None, "probabilities": {}, "fallback_reason": str(exc)}

    def build_runtime_context(
        self,
        *,
        payload: RecommendationGenerateInput,
        base_output: RecommendationGenerateOutput,
        recommendation_id: int = 0,
        predicted_problem_type: Optional[str] = None,
    ) -> RecommendationRankingContext:
        return RecommendationRankingContext(
            recommendation_id=int(max(0, recommendation_id)),
            device_id=int(payload.device.id),
            device_code=str(payload.device.code),
            baseline_params=base_output.current_params,
            base_recommended_params=base_output.recommended_params,
            evidence=dict(base_output.evidence or {}),
            current_temp=float(payload.current_state.current_temp),
            target_temp=float(payload.current_state.target_temp),
            target_band=float(payload.target_band),
            pwm_saturation_threshold=float(payload.pwm_saturation_threshold),
            horizon_sec=900,
            step_sec=30,
            control_mode="pid_control",
            predicted_problem_type=predicted_problem_type,
        )

    def _build_ranker(self) -> RecommendationRanker:
        cfg = self.get_runtime_config()
        return RecommendationRanker(
            success_model=self._models["success"],
            preview_gap_model=self._models["preview_gap"],
            preview_simulator=self.preview_simulator,
            alpha=float(cfg.get("ranker_alpha") or 0.65),
            beta=float(cfg.get("ranker_beta") or 0.35),
            candidate_count=int(cfg.get("ranker_candidate_count") or 6),
        )

    def build_recommendation_decision(
        self,
        *,
        payload: RecommendationGenerateInput,
        base_output: RecommendationGenerateOutput,
        recommendation_id: int = 0,
    ) -> dict[str, Any]:
        cfg = self.get_runtime_config()
        status = self.model_status()
        classifier_result = self.classify_problem_runtime(payload)
        predicted_problem_type = classifier_result.get("predicted_problem_type")
        if not bool(cfg.get("use_problem_classifier_for_candidate_bias")):
            predicted_problem_type = None

        fallback_used = False
        fallback_reason: Optional[str] = None
        ranked_candidates: list[dict[str, Any]] = []
        top_candidate: Optional[dict[str, Any]] = None

        ranker_enabled = bool(cfg.get("candidate_ranker_enabled"))
        success_enabled = bool(cfg.get("success_predictor_enabled"))
        gap_enabled = bool(cfg.get("preview_gap_predictor_enabled"))
        success_ready = success_enabled and self._models.get("success") is not None
        gap_ready = gap_enabled and self._models.get("preview_gap") is not None

        if ranker_enabled and success_ready and gap_ready:
            try:
                context = self.build_runtime_context(
                    payload=payload,
                    base_output=base_output,
                    recommendation_id=recommendation_id,
                    predicted_problem_type=predicted_problem_type,
                )
                ranker = self._build_ranker()
                ranked_candidates = ranker.rank_candidates(context=context)
                top_candidate = ranked_candidates[0] if ranked_candidates else None
            except Exception as exc:  # noqa: BLE001
                fallback_used = True
                fallback_reason = f"candidate ranking failed: {exc}"
        else:
            fallback_used = True
            missing = []
            if not ranker_enabled:
                missing.append("candidate_ranker_disabled")
            if not success_ready:
                missing.append("success_model_unavailable")
            if not gap_ready:
                missing.append("preview_gap_model_unavailable")
            fallback_reason = ", ".join(missing) if missing else "runtime_models_unavailable"

        decision: dict[str, Any] = {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "enabled_models": {
                "problem_classifier": bool(cfg.get("problem_classifier_enabled")),
                "success_predictor": bool(cfg.get("success_predictor_enabled")),
                "preview_gap_predictor": bool(cfg.get("preview_gap_predictor_enabled")),
                "candidate_ranker": bool(cfg.get("candidate_ranker_enabled")),
            },
            "model_status": status,
            "predicted_problem_type": classifier_result.get("predicted_problem_type"),
            "problem_classifier_probabilities": classifier_result.get("probabilities", {}),
            "candidate_count": len(ranked_candidates),
            "top_1_candidate_id": top_candidate.get("candidate_id") if isinstance(top_candidate, dict) else None,
            "top_1_candidate": top_candidate,
            "ranked_candidates": ranked_candidates[: min(3, len(ranked_candidates))],
            "scoring_formula": {
                "success_score": "P(improved) - 0.5 * P(unchanged) - 1.0 * P(worse)",
                "gap_score": "P(low) - 0.5 * P(medium) - 1.0 * P(high)",
                "total_score": f"{float(cfg.get('ranker_alpha') or 0.65):.2f} * success_score + {float(cfg.get('ranker_beta') or 0.35):.2f} * gap_score",
            },
            "fallback_used": bool(fallback_used),
            "fallback_reason": fallback_reason,
        }
        return decision

    def apply_decision_to_recommendation(
        self,
        *,
        output: RecommendationGenerateOutput,
        decision: dict[str, Any],
    ) -> RecommendationGenerateOutput:
        output.ai_decision = decision
        top = decision.get("top_1_candidate")
        if not isinstance(top, dict):
            return output
        rec = top.get("recommended_params") if isinstance(top.get("recommended_params"), dict) else {}
        delta = top.get("delta") if isinstance(top.get("delta"), dict) else {}
        try:
            output.recommended_params = PIDParams(
                kp=float(rec.get("kp", output.recommended_params.kp)),
                ki=float(rec.get("ki", output.recommended_params.ki)),
                kd=float(rec.get("kd", output.recommended_params.kd)),
            )
            output.delta = PIDParams(
                kp=float(delta.get("kp", output.delta.kp)),
                ki=float(delta.get("ki", output.delta.ki)),
                kd=float(delta.get("kd", output.delta.kd)),
            )
        except Exception:  # noqa: BLE001
            return output
        return output

    def remember_decision(self, *, device_id: int, decision: dict[str, Any]) -> None:
        self._last_decision_by_device[int(device_id)] = dict(decision)

    def get_last_decision(self, *, device_id: int) -> Optional[dict[str, Any]]:
        return self._last_decision_by_device.get(int(device_id))


_runtime_singleton: Optional[AIRuntimeService] = None


def get_ai_runtime_service() -> AIRuntimeService:
    global _runtime_singleton
    if _runtime_singleton is None:
        _runtime_singleton = AIRuntimeService()
    return _runtime_singleton

