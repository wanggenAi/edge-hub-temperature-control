#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[2]
REPO_ROOT = BACKEND_ROOT.parents[1]

DEFAULT_DATA_PATH = REPO_ROOT / "ml" / "data" / "datasets" / "labeled_samples.parquet"
DEFAULT_ARTIFACT_DIR = BACKEND_ROOT / "artifacts" / "problem_classifier"

LABEL_COLUMN = "problem_type"
TARGET_LABELS = [
    "normal",
    "slow_response",
    "overshoot_high",
    "steady_state_error",
    "oscillation",
    "saturation_limited",
]

# Window-level control features (explicit first-pass set).
FEATURE_CANDIDATES: list[tuple[str, list[str]]] = [
    ("mean_error", ["mean_error", "error_mean"]),
    ("mean_abs_error", ["mean_abs_error"]),
    ("error_std", ["error_std"]),
    ("temp_swing", ["temp_swing"]),
    ("pwm_mean", ["pwm_duty_mean", "pwm_mean"]),
    ("pwm_max", ["pwm_duty_max", "pwm_max"]),
    ("zero_crossings", ["zero_crossings"]),
    ("in_band_ratio", ["in_band_ratio"]),
    ("overshoot_pct", ["overshoot_pct"]),
    ("overshoot_c", ["overshoot_c"]),
    ("settling_sec", ["settling_sec"]),
    ("saturation_ratio", ["saturation_ratio"]),
    ("rise_slope", ["rise_slope"]),
    ("abs_error_max", ["abs_error_max"]),
]


@dataclass
class DatasetStats:
    total_rows: int
    rows_for_training: int
    label_distribution: dict[str, int]
    selected_labels: list[str]
    feature_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train control problem classifier (window-level multiclass)")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="Input labeled windows parquet")
    parser.add_argument("--artifacts-dir", default=str(DEFAULT_ARTIFACT_DIR), help="Output artifacts directory")
    parser.add_argument("--test-size", type=float, default=0.3, help="Validation split ratio")
    parser.add_argument("--seed", type=int, default=20260407, help="Random seed")
    return parser.parse_args()


