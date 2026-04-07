#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[2]
REPO_ROOT = BACKEND_ROOT.parents[1]

DEFAULT_DATA_PATH = REPO_ROOT / "ml" / "data" / "datasets" / "recommendation_feedback.parquet"
DEFAULT_ARTIFACT_DIR = BACKEND_ROOT / "artifacts" / "recommendation_success"

LABEL_COLUMN = "effect_outcome"
USABLE_COLUMN = "feedback_usable_for_training"
ALLOWED_LABELS = ["improved", "unchanged", "worse"]

# First-pass stable feature set (recommendation-time available signals).
FEATURE_COLUMNS = [
    # A) baseline/recommended/delta PID params
    "baseline_kp",
    "baseline_ki",
    "baseline_kd",
    "recommended_kp",
    "recommended_ki",
    "recommended_kd",
    "delta_kp",
    "delta_ki",
    "delta_kd",
    # B) recommendation-time evidence
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
    # C) preview summary (available before apply)
    "preview_in_band_ratio",
    "preview_overshoot_c",
    "preview_settling_sec",
    "preview_mean_abs_error",
    "preview_saturation_ratio",
    "preview_temp_swing",
]


@dataclass
class DatasetStats:
    total_rows: int
    usable_rows: int
    rows_for_training: int
    label_distribution: dict[str, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train recommendation success predictor (improved/unchanged/worse)")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="Input recommendation feedback parquet")
    parser.add_argument("--artifacts-dir", default=str(DEFAULT_ARTIFACT_DIR), help="Output artifacts directory")
    parser.add_argument("--test-size", type=float, default=0.3, help="Validation split ratio")
    parser.add_argument("--seed", type=int, default=20260407, help="Random seed")
    return parser.parse_args()


def load_training_data(path: Path):
    import pandas as pd

    if not path.exists():
        raise SystemExit(f"Dataset not found: {path}")

    df = pd.read_parquet(path)
    total_rows = len(df)

    usable_mask = df[USABLE_COLUMN].fillna(False).astype(bool) if USABLE_COLUMN in df.columns else False
    usable_rows = int(usable_mask.sum()) if hasattr(usable_mask, "sum") else 0

    filtered = df[usable_mask].copy() if hasattr(usable_mask, "sum") else df.iloc[0:0].copy()
    filtered = filtered[filtered[LABEL_COLUMN].isin(ALLOWED_LABELS)].copy()

    label_distribution = {k: int(v) for k, v in filtered[LABEL_COLUMN].value_counts().to_dict().items()}
    stats = DatasetStats(
        total_rows=total_rows,
        usable_rows=usable_rows,
        rows_for_training=len(filtered),
        label_distribution=label_distribution,
    )
    return filtered, stats


def select_features(df):
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing feature columns in dataset: {missing}")
    return FEATURE_COLUMNS


def prepare_xy(df, feature_cols: list[str]):
    X = df[feature_cols].copy()
    y = df[LABEL_COLUMN].copy()
    return X, y


def split_train_valid(X, y, *, test_size: float, seed: int):
    from sklearn.model_selection import train_test_split

    label_counts = y.value_counts().to_dict()
    can_stratify = len(label_counts) >= 2 and all(int(v) >= 2 for v in label_counts.values())

    if can_stratify:
        return train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y), {
            "stratified": True,
            "fallback": False,
        }

    # Fallback for tiny/imbalanced datasets.
    if len(X) < 4:
        return (X, X, y, y), {
            "stratified": False,
            "fallback": True,
            "reason": "dataset too small; validation uses training data",
        }

    return train_test_split(X, y, test_size=test_size, random_state=seed, stratify=None), {
        "stratified": False,
        "fallback": True,
        "reason": "insufficient per-class samples for stratified split",
    }


def train_baseline_model(X_train, y_train, *, seed: int):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    random_state=seed,
                    n_jobs=None,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)
    return model


def train_tree_model(X_train, y_train, *, seed: int):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=400,
                    max_depth=None,
                    min_samples_leaf=1,
                    class_weight="balanced_subsample",
                    random_state=seed,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)
    return model


def evaluate_model(name: str, model, X_valid, y_valid) -> dict[str, Any]:
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    y_pred = model.predict(X_valid)
    labels = list(ALLOWED_LABELS)

    metrics = {
        "model_name": name,
        "accuracy": float(accuracy_score(y_valid, y_pred)),
        "macro_precision": float(precision_score(y_valid, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_valid, y_pred, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_valid, y_pred, average="macro", zero_division=0)),
        "confusion_matrix_labels": labels,
        "confusion_matrix": confusion_matrix(y_valid, y_pred, labels=labels).tolist(),
        "classification_report": classification_report(y_valid, y_pred, labels=labels, zero_division=0, output_dict=True),
        "validation_size": int(len(y_valid)),
    }
    return metrics


def build_feature_importance(name: str, model, feature_cols: list[str]):
    import pandas as pd

    rows: list[dict[str, Any]] = []
    clf = model.named_steps.get("clf")

    if hasattr(clf, "feature_importances_"):
        importances = list(clf.feature_importances_)
        for feat, val in zip(feature_cols, importances):
            rows.append({"model": name, "feature": feat, "importance": float(val)})
    elif hasattr(clf, "coef_") and hasattr(clf, "classes_"):
        coefs = clf.coef_
        classes = list(clf.classes_)
        abs_mean = coefs.copy()
        abs_mean = abs_mean if hasattr(abs_mean, "shape") else []
        for idx, feat in enumerate(feature_cols):
            class_weights = {}
            if len(classes) == len(coefs):
                for cls_idx, cls_name in enumerate(classes):
                    class_weights[str(cls_name)] = float(coefs[cls_idx][idx])
                importance = float(sum(abs(v) for v in class_weights.values()) / max(1, len(class_weights)))
            else:
                importance = float(abs(coefs[0][idx]))
                class_weights = {str(classes[0]): float(coefs[0][idx])}
            row = {"model": name, "feature": feat, "importance": importance}
            row.update({f"coef_{k}": v for k, v in class_weights.items()})
            rows.append(row)

    fi = pd.DataFrame(rows)
    if not fi.empty:
        fi = fi.sort_values(["model", "importance"], ascending=[True, False])
    return fi


