#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config must be a mapping")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build cleaned training windows from telemetry parquet")
    parser.add_argument("--config", default="ml/configs/training_data.yaml", help="Path to pipeline YAML config")
    parser.add_argument("--input", default=None, help="Override telemetry parquet input path")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument("--output-file", default=None, help="Override output parquet filename")
    parser.add_argument("--window-minutes", type=int, default=None, help="Override window size in minutes")
    parser.add_argument("--stride-minutes", type=int, default=None, help="Override stride in minutes")
    parser.add_argument("--min-points", type=int, default=None, help="Override minimum points per window")
    return parser.parse_args()


def ensure_required_columns(df: pd.DataFrame, required: List[str]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required telemetry columns: {missing}")


def normalize_ts_ms(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "ts_ms" in out.columns and pd.api.types.is_numeric_dtype(out["ts_ms"]):
        out["ts_ms"] = pd.to_numeric(out["ts_ms"], errors="coerce")
        return out

    if "ts" not in out.columns:
        raise ValueError("telemetry parquet must contain either 'ts_ms' or 'ts' column")

    if pd.api.types.is_numeric_dtype(out["ts"]):
        out["ts_ms"] = pd.to_numeric(out["ts"], errors="coerce")
    else:
        parsed = pd.to_datetime(out["ts"], errors="coerce", utc=True)
        out["ts_ms"] = (parsed.view("int64") // 1_000_000)
    return out


def is_true_like(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return int(v) == 1
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "t", "yes", "y"}
    return False


def clean_telemetry(df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_ts_ms(df)

    required_notna = [
        "device_id",
        "ts_ms",
        "target_temp_c",
        "sensor_temp_c",
        "run_id",
        "control_mode",
        "kp",
        "ki",
        "kd",
    ]
    ensure_required_columns(out, required_notna + ["sensor_valid", "fault_latched"])

    out = out[out["sensor_valid"].map(is_true_like)]
    out = out[~out["fault_latched"].map(is_true_like)]
    out = out.dropna(subset=required_notna)

    out["run_id"] = out["run_id"].astype(str).str.strip().replace("", "__unknown_run__")
    out["device_id"] = out["device_id"].astype(str).str.strip()
    out["control_mode"] = out["control_mode"].astype(str).str.strip()

    for c in ["ts_ms", "target_temp_c", "sensor_temp_c", "kp", "ki", "kd"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["ts_ms", "kp", "ki", "kd", "target_temp_c"]) 
    out = out.sort_values(["device_id", "run_id", "ts_ms"]).reset_index(drop=True)
    return out


def stable_params(window_df: pd.DataFrame, thresholds: Dict[str, float]) -> bool:
    if window_df.empty:
        return False

    mode_unique = window_df["control_mode"].dropna().astype(str).nunique()
    if mode_unique > 1:
        return False

    kp_delta = float(window_df["kp"].max() - window_df["kp"].min())
    ki_delta = float(window_df["ki"].max() - window_df["ki"].min())
    kd_delta = float(window_df["kd"].max() - window_df["kd"].min())

    return (
        kp_delta <= float(thresholds.get("kp_max_delta", 0.05))
        and ki_delta <= float(thresholds.get("ki_max_delta", 0.02))
        and kd_delta <= float(thresholds.get("kd_max_delta", 0.02))
    )


def summarize_window(window_df: pd.DataFrame, keep_cols: List[str]) -> Dict[str, Any]:
    row0 = window_df.iloc[0]
    target_temp = float(window_df["target_temp_c"].median())
    control_mode = str(window_df["control_mode"].mode(dropna=True).iloc[0])
    kp = float(window_df["kp"].median())
    ki = float(window_df["ki"].median())
    kd = float(window_df["kd"].median())

    safe_cols = [c for c in keep_cols if c in window_df.columns]
    points_records: List[Dict[str, Any]] = []
    for rec in window_df[safe_cols].to_dict(orient="records"):
        clean_rec: Dict[str, Any] = {}
        for k, v in rec.items():
            if pd.isna(v):
                clean_rec[k] = None
            elif hasattr(v, "item"):
                clean_rec[k] = v.item()
            else:
                clean_rec[k] = v
        points_records.append(clean_rec)

    return {
        "device_id": str(row0["device_id"]),
        "run_id": str(row0["run_id"]),
        "window_start_ms": int(window_df["ts_ms"].iloc[0]),
        "window_end_ms": int(window_df["ts_ms"].iloc[-1]),
        "target_temp_c": target_temp,
        "control_mode": control_mode,
        "kp": kp,
        "ki": ki,
        "kd": kd,
        "points": json.dumps(points_records, ensure_ascii=False),
    }


def build_windows(
    telemetry: pd.DataFrame,
    *,
    window_minutes: int,
    stride_minutes: int,
    min_points_per_window: int,
    thresholds: Dict[str, float],
    keep_cols: List[str],
) -> pd.DataFrame:
    window_ms = int(window_minutes) * 60 * 1000
    stride_ms = int(stride_minutes) * 60 * 1000

    samples: List[Dict[str, Any]] = []

    grouped = telemetry.groupby(["device_id", "run_id"], sort=False)
    for (device_id, run_id), g in grouped:
        g = g.sort_values("ts_ms")
        if g.empty:
            continue

        t_min = int(g["ts_ms"].min())
        t_max = int(g["ts_ms"].max())
        start = t_min

        while start + window_ms <= t_max:
            end = start + window_ms
            w = g[(g["ts_ms"] >= start) & (g["ts_ms"] < end)]
            if len(w) >= min_points_per_window and stable_params(w, thresholds):
                samples.append(summarize_window(w, keep_cols))
            start += stride_ms

    if not samples:
        return pd.DataFrame(
            columns=[
                "device_id",
                "run_id",
                "window_start_ms",
                "window_end_ms",
                "target_temp_c",
                "control_mode",
                "kp",
                "ki",
                "kd",
                "points",
            ]
        )

    out = pd.DataFrame(samples)
    out = out.sort_values(["device_id", "run_id", "window_start_ms"]).reset_index(drop=True)
    return out


def resolve_window_cfg(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[Path, Path, str, int, int, int, Dict[str, float], List[str]]:
    wcfg = cfg.get("windowing", {})
    input_path = Path(args.input or wcfg.get("input_parquet") or "ml/data/raw/telemetry.parquet")
    output_dir = Path(args.output_dir or wcfg.get("output_dir") or "ml/data/cleaned")
    output_file = str(args.output_file or wcfg.get("output_file") or "training_windows.parquet")

    window_minutes = int(args.window_minutes or wcfg.get("window_minutes") or 30)
    stride_minutes = int(args.stride_minutes or wcfg.get("stride_minutes") or 5)
    min_points_per_window = int(args.min_points or wcfg.get("min_points_per_window") or 30)

    thresholds_raw = wcfg.get("stability", {}) if isinstance(wcfg.get("stability", {}), dict) else {}
    thresholds: Dict[str, float] = {
        "kp_max_delta": float(thresholds_raw.get("kp_max_delta", 0.05)),
        "ki_max_delta": float(thresholds_raw.get("ki_max_delta", 0.02)),
        "kd_max_delta": float(thresholds_raw.get("kd_max_delta", 0.02)),
    }

    keep_cols_cfg = wcfg.get("points_keep_columns")
    if isinstance(keep_cols_cfg, list) and keep_cols_cfg:
        keep_cols = [str(x) for x in keep_cols_cfg]
    else:
        keep_cols = ["ts", "target_temp_c", "sensor_temp_c", "error_c", "pwm_duty", "control_mode", "kp", "ki", "kd"]

    return (
        input_path,
        output_dir,
        output_file,
        window_minutes,
        stride_minutes,
        min_points_per_window,
        thresholds,
        keep_cols,
    )


def main() -> None:
    args = parse_args()
    cfg = load_yaml(Path(args.config))

    (
        input_path,
        output_dir,
        output_file,
        window_minutes,
        stride_minutes,
        min_points_per_window,
        thresholds,
        keep_cols,
    ) = resolve_window_cfg(cfg, args)

    if not input_path.exists():
        raise FileNotFoundError(f"Telemetry parquet not found: {input_path}")

    telemetry_raw = pd.read_parquet(input_path)
    telemetry_clean = clean_telemetry(telemetry_raw)
    windows = build_windows(
        telemetry_clean,
        window_minutes=window_minutes,
        stride_minutes=stride_minutes,
        min_points_per_window=min_points_per_window,
        thresholds=thresholds,
        keep_cols=keep_cols,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / output_file
    windows.to_parquet(out_path, index=False)

    print(f"[window] input_points_raw={len(telemetry_raw)}")
    print(f"[window] input_points_clean={len(telemetry_clean)}")
    print(f"[window] output_samples={len(windows)}")
    print(f"[window] output={out_path}")


if __name__ == "__main__":
    main()
