#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import pstdev
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
    parser = argparse.ArgumentParser(description="Extract training features from cleaned training windows")
    parser.add_argument("--config", default="ml/configs/training_data.yaml", help="Path to pipeline YAML config")
    parser.add_argument("--input", default=None, help="Override windows parquet input path")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument("--output-file", default=None, help="Override output parquet filename")
    return parser.parse_args()


def safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:  # noqa: BLE001
        pass
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return None


def is_true_like(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return int(v) == 1
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "t", "yes", "y"}
    return False


def compute_zero_crossings(errors: List[float]) -> int:
    crossings = 0
    prev_sign = 0
    for val in errors:
        sign = 1 if val > 0 else (-1 if val < 0 else 0)
        if sign == 0:
            continue
        if prev_sign != 0 and sign != prev_sign:
            crossings += 1
        prev_sign = sign
    return crossings


def normalize_saturation_state(v: Any) -> str:
    text = "" if v is None else str(v).strip().lower()
    return text


def compute_settling_sec(
    ts_ms: List[int],
    errors: List[float],
    target_band: float,
) -> Optional[float]:
    if len(errors) < 2 or len(ts_ms) != len(errors):
        return None

    all_future_in_band = True
    settle_ts: Optional[int] = None
    for i in range(len(errors) - 1, -1, -1):
        in_band = abs(errors[i]) <= target_band
        all_future_in_band = all_future_in_band and in_band
        if all_future_in_band:
            settle_ts = ts_ms[i]

    if settle_ts is None:
        return None
    return max(0.0, (settle_ts - ts_ms[0]) / 1000.0)


def dominant_text(values: List[Any], default: str = "unknown") -> str:
    clean = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not clean:
        return default
    return pd.Series(clean).mode(dropna=True).iloc[0]


def parse_points(points_raw: Any) -> Optional[List[Dict[str, Any]]]:
    if points_raw is None:
        return None
    try:
        payload = json.loads(points_raw) if isinstance(points_raw, str) else points_raw
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, list):
        return None
    out: List[Dict[str, Any]] = []
    for row in payload:
        if isinstance(row, dict):
            out.append(row)
    return out


