#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "ml" / "data" / "datasets" / "recommendation_feedback.parquet"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.ai.recommendation_feedback_dataset import (
    RecommendationFeedbackDatasetBuilder,
    RecommendationFeedbackDatasetSummary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export recommendation feedback dataset for model training")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Parquet output path",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Optional CSV output path for manual inspection",
    )
    parser.add_argument(
        "--only-usable",
        action="store_true",
        help="Only export feedback samples marked as usable for training",
    )
    parser.add_argument("--device-id", type=int, default=None, help="Filter by device_id")
    parser.add_argument("--limit", type=int, default=None, help="Limit recommendation records before export")
    return parser.parse_args()


def _format_float(value: Optional[float], digits: int = 6) -> str:
    if value is None:
        return "None"
    return f"{value:.{digits}f}"


def print_summary(*, title: str, summary: RecommendationFeedbackDatasetSummary) -> None:
    print(title)
    print(f"  total recommendation records: {summary.total_recommendation_records}")
    print(f"  unique recommendation ids: {summary.unique_recommendation_ids}")
    print(f"  duplicate recommendation ids count: {summary.duplicate_recommendation_ids_count}")
    print(f"  applied recommendation records: {summary.applied_recommendation_records}")
    print(f"  evaluated recommendation records: {summary.evaluated_recommendation_records}")
    print(f"  insufficient_data count: {summary.insufficient_data_count}")
    print(f"  trainable samples count: {summary.trainable_samples_count}")
    print(
        "  effect outcome counts: "
        f"improved={summary.improved_count}, "
        f"unchanged={summary.unchanged_count}, "
        f"worse={summary.worse_count}, "
        f"pending={summary.pending_count}"
    )
    print(f"  average confidence: {_format_float(summary.average_confidence, digits=4)}")
    print(
        "  average delta: "
        f"kp={_format_float(summary.average_delta_kp, digits=6)}, "
        f"ki={_format_float(summary.average_delta_ki, digits=6)}, "
        f"kd={_format_float(summary.average_delta_kd, digits=6)}"
    )
    print(
        "  preview gap levels: "
        f"low={summary.preview_gap_low_count}, "
        f"medium={summary.preview_gap_medium_count}, "
        f"high={summary.preview_gap_high_count}"
    )


def main() -> None:
    args = parse_args()

    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "pandas is required for dataset export. Install dependencies first, for example:\n"
            "  pip install -r hmi/backend/requirements.txt"
        ) from exc

    output_path = Path(args.output)
    csv_path = Path(args.csv) if args.csv else None

    builder = RecommendationFeedbackDatasetBuilder()
    db = SessionLocal()
    try:
        all_rows = builder.build_feedback_dataset(
            db=db,
            device_id=args.device_id,
            limit=args.limit,
            only_usable=False,
        )
    finally:
        db.close()

    exported_rows = [row for row in all_rows if bool(row.get("feedback_usable_for_training"))] if args.only_usable else all_rows
    builder.validate_feedback_dataset(exported_rows)

    df = pd.DataFrame(exported_rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)

    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)

    summary_all = builder.summarize_feedback_dataset(all_rows)
    summary_exported = builder.summarize_feedback_dataset(exported_rows)

    print(f"[feedback-export] parquet={output_path}")
    print(f"[feedback-export] exported_rows={len(exported_rows)} only_usable={bool(args.only_usable)}")
    if csv_path is not None:
        print(f"[feedback-export] csv={csv_path}")

    print_summary(title="[summary] source records", summary=summary_all)
    print_summary(title="[summary] exported dataset", summary=summary_exported)


if __name__ == "__main__":
    main()
