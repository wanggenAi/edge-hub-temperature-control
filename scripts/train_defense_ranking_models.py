#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "hmi" / "backend"
DEFAULT_DATASET_PATH = REPO_ROOT / "ml" / "data" / "datasets" / "defense_recommendation_feedback.parquet"
DEFAULT_CSV_PATH = REPO_ROOT / "ml" / "data" / "datasets" / "defense_recommendation_feedback.csv"
DEFAULT_SUCCESS_DIR = BACKEND_ROOT / "artifacts" / "recommendation_success"
DEFAULT_GAP_DIR = BACKEND_ROOT / "artifacts" / "preview_gap"
DEFAULT_ACTIVE_DIR = BACKEND_ROOT / "artifacts" / "active"
DEFAULT_MANIFEST_PATH = DEFAULT_ACTIVE_DIR / "defense_ranking_models_manifest.json"
DEFAULT_BACKEND_PYTHON = BACKEND_ROOT / ".venv" / "bin" / "python"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ai.recommendation_ranker import RecommendationRanker, RecommendationRankingContext  # noqa: E402
from app.services.ai.schemas import PIDParams  # noqa: E402


@dataclass(frozen=True)
class TrainingProfile:
    name: str
    problem_type: str
    target_temp: float
    current_temp: float
    baseline: tuple[float, float, float]
    rule_rec: tuple[float, float, float]
    evidence: dict[str, float | int | None]
    flags: dict[str, bool]


class _NoopModel:
    classes_ = ["improved", "unchanged", "worse"]

    def predict_proba(self, _features_df):  # type: ignore[no-untyped-def]
        return [[0.34, 0.33, 0.33]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a balanced local defense ranking dataset, train the native "
            "recommendation_success/preview_gap models, and activate the joblib artifacts."
        )
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH), help="Output training parquet path.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="Optional CSV audit output path. Use '' to skip.")
    parser.add_argument("--success-dir", default=str(DEFAULT_SUCCESS_DIR), help="Recommendation-success artifacts dir.")
    parser.add_argument("--gap-dir", default=str(DEFAULT_GAP_DIR), help="Preview-gap artifacts dir.")
    parser.add_argument("--active-dir", default=str(DEFAULT_ACTIVE_DIR), help="Runtime active artifacts dir.")
    parser.add_argument("--python", default=str(DEFAULT_BACKEND_PYTHON if DEFAULT_BACKEND_PYTHON.exists() else sys.executable))
    parser.add_argument("--seed", type=int, default=20260517, help="Deterministic seed recorded in the manifest.")
    parser.add_argument("--dataset-only", action="store_true", help="Only write dataset/CSV; do not train or activate models.")
    parser.add_argument("--skip-activate", action="store_true", help="Train models but do not copy artifacts to active/.")
    parser.add_argument("--report", action="store_true", help="Print current active defense ranking model status.")
    return parser.parse_args()


def _profile(
    *,
    name: str,
    problem_type: str,
    target: float,
    mean_error: float,
    baseline: tuple[float, float, float],
    rule_rec: tuple[float, float, float],
    mean_abs_error: float,
    error_std: float,
    temp_swing: float,
    pwm_mean: float,
    pwm_max: float,
    zero_crossings: int,
    in_band_ratio: float,
    overshoot_pct: float,
    settling_sec: float | None,
    saturation_ratio: float,
) -> TrainingProfile:
    flags = {
        "slow_response": problem_type == "slow_response",
        "steady_state_error": problem_type == "steady_state_error",
        "overshoot_high": problem_type == "overshoot_high",
        "oscillation": problem_type == "oscillation",
        "saturation_limited": problem_type == "saturation_limited",
        "severe_saturation": problem_type == "saturation_limited",
    }
    evidence: dict[str, float | int | None] = {
        "mean_error": mean_error,
        "mean_abs_error": mean_abs_error,
        "error_std": error_std,
        "temp_swing": temp_swing,
        "pwm_mean": pwm_mean,
        "pwm_max": pwm_max,
        "zero_crossings": zero_crossings,
        "in_band_ratio": in_band_ratio,
        "overshoot_pct": overshoot_pct,
        "settling_sec": settling_sec,
        "saturation_ratio": saturation_ratio,
    }
    return TrainingProfile(
        name=name,
        problem_type=problem_type,
        target_temp=target,
        current_temp=target - mean_error,
        baseline=baseline,
        rule_rec=rule_rec,
        evidence=evidence,
        flags=flags,
    )