def extract_window_features(
    row: pd.Series,
    *,
    target_band: float,
    saturation_pwm_threshold: float,
) -> Optional[Dict[str, Any]]:
    points = parse_points(row.get("points"))
    if not points:
        return None

    temps: List[float] = []
    targets: List[float] = []
    errors: List[float] = []
    control_outputs: List[float] = []
    pwm_duties: List[float] = []
    pwm_norms: List[float] = []
    ts_ms: List[int] = []
    actual_dt_ms_vals: List[float] = []
    dt_error_ms_vals: List[float] = []
    saturation_states: List[str] = []
    fault_latched_flags: List[bool] = []
    pending_params_flags: List[bool] = []
    sensor_valid_flags: List[bool] = []
    system_states: List[Any] = []

    default_target = safe_float(row.get("target_temp_c"))

    for p in points:
        temp = safe_float(p.get("sensor_temp_c"))
        if temp is None:
            continue

        target = safe_float(p.get("target_temp_c"))
        if target is None:
            target = default_target
        if target is None:
            continue

        err = safe_float(p.get("error_c"))
        if err is None:
            err = target - temp

        temps.append(temp)
        targets.append(target)
        errors.append(err)

        c_out = safe_float(p.get("control_output"))
        if c_out is not None:
            control_outputs.append(c_out)
        pwm = safe_float(p.get("pwm_duty"))
        if pwm is not None:
            pwm_duties.append(pwm)
        pwm_n = safe_float(p.get("pwm_norm"))
        if pwm_n is not None:
            pwm_norms.append(pwm_n)

        ts = safe_float(p.get("ts_ms"))
        if ts is None:
            ts_v = p.get("ts")
            if ts_v is not None:
                try:
                    ts = pd.to_datetime(ts_v, utc=True, errors="coerce").value / 1_000_000.0
                except Exception:  # noqa: BLE001
                    ts = None
        if ts is not None:
            ts_ms.append(int(ts))

        dt = safe_float(p.get("actual_dt_ms"))
        if dt is not None:
            actual_dt_ms_vals.append(dt)
        dt_err = safe_float(p.get("dt_error_ms"))
        if dt_err is not None:
            dt_error_ms_vals.append(dt_err)

        saturation_states.append(normalize_saturation_state(p.get("saturation_state")))
        fault_latched_flags.append(is_true_like(p.get("fault_latched")))
        pending_params_flags.append(is_true_like(p.get("has_pending_params")))
        sensor_valid_flags.append(is_true_like(p.get("sensor_valid")))
        system_states.append(p.get("system_state"))

    if len(temps) < 2:
        return None

    # Fallback timestamps from window bounds if point-level ts is sparse.
    if len(ts_ms) != len(temps):
        ws = safe_float(row.get("window_start_ms"))
        we = safe_float(row.get("window_end_ms"))
        if ws is not None and we is not None and we >= ws and len(temps) > 1:
            span = (we - ws) / max(1, len(temps) - 1)
            ts_ms = [int(ws + i * span) for i in range(len(temps))]
        else:
            ts_ms = list(range(len(temps)))

    duration_ms = max(0, int(ts_ms[-1] - ts_ms[0]))
    duration_s = duration_ms / 1000.0

    temp_start = temps[0]
    temp_end = temps[-1]
    temp_min = min(temps)
    temp_max = max(temps)
    temp_mean = sum(temps) / len(temps)
    temp_std = pstdev(temps) if len(temps) > 1 else 0.0
    temp_swing = temp_max - temp_min

    mean_error = sum(errors) / len(errors)
    error_mean = mean_error
    abs_errors = [abs(e) for e in errors]
    mean_abs_error = sum(abs_errors) / len(abs_errors)
    error_std = pstdev(errors) if len(errors) > 1 else 0.0
    abs_error_max = max(abs_errors)

    control_output_mean = sum(control_outputs) / len(control_outputs) if control_outputs else 0.0
    control_output_std = pstdev(control_outputs) if len(control_outputs) > 1 else 0.0
    pwm_duty_mean = sum(pwm_duties) / len(pwm_duties) if pwm_duties else 0.0
    pwm_duty_max = max(pwm_duties) if pwm_duties else 0.0
    pwm_norm_mean = sum(pwm_norms) / len(pwm_norms) if pwm_norms else 0.0
    pwm_norm_max = max(pwm_norms) if pwm_norms else 0.0

    zero_crossings = compute_zero_crossings(errors)
    rise_slope = None if duration_s <= 0 else (temp_end - temp_start) / duration_s
    in_band_ratio = sum(1 for e in errors if abs(e) <= target_band) / len(errors)

    if saturation_states:
        saturated = sum(1 for s in saturation_states if s not in {"", "none", "normal", "knone"})
        saturation_ratio = saturated / len(saturation_states)
    else:
        saturation_ratio = (sum(1 for p in pwm_duties if p >= saturation_pwm_threshold) / len(pwm_duties)) if pwm_duties else 0.0

    overshoot_c = max(0.0, max(t - tgt for t, tgt in zip(temps, targets)))
    target_ref = safe_float(row.get("target_temp_c"))
    if target_ref is None:
        target_ref = sum(targets) / len(targets)
    overshoot_pct = 0.0 if not target_ref else (overshoot_c / max(abs(target_ref), 1e-6)) * 100.0
    settling_sec = compute_settling_sec(ts_ms, errors, target_band)

    point_count = len(temps)
    mean_actual_dt_ms = (sum(actual_dt_ms_vals) / len(actual_dt_ms_vals)) if actual_dt_ms_vals else None
    mean_dt_error_ms = (sum(dt_error_ms_vals) / len(dt_error_ms_vals)) if dt_error_ms_vals else None

    fault_latched_ratio = (sum(1 for x in fault_latched_flags if x) / len(fault_latched_flags)) if fault_latched_flags else 0.0
    pending_params_ratio = (sum(1 for x in pending_params_flags if x) / len(pending_params_flags)) if pending_params_flags else 0.0
    sensor_valid_ratio = (sum(1 for x in sensor_valid_flags if x) / len(sensor_valid_flags)) if sensor_valid_flags else 1.0
    dominant_system_state = dominant_text(system_states, default="unknown")

    return {
        "device_id": str(row.get("device_id", "")),
        "run_id": str(row.get("run_id", "")),
        "window_start_ms": int(safe_float(row.get("window_start_ms")) or ts_ms[0]),
        "window_end_ms": int(safe_float(row.get("window_end_ms")) or ts_ms[-1]),
        "target_temp_c": float(target_ref or 0.0),
        "control_mode": str(row.get("control_mode", "")),
        "kp": float(safe_float(row.get("kp")) or 0.0),
        "ki": float(safe_float(row.get("ki")) or 0.0),
        "kd": float(safe_float(row.get("kd")) or 0.0),
        "temp_start": temp_start,
        "temp_end": temp_end,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "temp_mean": temp_mean,
        "temp_std": temp_std,
        "temp_swing": temp_swing,
        "error_mean": error_mean,
        "mean_error": mean_error,
        "mean_abs_error": mean_abs_error,
        "error_std": error_std,
        "abs_error_max": abs_error_max,
        "control_output_mean": control_output_mean,
        "control_output_std": control_output_std,
        "pwm_duty_mean": pwm_duty_mean,
        "pwm_duty_max": pwm_duty_max,
        "pwm_norm_mean": pwm_norm_mean,
        "pwm_norm_max": pwm_norm_max,
        "zero_crossings": int(zero_crossings),
        "rise_slope": rise_slope,
        "in_band_ratio": in_band_ratio,
        "saturation_ratio": saturation_ratio,
        "overshoot_c": overshoot_c,
        "overshoot_pct": overshoot_pct,
        "settling_sec": settling_sec,
        "point_count": int(point_count),
        "duration_ms": int(duration_ms),
        "mean_actual_dt_ms": mean_actual_dt_ms,
        "mean_dt_error_ms": mean_dt_error_ms,
        "fault_latched_ratio": fault_latched_ratio,
        "pending_params_ratio": pending_params_ratio,
        "sensor_valid_ratio": sensor_valid_ratio,
        "dominant_system_state": dominant_system_state,
    }


