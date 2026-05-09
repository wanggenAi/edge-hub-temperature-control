# Preview Gap Predictor

## Purpose
Train the second supervised model to predict preview reliability level:
- `low`
- `medium`
- `high`

Label column: `preview_gap_level`.

## Label and filtering
Training script filters to:
- `feedback_usable_for_training == true`
- `preview_gap_level in {low, medium, high}`

Rows outside these conditions are excluded.

## Leakage rule (important)
The following columns are **not** allowed as input features because they are post-hoc gap results and would leak the target:
- `preview_gap_in_band_ratio`
- `preview_gap_overshoot_c`
- `preview_gap_settling_sec`
- `preview_gap_mean_abs_error`
- `preview_gap_saturation_ratio`
- `preview_gap_temp_swing`

## Input dataset
Default: `ml/data/datasets/recommendation_feedback.parquet`

You can override with `--data`.

## How to run
```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_preview_gap_model.py \
  --data /tmp/recommendation_feedback.parquet \
  --artifacts-dir hmi/backend/artifacts/preview_gap
```

## Models
1. Baseline: `LogisticRegression`
2. Tree: `RandomForestClassifier`

Both use median imputation; baseline also uses standardization.

## Outputs
Saved under `--artifacts-dir`:
- `preview_gap_baseline.joblib`
- `preview_gap_tree.joblib`
- `preview_gap_metrics.json`
- `preview_gap_report.txt`
- `preview_gap_feature_importance.csv`
- `preview_gap_features.json`

## Current limitations
- Dataset size is still limited.
- Single train/validation split (no CV in this first version).
- Offline experiment only; no online inference wiring in this step.

Documentation sync date: 2026-05-09.