def build_profiles() -> list[TrainingProfile]:
    profiles: list[TrainingProfile] = []
    for idx, severity in enumerate((0.85, 1.0, 1.18), start=1):
        profiles.append(
            _profile(
                name=f"steady_state_error_{idx}",
                problem_type="steady_state_error",
                target=28.0,
                mean_error=0.95 * severity,
                baseline=(2.0, 0.27, 0.05),
                rule_rec=(2.12, 0.36, 0.05),
                mean_abs_error=0.98 * severity,
                error_std=0.12,
                temp_swing=0.45,
                pwm_mean=63 + idx,
                pwm_max=74 + idx,
                zero_crossings=0,
                in_band_ratio=0.12,
                overshoot_pct=0.0,
                settling_sec=900.0,
                saturation_ratio=0.05,
            )
        )
        profiles.append(
            _profile(
                name=f"steady_state_error_integral_only_{idx}",
                problem_type="steady_state_error",
                target=28.0,
                mean_error=1.02 * severity,
                baseline=(2.1, 0.22, 0.05),
                rule_rec=(2.1, 0.253, 0.05),
                mean_abs_error=1.02 * severity,
                error_std=0.06,
                temp_swing=0.22,
                pwm_mean=58 + idx,
                pwm_max=62 + idx,
                zero_crossings=0,
                in_band_ratio=0.0,
                overshoot_pct=0.0,
                settling_sec=900.0,
                saturation_ratio=0.0,
            )
        )
        profiles.append(
            _profile(
                name=f"slow_response_{idx}",
                problem_type="slow_response",
                target=28.0,
                mean_error=0.65 * severity,
                baseline=(2.0, 0.26, 0.05),
                rule_rec=(2.24, 0.281, 0.047),
                mean_abs_error=0.78 * severity,
                error_std=0.85,
                temp_swing=3.2,
                pwm_mean=58 + idx,
                pwm_max=76 + idx,
                zero_crossings=0,
                in_band_ratio=0.48,
                overshoot_pct=0.0,
                settling_sec=600.0 + idx * 30,
                saturation_ratio=0.02,
            )
        )
        profiles.append(
            _profile(
                name=f"oscillation_{idx}",
                problem_type="oscillation",
                target=28.0,
                mean_error=0.02,
                baseline=(2.45, 0.34, 0.055),
                rule_rec=(2.18, 0.285, 0.075),
                mean_abs_error=0.78 * severity,
                error_std=0.92 * severity,
                temp_swing=2.9 * severity,
                pwm_mean=55,
                pwm_max=82 + idx,
                zero_crossings=7 + idx,
                in_band_ratio=0.35,
                overshoot_pct=3.5 * severity,
                settling_sec=780.0,
                saturation_ratio=0.14,
            )
        )
        profiles.append(
            _profile(
                name=f"overshoot_high_{idx}",
                problem_type="overshoot_high",
                target=28.0,
                mean_error=-0.25 * severity,
                baseline=(2.55, 0.33, 0.05),
                rule_rec=(2.22, 0.285, 0.072),
                mean_abs_error=0.86 * severity,
                error_std=0.62,
                temp_swing=2.2 * severity,
                pwm_mean=51,
                pwm_max=80,
                zero_crossings=2,
                in_band_ratio=0.42,
                overshoot_pct=6.0 * severity,
                settling_sec=720.0,
                saturation_ratio=0.07,
            )
        )
        profiles.append(
            _profile(
                name=f"saturation_limited_{idx}",
                problem_type="saturation_limited",
                target=35.0,
                mean_error=4.6 * severity,
                baseline=(2.4, 0.30, 0.055),
                rule_rec=(2.30, 0.285, 0.065),
                mean_abs_error=4.6 * severity,
                error_std=0.38,
                temp_swing=1.3,
                pwm_mean=96.0,
                pwm_max=100.0,
                zero_crossings=0,
                in_band_ratio=0.0,
                overshoot_pct=0.0,
                settling_sec=900.0,
                saturation_ratio=0.94,
            )
        )
        profiles.append(
            _profile(
                name=f"preview_mismatch_{idx}",
                problem_type="slow_response",
                target=37.0,
                mean_error=2.5 * severity,
                baseline=(2.25, 0.33, 0.06),
                rule_rec=(2.52, 0.356, 0.056),
                mean_abs_error=2.65 * severity,
                error_std=0.45,
                temp_swing=2.0,
                pwm_mean=83,
                pwm_max=100,
                zero_crossings=0,
                in_band_ratio=0.0,
                overshoot_pct=0.0,
                settling_sec=900.0,
                saturation_ratio=0.62,
            )
        )
    return profiles