def resolve_feature_cfg(cfg: Dict[str, Any], args: argparse.Namespace) -> Tuple[Path, Path, str, float, float]:
    fcfg = cfg.get("feature", {})
    input_path = Path(args.input or fcfg.get("input_parquet") or "ml/data/cleaned/training_windows.parquet")
    output_dir = Path(args.output_dir or fcfg.get("output_dir") or "ml/data/features")
    output_file = str(args.output_file or fcfg.get("output_file") or "training_features.parquet")
    target_band = float(fcfg.get("target_band", 0.5))
    saturation_pwm_threshold = float(fcfg.get("saturation_pwm_threshold", 85.0))
    return input_path, output_dir, output_file, target_band, saturation_pwm_threshold


def main() -> None:
    args = parse_args()
    cfg = load_yaml(Path(args.config))
    input_path, output_dir, output_file, target_band, saturation_pwm_threshold = resolve_feature_cfg(cfg, args)

    if not input_path.exists():
        raise FileNotFoundError(f"Input parquet not found: {input_path}")

    windows = pd.read_parquet(input_path)
    features: List[Dict[str, Any]] = []
    skipped = 0
    for _, row in windows.iterrows():
        rec = extract_window_features(
            row,
            target_band=target_band,
            saturation_pwm_threshold=saturation_pwm_threshold,
        )
        if rec is None:
            skipped += 1
            continue
        features.append(rec)

    out_df = pd.DataFrame(features)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / output_file
    out_df.to_parquet(out_path, index=False)

    print(f"[feature] input_windows={len(windows)}")
    print(f"[feature] output_rows={len(out_df)}")
    print(f"[feature] skipped_rows={skipped}")
    print(f"[feature] output={out_path}")


if __name__ == "__main__":
    main()
