#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import yaml


LABEL_VERSION = "rules_v1"


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config must be a mapping")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rule-based pseudo labeling for training features")
    parser.add_argument("--config", default="ml/configs/training_data.yaml", help="Path to pipeline YAML config")
    parser.add_argument("--input", default=None, help="Override features parquet input path")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument("--output-file", default=None, help="Override output parquet filename")
    return parser.parse_args()


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
    except Exception:  # noqa: BLE001
        pass
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return default


def resolve_label_cfg(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[Path, Path, str, Dict[str, float]]:
    lcfg = cfg.get("labeling", {})
    input_path = Path(args.input or lcfg.get("input_parquet") or "ml/data/features/training_features.parquet")
    output_dir = Path(args.output_dir or lcfg.get("output_dir") or "ml/data/datasets")
    output_file = str(args.output_file or lcfg.get("output_file") or "labeled_samples.parquet")

    thr_raw = lcfg.get("thresholds", {}) if isinstance(lcfg.get("thresholds", {}), dict) else {}
    thr = {
        "target_band": float(thr_raw.get("target_band", 0.5)),
        "low_in_band_ratio": float(thr_raw.get("low_in_band_ratio", 0.4)),
        "normal_in_band_ratio": float(thr_raw.get("normal_in_band_ratio", 0.85)),
        "overshoot_pct_high": float(thr_raw.get("overshoot_pct_high", 3.0)),
        "oscillation_zero_crossings": float(thr_raw.get("oscillation_zero_crossings", 6)),
        "oscillation_error_std": float(thr_raw.get("oscillation_error_std", 0.4)),
        "saturation_ratio_high": float(thr_raw.get("saturation_ratio_high", 0.5)),
        "slow_response_rise_slope_max": float(thr_raw.get("slow_response_rise_slope_max", 0.002)),
        "steady_state_error_mean_abs_min": float(thr_raw.get("steady_state_error_mean_abs_min", 0.5)),
    }
    return input_path, output_dir, output_file, thr


def is_steady_like(sample: pd.Series, thresholds: Dict[str, float]) -> bool:
    slope = abs(safe_float(sample.get("rise_slope"), 0.0))
    temp_start = safe_float(sample.get("temp_start"), 0.0)
    temp_end = safe_float(sample.get("temp_end"), 0.0)
    target_band = thresholds["target_band"]
    return slope <= thresholds["slow_response_rise_slope_max"] or abs(temp_end - temp_start) <= target_band


def compute_problem_flags(sample: pd.Series, thresholds: Dict[str, float]) -> Dict[str, bool]:
    saturation_ratio = safe_float(sample.get("saturation_ratio"), 0.0)
    zero_crossings = safe_float(sample.get("zero_crossings"), 0.0)
    error_std = safe_float(sample.get("error_std"), 0.0)
    overshoot_pct = safe_float(sample.get("overshoot_pct"), 0.0)
    in_band_ratio = safe_float(sample.get("in_band_ratio"), 0.0)
    mean_abs_error = safe_float(sample.get("mean_abs_error"), 0.0)
    rise_slope = safe_float(sample.get("rise_slope"), 0.0)

    return {
        "saturation_limited": saturation_ratio >= thresholds["saturation_ratio_high"],
        "oscillation": (
            zero_crossings >= thresholds["oscillation_zero_crossings"]
            and error_std >= thresholds["oscillation_error_std"]
        ),
        "overshoot_high": overshoot_pct >= thresholds["overshoot_pct_high"],
        "steady_state_error": (
            in_band_ratio < thresholds["normal_in_band_ratio"]
            and mean_abs_error >= thresholds["steady_state_error_mean_abs_min"]
            and is_steady_like(sample, thresholds)
        ),
        "slow_response": (
            in_band_ratio < thresholds["low_in_band_ratio"]
            and rise_slope <= thresholds["slow_response_rise_slope_max"]
        ),
    }


def derive_problem_labels(problem_flags: Dict[str, bool]) -> Tuple[str, list[str]]:
    priority = [
        "saturation_limited",
        "oscillation",
        "overshoot_high",
        "steady_state_error",
        "slow_response",
    ]
    primary = "normal"
    for label in priority:
        if problem_flags.get(label):
            primary = label
            break
    secondary = [label for label in priority if problem_flags.get(label) and label != primary]
    return primary, secondary


def classify_problem_type(sample: pd.Series, thresholds: Dict[str, float]) -> str:
    primary, _secondary = derive_problem_labels(compute_problem_flags(sample, thresholds))
    return primary


def main() -> None:
    args = parse_args()
    cfg = load_yaml(Path(args.config))
    input_path, output_dir, output_file, thresholds = resolve_label_cfg(cfg, args)

    if not input_path.exists():
        raise FileNotFoundError(f"Input parquet not found: {input_path}")

    df = pd.read_parquet(input_path)
    if df.empty:
        out = df.copy()
        out["primary_problem_type"] = pd.Series(dtype="string")
        out["secondary_problem_types"] = pd.Series(dtype="object")
        out["problem_flags"] = pd.Series(dtype="object")
        out["problem_type"] = pd.Series(dtype="string")
        out["label_version"] = pd.Series(dtype="string")
        out["labeled_at"] = pd.Series(dtype="string")
    else:
        out = df.copy()
        out["problem_flags"] = out.apply(lambda r: compute_problem_flags(r, thresholds), axis=1)
        labels = out["problem_flags"].apply(derive_problem_labels)
        out["primary_problem_type"] = labels.apply(lambda item: item[0])
        out["secondary_problem_types"] = labels.apply(lambda item: item[1])
        # Backward compatibility for existing training/evaluation pipeline.
        out["problem_type"] = out["primary_problem_type"]
        out["label_version"] = LABEL_VERSION
        out["labeled_at"] = datetime.now(timezone.utc).isoformat()

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / output_file
    out.to_parquet(out_path, index=False)

    print(f"[label] input_rows={len(df)}")
    print(f"[label] output_rows={len(out)}")
    if not out.empty:
        counts = out["primary_problem_type"].value_counts(dropna=False).to_dict()
        print(f"[label] class_distribution={counts}")
    print(f"[label] output={out_path}")


if __name__ == "__main__":
    main()