def _label_for_candidate(profile: TrainingProfile, candidate_id: str) -> tuple[str, str]:
    problem = profile.problem_type
    saturation = float(profile.evidence.get("saturation_ratio") or 0.0)
    if problem in {"slow_response", "steady_state_error"} and saturation < 0.35:
        if candidate_id in {"aggressive", "sse_speed_balance", "settling_focus"}:
            return "improved", "low"
        if candidate_id == "rule_center":
            return "improved", "medium"
        if candidate_id == "conservative":
            return "unchanged", "medium"
        if candidate_id == "baseline_hold":
            return "unchanged", "high"
        return "unchanged", "medium"
    if problem in {"oscillation", "overshoot_high"}:
        if candidate_id in {"overshoot_guard", "conservative", "oscillation_overshoot_balance"}:
            return "improved", "low"
        if candidate_id == "rule_center":
            return "unchanged", "medium"
        if candidate_id in {"aggressive", "settling_focus"}:
            return "worse", "high"
        return "unchanged", "medium"
    if problem == "saturation_limited" or saturation >= 0.55:
        if candidate_id in {"saturation_safe_recovery", "conservative"}:
            return "unchanged", "medium"
        if candidate_id in {"aggressive", "settling_focus"}:
            return "worse", "high"
        if candidate_id == "rule_center":
            return "unchanged", "high"
        return "unchanged", "high"
    return "unchanged", "medium"


def build_dataset_rows() -> list[dict[str, Any]]:
    ranker = RecommendationRanker(success_model=_NoopModel(), preview_gap_model=_NoopModel(), candidate_count=6)
    rows: list[dict[str, Any]] = []
    for profile in build_profiles():
        context = RecommendationRankingContext(
            recommendation_id=0,
            device_id=0,
            device_code=f"TRAIN-{profile.name}",
            baseline_params=PIDParams(kp=profile.baseline[0], ki=profile.baseline[1], kd=profile.baseline[2]),
            base_recommended_params=PIDParams(kp=profile.rule_rec[0], ki=profile.rule_rec[1], kd=profile.rule_rec[2]),
            evidence=profile.evidence,
            current_temp=profile.current_temp,
            target_temp=profile.target_temp,
            target_band=0.5,
            pwm_saturation_threshold=85.0,
            control_mode="pid_control",
            predicted_problem_type=profile.problem_type,
            secondary_problem_types=[],
            problem_flags=profile.flags,
        )
        for candidate in ranker.generate_candidates(context=context):
            preview_summary = ranker._simulate_preview_summary(context=context, candidate=candidate)
            features = ranker._build_features(context=context, candidate=candidate, preview_summary=preview_summary)
            effect, gap = _label_for_candidate(profile, candidate.candidate_id)
            row = {key: features.get(key) for key in RecommendationRanker.FEATURE_COLUMNS}
            row.update(
                {
                    "recommendation_id": f"defense-training-{profile.name}-{candidate.candidate_id}",
                    "device_code": context.device_code,
                    "problem_type": profile.problem_type,
                    "candidate_id": candidate.candidate_id,
                    "effect_outcome": effect,
                    "preview_gap_level": gap,
                    "feedback_usable_for_training": True,
                }
            )
            rows.append(row)
    return rows


def write_dataset(rows: list[dict[str, Any]], *, dataset_path: Path, csv_path: Path | None) -> dict[str, Any]:
    import pandas as pd

    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(dataset_path, index=False)
    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
    return {
        "rows": int(len(df)),
        "effect_outcome": {str(k): int(v) for k, v in df["effect_outcome"].value_counts().to_dict().items()},
        "preview_gap_level": {str(k): int(v) for k, v in df["preview_gap_level"].value_counts().to_dict().items()},
        "candidate_id": {str(k): int(v) for k, v in df["candidate_id"].value_counts().to_dict().items()},
    }


def run_train(*, python: str, script: Path, dataset: Path, artifacts_dir: Path) -> str:
    cmd = [
        python,
        str(script),
        "--data",
        str(dataset),
        "--artifacts-dir",
        str(artifacts_dir),
        "--test-size",
        "0.25",
    ]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.stdout)
    return proc.stdout