def _normalize_label(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def load_training_data(path: Path):
    import pandas as pd

    if not path.exists():
        raise SystemExit(f"Dataset not found: {path}")

    df = pd.read_parquet(path)
    total_rows = len(df)

    if LABEL_COLUMN not in df.columns:
        raise SystemExit(f"Missing label column '{LABEL_COLUMN}' in dataset.")

    work = df.copy()
    work[LABEL_COLUMN] = work[LABEL_COLUMN].map(_normalize_label)
    work = work[work[LABEL_COLUMN] != ""].copy()

    usable_target_labels = [lbl for lbl in TARGET_LABELS if lbl in set(work[LABEL_COLUMN].unique())]
    if len(usable_target_labels) >= 2:
        work = work[work[LABEL_COLUMN].isin(usable_target_labels)].copy()
        selected_labels = usable_target_labels
    else:
        # Fallback: keep real labels from dataset if target labels are sparse/missing.
        selected_labels = sorted(work[LABEL_COLUMN].dropna().astype(str).unique().tolist())

    label_distribution = {k: int(v) for k, v in work[LABEL_COLUMN].value_counts().to_dict().items()}
    return work, total_rows, label_distribution, selected_labels


def select_features(df):
    selected_actual_cols: list[str] = []
    selected_feature_names: list[str] = []

    for canonical, alternatives in FEATURE_CANDIDATES:
        hit = next((c for c in alternatives if c in df.columns), None)
        if hit is not None:
            selected_feature_names.append(canonical)
            selected_actual_cols.append(hit)

    if not selected_actual_cols:
        raise SystemExit("No configured feature columns found in dataset.")

    return selected_feature_names, selected_actual_cols


def apply_row_quality_filter(df, actual_feature_cols: list[str], *, min_non_null_ratio: float = 0.4):
    import pandas as pd

    numeric = df[actual_feature_cols].apply(pd.to_numeric, errors="coerce")
    non_null_ratio = numeric.notna().mean(axis=1)
    kept = df[non_null_ratio >= float(min_non_null_ratio)].copy()
    return kept


def prepare_xy(df, feature_names: list[str], actual_feature_cols: list[str]):
    import pandas as pd

    X = df[actual_feature_cols].copy()
    X = X.apply(pd.to_numeric, errors="coerce")
    X.columns = feature_names
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


def evaluate_model(name: str, model, X_valid, y_valid, labels: list[str]) -> dict[str, Any]:
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    y_pred = model.predict(X_valid)
    return {
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


def build_feature_importance(name: str, model, feature_cols: list[str]):
    import pandas as pd

    rows: list[dict[str, Any]] = []
    clf = model.named_steps.get("clf")

    if hasattr(clf, "feature_importances_"):
        for feat, val in zip(feature_cols, list(clf.feature_importances_)):
            rows.append({"model": name, "feature": feat, "importance": float(val)})
    elif hasattr(clf, "coef_") and hasattr(clf, "classes_"):
        coefs = clf.coef_
        classes = list(clf.classes_)
        for idx, feat in enumerate(feature_cols):
            class_weights: dict[str, float] = {}
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

    joblib.dump(baseline_model, artifacts_dir / "problem_classifier_baseline.joblib")
    joblib.dump(tree_model, artifacts_dir / "problem_classifier_tree.joblib")

    payload = {
        "dataset": {
            "total_rows": dataset_stats.total_rows,
            "rows_for_training": dataset_stats.rows_for_training,
            "label_distribution": dataset_stats.label_distribution,
            "selected_labels": dataset_stats.selected_labels,
            "feature_count": dataset_stats.feature_count,
        },
        "split": split_info,
        "models": {
            "baseline": baseline_metrics,
            "tree": tree_metrics,
        },
    }
    (artifacts_dir / "problem_classifier_metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (artifacts_dir / "problem_classifier_features.json").write_text(
        json.dumps(feature_cols, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if feature_importance is not None and not feature_importance.empty:
        feature_importance.to_csv(artifacts_dir / "problem_classifier_feature_importance.csv", index=False)

    lines = [
        "Control Problem Classifier - Training Report",
        "",
        "Dataset",
        f"- total_rows: {dataset_stats.total_rows}",
        f"- rows_for_training: {dataset_stats.rows_for_training}",
        f"- label_distribution: {dataset_stats.label_distribution}",
        f"- selected_labels: {dataset_stats.selected_labels}",
        f"- feature_count: {dataset_stats.feature_count}",
        "",
        "Split",
        f"- split_info: {split_info}",
        "",
    ]
    for key, metrics in (("baseline", baseline_metrics), ("tree", tree_metrics)):
        lines.extend(
            [
                f"Model: {key}",
                f"- accuracy: {metrics['accuracy']:.4f}",
                f"- macro_precision: {metrics['macro_precision']:.4f}",
                f"- macro_recall: {metrics['macro_recall']:.4f}",
                f"- macro_f1: {metrics['macro_f1']:.4f}",
                f"- confusion_matrix_labels: {metrics['confusion_matrix_labels']}",
                f"- confusion_matrix: {metrics['confusion_matrix']}",
                "",
            ]
        )
    (artifacts_dir / "problem_classifier_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()

    data_path = Path(args.data)
    artifacts_dir = Path(args.artifacts_dir)

    df, total_rows, label_distribution, selected_labels = load_training_data(data_path)
    feature_names, actual_feature_cols = select_features(df)
    df = apply_row_quality_filter(df, actual_feature_cols, min_non_null_ratio=0.4)

    label_distribution = {k: int(v) for k, v in df[LABEL_COLUMN].value_counts().to_dict().items()}
    dataset_stats = DatasetStats(
        total_rows=int(total_rows),
        rows_for_training=int(len(df)),
        label_distribution=label_distribution,
        selected_labels=selected_labels,
        feature_count=len(feature_names),
    )

    print("[train-problem-classifier] dataset overview")
    print(f"  total rows: {dataset_stats.total_rows}")
    print(f"  rows used for training: {dataset_stats.rows_for_training}")
    print(f"  label distribution: {dataset_stats.label_distribution}")
    print(f"  selected feature count: {dataset_stats.feature_count}")

    if dataset_stats.rows_for_training == 0:
        raise SystemExit("No trainable rows after filtering.")
    if len(dataset_stats.label_distribution) < 2:
        raise SystemExit("Need at least 2 label classes to train classifier.")

    min_class = min(dataset_stats.label_distribution.values()) if dataset_stats.label_distribution else 0
    if min_class < 3:
        print("[train-problem-classifier] warning: label distribution is sparse/imbalanced; results are feasibility-only")

    X, y = prepare_xy(df, feature_names, actual_feature_cols)
    (X_train, X_valid, y_train, y_valid), split_info = split_train_valid(
        X,
        y,
        test_size=float(args.test_size),
        seed=int(args.seed),
    )

    labels_for_eval = sorted(y.unique().tolist())
    baseline_model = train_baseline_model(X_train, y_train, seed=int(args.seed))
    tree_model = train_tree_model(X_train, y_train, seed=int(args.seed))

    baseline_metrics = evaluate_model("logistic_regression", baseline_model, X_valid, y_valid, labels_for_eval)
    tree_metrics = evaluate_model("random_forest", tree_model, X_valid, y_valid, labels_for_eval)

    fi_baseline = build_feature_importance("logistic_regression", baseline_model, feature_names)
    fi_tree = build_feature_importance("random_forest", tree_model, feature_names)

    if fi_baseline is not None and fi_tree is not None:
        import pandas as pd

        feature_importance = pd.concat([fi_baseline, fi_tree], ignore_index=True)
    else:
        feature_importance = fi_baseline if fi_baseline is not None else fi_tree

    save_artifacts(
        artifacts_dir=artifacts_dir,
        dataset_stats=dataset_stats,
        split_info=split_info,
        feature_cols=feature_names,
        baseline_model=baseline_model,
        tree_model=tree_model,
        baseline_metrics=baseline_metrics,
        tree_metrics=tree_metrics,
        feature_importance=feature_importance,
    )

    print("[train-problem-classifier] metrics")
    print(
        f"  baseline(logistic_regression): acc={baseline_metrics['accuracy']:.4f} "
        f"macro_f1={baseline_metrics['macro_f1']:.4f}"
    )
    print(
        f"  tree(random_forest):          acc={tree_metrics['accuracy']:.4f} "
        f"macro_f1={tree_metrics['macro_f1']:.4f}"
    )
    print(f"[train-problem-classifier] artifacts -> {artifacts_dir}")


if __name__ == "__main__":
    main()
