#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "hmi" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.models.entities import ControlActionFeedbackSample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export control-action feedback samples to parquet")
    parser.add_argument(
        "--output",
        default="ml/data/datasets/control_action_feedback_samples.parquet",
        help="Output parquet path",
    )
    parser.add_argument("--include-ineligible", action="store_true", help="Include samples not eligible for training")
    parser.add_argument("--limit", type=int, default=None, help="Optional max rows")
    return parser.parse_args()


def row_to_dict(row: ControlActionFeedbackSample) -> dict:
    return {
        "id": row.id,
        "control_action_id": row.control_action_id,
        "device_id": row.device_id,
        "source": row.source,
        "source_ref_id": row.source_ref_id,
        "action_type": row.action_type,
        "initiated_by": row.initiated_by,
        "generated_at": row.generated_at,
        "applied_at": row.applied_at,
        "evaluated_at": row.evaluated_at,
        "primary_problem_type": row.primary_problem_type,
        "secondary_problem_types": row.secondary_problem_types,
        "problem_flags": row.problem_flags,
        "expected_effect": row.expected_effect,
        "risk_level": row.risk_level,
        "confidence": row.confidence,
        "control_mode_before": row.control_mode_before,
        "control_mode_after": row.control_mode_after,
        "target_temp_before": row.target_temp_before,
        "target_temp_after": row.target_temp_after,
        "kp_before": row.kp_before,
        "ki_before": row.ki_before,
        "kd_before": row.kd_before,
        "kp_after": row.kp_after,
        "ki_after": row.ki_after,
        "kd_after": row.kd_after,
        "delta_kp": row.delta_kp,
        "delta_ki": row.delta_ki,
        "delta_kd": row.delta_kd,
        "mean_error": row.mean_error,
        "mean_abs_error": row.mean_abs_error,
        "error_std": row.error_std,
        "temp_swing": row.temp_swing,
        "pwm_mean": row.pwm_mean,
        "pwm_max": row.pwm_max,
        "zero_crossings": row.zero_crossings,
        "in_band_ratio": row.in_band_ratio,
        "overshoot_pct": row.overshoot_pct,
        "settling_sec": row.settling_sec,
        "saturation_ratio": row.saturation_ratio,
        "runtime_decision_summary": row.runtime_decision_summary,
        "preview_metrics_summary": row.preview_metrics_summary,
        "actual_metrics_summary": row.actual_metrics_summary,
        "comparison_to_before": row.comparison_to_before,
        "comparison_to_preview": row.comparison_to_preview,
        "actual_effect_label": row.actual_effect_label,
        "preview_gap_label": row.preview_gap_label,
        "insufficient_data": bool(row.insufficient_data),
        "sample_quality": row.sample_quality,
        "is_training_eligible": bool(row.is_training_eligible),
        "training_exclusion_reason": row.training_exclusion_reason,
        "label_source": row.label_source,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def main() -> None:
    args = parse_args()
    db = SessionLocal()
    try:
        stmt = select(ControlActionFeedbackSample).order_by(ControlActionFeedbackSample.created_at.asc(), ControlActionFeedbackSample.id.asc())
        if not args.include_ineligible:
            stmt = stmt.where(
                ControlActionFeedbackSample.is_training_eligible.is_(True),
                ControlActionFeedbackSample.insufficient_data.is_(False),
            )
        if args.limit is not None:
            stmt = stmt.limit(max(1, int(args.limit)))
        rows = db.scalars(stmt).all()
    finally:
        db.close()

    data = [row_to_dict(row) for row in rows]
    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(data).to_parquet(out_path, index=False)
    print(f"[export] rows={len(data)}")
    print(f"[export] output={out_path}")


if __name__ == "__main__":
    main()