def copy_active_artifacts(*, success_dir: Path, gap_dir: Path, active_dir: Path, manifest: dict[str, Any]) -> None:
    active_dir.mkdir(parents=True, exist_ok=True)
    for src in (
        success_dir / "recommendation_success_baseline.joblib",
        success_dir / "recommendation_success_tree.joblib",
        success_dir / "recommendation_success_metrics.json",
        success_dir / "recommendation_success_features.json",
        success_dir / "recommendation_success_report.txt",
        gap_dir / "preview_gap_baseline.joblib",
        gap_dir / "preview_gap_tree.joblib",
        gap_dir / "preview_gap_metrics.json",
        gap_dir / "preview_gap_features.json",
        gap_dir / "preview_gap_report.txt",
    ):
        if src.exists():
            shutil.copy2(src, active_dir / src.name)
    manifest_path = active_dir / DEFAULT_MANIFEST_PATH.name
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def load_artifact_report(active_dir: Path) -> dict[str, Any]:
    import joblib

    files = {
        "recommendation_success_tree": active_dir / "recommendation_success_tree.joblib",
        "preview_gap_tree": active_dir / "preview_gap_tree.joblib",
        "recommendation_success_metrics": active_dir / "recommendation_success_metrics.json",
        "preview_gap_metrics": active_dir / "preview_gap_metrics.json",
        "manifest": active_dir / DEFAULT_MANIFEST_PATH.name,
    }
    out: dict[str, Any] = {}
    for key, path in files.items():
        item: dict[str, Any] = {"path": str(path), "exists": path.exists(), "bytes": path.stat().st_size if path.exists() else 0}
        if path.suffix == ".joblib" and path.exists():
            model = joblib.load(path)
            clf = getattr(model, "named_steps", {}).get("clf", model)
            item["classes"] = [str(c) for c in getattr(clf, "classes_", [])]
            item["has_predict_proba"] = bool(hasattr(model, "predict_proba"))
        if path.suffix == ".json" and path.exists():
            try:
                item["json"] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                item["json_error"] = str(exc)
        out[key] = item
    return out


def print_report(active_dir: Path) -> None:
    report = load_artifact_report(active_dir)
    print("Defense ranking model artifact report")
    for key, item in report.items():
        print(f"- {key}: exists={item['exists']} bytes={item['bytes']}")
        if item.get("classes"):
            print(f"  classes={item['classes']} predict_proba={item.get('has_predict_proba')}")
        payload = item.get("json")
        if isinstance(payload, dict) and key.endswith("metrics"):
            dataset = payload.get("dataset") or {}
            print(f"  dataset={dataset}")
        if isinstance(payload, dict) and key == "manifest":
            print(f"  trained_at={payload.get('trained_at')} dataset_rows={payload.get('dataset_summary', {}).get('rows')}")


def main() -> int:
    args = parse_args()
    dataset_path = Path(args.dataset)
    csv_path = Path(args.csv) if str(args.csv or "").strip() else None
    success_dir = Path(args.success_dir)
    gap_dir = Path(args.gap_dir)
    active_dir = Path(args.active_dir)

    if args.report:
        print_report(active_dir)
        return 0

    rows = build_dataset_rows()
    dataset_summary = write_dataset(rows, dataset_path=dataset_path, csv_path=csv_path)
    print("[defense-ranking] dataset written")
    print(f"  parquet={dataset_path}")
    if csv_path is not None:
        print(f"  csv={csv_path}")
    print(f"  summary={json.dumps(dataset_summary, ensure_ascii=False)}")
    if args.dataset_only:
        return 0

    success_log = run_train(
        python=str(args.python),
        script=BACKEND_ROOT / "ai" / "scripts" / "train_recommendation_success_model.py",
        dataset=dataset_path,
        artifacts_dir=success_dir,
    )
    gap_log = run_train(
        python=str(args.python),
        script=BACKEND_ROOT / "ai" / "scripts" / "train_preview_gap_model.py",
        dataset=dataset_path,
        artifacts_dir=gap_dir,
    )
    print(success_log.rstrip())
    print(gap_log.rstrip())

    manifest = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": int(args.seed),
        "dataset_path": str(dataset_path),
        "csv_path": str(csv_path) if csv_path is not None else None,
        "dataset_summary": dataset_summary,
        "success_artifacts_dir": str(success_dir),
        "preview_gap_artifacts_dir": str(gap_dir),
        "active_artifacts_dir": str(active_dir),
        "note": "Local deterministic defense ranking artifacts trained with the native project training scripts.",
    }
    if not args.skip_activate:
        copy_active_artifacts(success_dir=success_dir, gap_dir=gap_dir, active_dir=active_dir, manifest=manifest)
        print(f"[defense-ranking] active artifacts updated: {active_dir}")
    print_report(active_dir if not args.skip_activate else success_dir.parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
