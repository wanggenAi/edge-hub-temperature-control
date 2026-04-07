#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import joblib
import pandas as pd
from app.services.ai.recommendation_ranker import RecommendationRanker, RecommendationRankingContext
from app.services.ai.schemas import PIDParams


DEFAULT_DATA_PATH = Path("/tmp/recommendation_feedback.parquet")
DEFAULT_SUCCESS_MODEL = BACKEND_ROOT / "artifacts" / "recommendation_success" / "recommendation_success_tree.joblib"
DEFAULT_PREVIEW_GAP_MODEL = BACKEND_ROOT / "artifacts" / "preview_gap" / "preview_gap_baseline.joblib"
DEFAULT_OUTPUT_PATH = BACKEND_ROOT / "artifacts" / "candidate_ranking_result.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank candidate PID recommendations using success + preview-gap predictors")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="Recommendation feedback parquet path")
    parser.add_argument("--recommendation-id", type=int, default=None, help="Context row selection by recommendation_id")
    parser.add_argument("--device-id", type=int, default=None, help="Context row selection by device_id (latest usable)")
    parser.add_argument("--success-model", default=str(DEFAULT_SUCCESS_MODEL), help="Success predictor model path")
    parser.add_argument("--preview-gap-model", default=str(DEFAULT_PREVIEW_GAP_MODEL), help="Preview gap predictor model path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Ranking result JSON output path")
    parser.add_argument("--target-temp", type=float, default=37.0, help="Fallback target temp if missing from context")
    return parser.parse_args()


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _pick_context_row(df: pd.DataFrame, *, recommendation_id: int | None, device_id: int | None) -> pd.Series:
    usable = df[df["feedback_usable_for_training"].fillna(False).astype(bool)].copy()
    if usable.empty:
        raise SystemExit("No usable rows found in dataset.")

    if recommendation_id is not None:
        picked = usable[usable["recommendation_id"] == int(recommendation_id)]
        if picked.empty:
            raise SystemExit(f"recommendation_id={recommendation_id} not found in usable rows.")
        return picked.iloc[0]

    if device_id is not None:
        picked = usable[usable["device_id"] == int(device_id)].copy()
        if picked.empty:
            raise SystemExit(f"device_id={device_id} not found in usable rows.")
        if "generated_at" in picked.columns:
            picked = picked.sort_values("generated_at", ascending=False)
        return picked.iloc[0]

    if "generated_at" in usable.columns:
        usable = usable.sort_values("generated_at", ascending=False)
    return usable.iloc[0]


def _build_context_from_row(row: pd.Series, *, target_temp_fallback: float) -> RecommendationRankingContext:
    baseline = PIDParams(
        kp=_as_float(row.get("baseline_kp")),
        ki=_as_float(row.get("baseline_ki")),
        kd=_as_float(row.get("baseline_kd")),
    )
    recommended = PIDParams(
        kp=_as_float(row.get("recommended_kp")),
        ki=_as_float(row.get("recommended_ki")),
        kd=_as_float(row.get("recommended_kd")),
    )
    target_temp = float(target_temp_fallback)
    mean_error = row.get("mean_error")
    current_temp = target_temp + _as_float(mean_error) if mean_error is not None else target_temp

    evidence = {
        "mean_error": row.get("mean_error"),
        "mean_abs_error": row.get("mean_abs_error"),
        "error_std": row.get("error_std"),
        "temp_swing": row.get("temp_swing"),
        "pwm_mean": row.get("pwm_mean"),
        "pwm_max": row.get("pwm_max"),
        "zero_crossings": row.get("zero_crossings"),
        "in_band_ratio": row.get("in_band_ratio"),
        "overshoot_pct": row.get("overshoot_pct"),
        "settling_sec": row.get("settling_sec"),
        "saturation_ratio": row.get("saturation_ratio"),
    }

    return RecommendationRankingContext(
        recommendation_id=int(row["recommendation_id"]),
        device_id=int(row["device_id"]),
        device_code=str(row.get("device_code") or ""),
        baseline_params=baseline,
        base_recommended_params=recommended,
        evidence=evidence,
        current_temp=float(current_temp),
        target_temp=float(target_temp),
    )


def _build_reason_summary(*, top: dict[str, Any]) -> str:
    s = top.get("success_model", {})
    g = top.get("preview_gap_model", {})
    return (
        f"Selected rank-1 by highest total_score={top.get('total_score'):.4f}; "
        f"P(improved)={s.get('p_improved', 0.0):.3f}, "
        f"P(worse)={s.get('p_worse', 0.0):.3f}, "
        f"P(low_gap)={g.get('p_low', 0.0):.3f}, "
        f"P(high_gap)={g.get('p_high', 0.0):.3f}."
    )


def main() -> None:
    args = parse_args()

    data_path = Path(args.data)
    success_model_path = Path(args.success_model)
    preview_gap_model_path = Path(args.preview_gap_model)
    output_path = Path(args.output)

    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")
    if not success_model_path.exists():
        raise SystemExit(f"Success model not found: {success_model_path}")
    if not preview_gap_model_path.exists():
        raise SystemExit(f"Preview gap model not found: {preview_gap_model_path}")

    df = pd.read_parquet(data_path)
    row = _pick_context_row(df, recommendation_id=args.recommendation_id, device_id=args.device_id)
    context = _build_context_from_row(row, target_temp_fallback=float(args.target_temp))

    success_model = joblib.load(success_model_path)
    preview_gap_model = joblib.load(preview_gap_model_path)
    ranker = RecommendationRanker(success_model=success_model, preview_gap_model=preview_gap_model)
    ranked = ranker.rank_candidates(context=context)

    top1 = ranked[0]
    result = {
        "context": {
            "recommendation_id": context.recommendation_id,
            "device_id": context.device_id,
            "device_code": context.device_code,
            "baseline_params": {
                "kp": float(context.baseline_params.kp),
                "ki": float(context.baseline_params.ki),
                "kd": float(context.baseline_params.kd),
            },
            "base_recommended_params": {
                "kp": float(context.base_recommended_params.kp),
                "ki": float(context.base_recommended_params.ki),
                "kd": float(context.base_recommended_params.kd),
            },
        },
        "scoring_formula": {
            "success_score": "P(improved) - 0.5 * P(unchanged) - 1.0 * P(worse)",
            "gap_score": "P(low) - 0.5 * P(medium) - 1.0 * P(high)",
            "total_score": "0.65 * success_score + 0.35 * gap_score",
        },
        "candidate_count": len(ranked),
        "ranked_candidates": ranked,
        "top_1_candidate": top1,
        "top_1_reason_summary": _build_reason_summary(top=top1),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[candidate-ranker] done")
    print(f"[candidate-ranker] context recommendation_id={context.recommendation_id} device_id={context.device_id}")
    print(f"[candidate-ranker] candidates={len(ranked)}")
    print(f"[candidate-ranker] top1={top1.get('candidate_id')} total_score={float(top1.get('total_score', 0.0)):.4f}")
    print(f"[candidate-ranker] output={output_path}")


if __name__ == "__main__":
    main()