def save_artifacts(
    *,
    artifacts_dir: Path,
    dataset_stats: DatasetStats,
    split_info: dict[str, Any],
    feature_cols: list[str],
    baseline_model,
    tree_model,
    baseline_metrics: dict[str, Any],
    tree_metrics: dict[str, Any],
    feature_importance,
) -> None:
    import joblib

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(baseline_model, artifacts_dir / "recommendation_success_baseline.joblib")
    joblib.dump(tree_model, artifacts_dir / "recommendation_success_tree.joblib")

    payload = {
        "dataset": {
            "total_rows": dataset_stats.total_rows,
            "usable_rows": dataset_stats.usable_rows,
            "rows_for_training": dataset_stats.rows_for_training,
            "label_distribution": dataset_stats.label_distribution,
        },
        "split": split_info,
        "models": {
            "baseline": baseline_metrics,
            "tree": tree_metrics,
        },
    }
    (artifacts_dir / "recommendation_success_metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (artifacts_dir / "recommendation_success_features.json").write_text(
        json.dumps(feature_cols, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if feature_importance is not None and not feature_importance.empty:
        feature_importance.to_csv(artifacts_dir / "recommendation_success_feature_importance.csv", index=False)

    lines = []
    lines.append("Recommendation Success Predictor - Training Report")
    lines.append("")
    lines.append("Dataset")
    lines.append(f"- total_rows: {dataset_stats.total_rows}")
    lines.append(f"- usable_rows: {dataset_stats.usable_rows}")
    lines.append(f"- rows_for_training: {dataset_stats.rows_for_training}")
    lines.append(f"- label_distribution: {dataset_stats.label_distribution}")
    lines.append("")
    lines.append("Split")
    lines.append(f"- split_info: {split_info}")
    lines.append("")
    for key, metrics in (("baseline", baseline_metrics), ("tree", tree_metrics)):
        lines.append(f"Model: {key}")
        lines.append(f"- accuracy: {metrics['accuracy']:.4f}")
        lines.append(f"- macro_precision: {metrics['macro_precision']:.4f}")
        lines.append(f"- macro_recall: {metrics['macro_recall']:.4f}")
        lines.append(f"- macro_f1: {metrics['macro_f1']:.4f}")
        lines.append(f"- confusion_matrix_labels: {metrics['confusion_matrix_labels']}")
        lines.append(f"- confusion_matrix: {metrics['confusion_matrix']}")
        lines.append("")

    (artifacts_dir / "recommendation_success_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()

    try:
        import pandas as pd  # noqa: F401
        import sklearn  # noqa: F401
        import joblib  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing ML dependencies. Install with:\n"
            "  pip install -r hmi/backend/requirements.txt"
        ) from exc

    data_path = Path(args.data)
    artifacts_dir = Path(args.artifacts_dir)

    df, dataset_stats = load_training_data(data_path)
    print("[train-success] dataset overview")
    print(f"  total rows: {dataset_stats.total_rows}")
    print(f"  usable rows: {dataset_stats.usable_rows}")
    print(f"  rows used for training: {dataset_stats.rows_for_training}")
    print(f"  label distribution: {dataset_stats.label_distribution}")

    if dataset_stats.rows_for_training == 0:
        raise SystemExit("No trainable rows after filtering (usable + label filter).")

    feature_cols = select_features(df)
    X, y = prepare_xy(df, feature_cols)
    (X_train, X_valid, y_train, y_valid), split_info = split_train_valid(
        X,
        y,
        test_size=float(args.test_size),
        seed=int(args.seed),
    )

    baseline_model = train_baseline_model(X_train, y_train, seed=int(args.seed))
    tree_model = train_tree_model(X_train, y_train, seed=int(args.seed))

    baseline_metrics = evaluate_model("logistic_regression", baseline_model, X_valid, y_valid)
    tree_metrics = evaluate_model("random_forest", tree_model, X_valid, y_valid)

    fi_baseline = build_feature_importance("logistic_regression", baseline_model, feature_cols)
    fi_tree = build_feature_importance("random_forest", tree_model, feature_cols)
    if fi_baseline is not None and fi_tree is not None:
        import pandas as pd

        feature_importance = pd.concat([fi_baseline, fi_tree], ignore_index=True)
    else:
        feature_importance = fi_baseline if fi_baseline is not None else fi_tree

    save_artifacts(
        artifacts_dir=artifacts_dir,
        dataset_stats=dataset_stats,
        split_info=split_info,
        feature_cols=feature_cols,
        baseline_model=baseline_model,
        tree_model=tree_model,
        baseline_metrics=baseline_metrics,
        tree_metrics=tree_metrics,
        feature_importance=feature_importance,
    )

    print("[train-success] metrics")
    for name, m in (("baseline/logistic_regression", baseline_metrics), ("tree/random_forest", tree_metrics)):
        print(f"  {name}")
        print(f"    accuracy={m['accuracy']:.4f}")
        print(f"    macro_precision={m['macro_precision']:.4f}")
        print(f"    macro_recall={m['macro_recall']:.4f}")
        print(f"    macro_f1={m['macro_f1']:.4f}")
        print(f"    confusion_matrix={m['confusion_matrix']}")

    print(f"[train-success] artifacts={artifacts_dir}")


if __name__ == "__main__":
    main()
