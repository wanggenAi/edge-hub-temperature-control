# Recommendation Success Predictor

## Purpose
Train the first supervised model to predict recommendation outcome:
- `improved`
- `unchanged`
- `worse`

This is a multi-class classifier trained from `recommendation_feedback.parquet`.

## Label and filtering
Training script applies strict filtering:
- `feedback_usable_for_training == true`
- `effect_outcome in {improved, unchanged, worse}`

Excluded automatically:
- pending / insufficient_data / not_applied style rows

## Input dataset
Default input path:
- `ml/data/datasets/recommendation_feedback.parquet`

You can override with `--data`.

## How to run
```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_recommendation_success_model.py \
  --data /tmp/recommendation_feedback.parquet \
  --artifacts-dir hmi/backend/artifacts/recommendation_success
```

## What gets trained
Two models are trained and compared:
1. Baseline: `LogisticRegression`
2. Tree model: `RandomForestClassifier`

Both use median imputation; baseline also uses scaling.

## Outputs
Saved under `--artifacts-dir`:
- `recommendation_success_baseline.joblib`
- `recommendation_success_tree.joblib`
- `recommendation_success_metrics.json`
- `recommendation_success_report.txt`
- `recommendation_success_feature_importance.csv`
- `recommendation_success_features.json`

## Current limitations
- Dataset size is still small, so metrics may have high variance.
- Current split is a single train/validation split (not cross-validation).
- This script does not deploy inference online; it is offline experimentation only.

Documentation sync date: 2026-05-09.
