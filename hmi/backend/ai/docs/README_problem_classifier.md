# Control Problem Classifier

## Purpose
Train a window-level multiclass classifier to identify control issues from telemetry features.

Label column: `problem_type`.

## Target labels
Primary target set:
- `normal`
- `slow_response`
- `overshoot_high`
- `steady_state_error`
- `oscillation`
- `saturation_limited`

The script keeps real dataset labels when the target set is sparse in current data.

## Dataset
Default input:
- `ml/data/datasets/labeled_samples.parquet`

## Run
```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_problem_classifier.py
```

Optional:
```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_problem_classifier.py \
  --data ml/data/datasets/labeled_samples.parquet \
  --artifacts-dir hmi/backend/artifacts/problem_classifier \
  --test-size 0.3 \
  --seed 20260407
```

## Features (first pass)
- `mean_error`
- `mean_abs_error`
- `error_std`
- `temp_swing`
- `pwm_mean` (resolved from `pwm_duty_mean` when present)
- `pwm_max` (resolved from `pwm_duty_max` when present)
- `zero_crossings`
- `in_band_ratio`
- `overshoot_pct`
- `overshoot_c`
- `settling_sec`
- `saturation_ratio`
- `rise_slope`
- `abs_error_max`

## Output artifacts
- `problem_classifier_baseline.joblib`
- `problem_classifier_tree.joblib`
- `problem_classifier_metrics.json`
- `problem_classifier_report.txt`
- `problem_classifier_feature_importance.csv`
- `problem_classifier_features.json`

Default artifact directory:
- `hmi/backend/artifacts/problem_classifier`

## Limitations
- Strongly depends on label distribution quality from rule-based pseudo labeling.
- If classes are imbalanced/sparse, metrics are feasibility-level only.
- This is offline training only (no HMI/API integration in this step).
