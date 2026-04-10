# Feature Drift

## What this means
- Feature drift means live feature distributions diverged from training/baseline distributions.
- This can degrade online behavior even if offline metrics were previously strong.

## How this page detects it
- Compares baseline vs recent mean/P50/P95 for curated features.
- Aggregates per-feature statuses into a summary.
- Uses `Insufficient data` when recent sample volume is not enough.

## Common causes
- New operating regimes (environment/device/load changes).
- Changed action ranges (delta_kp/ki/kd behavior shifts).
- Feature instability/noise growth.

## How to investigate
1. Identify which features are High/Medium.
2. Check whether drift is concentrated in error features, control deltas, or preview metrics.
3. Verify recent sample volume before drawing strong conclusions.

## How to fix / improve
1. Retrain with recent representative data.
2. Expand training coverage for new regimes.
3. Improve feature engineering and stabilize noisy signals.

## What to watch after fixing
- Feature drift summary should move toward Low.
- Online usefulness should recover.
- Offline validation on refreshed data should remain stable.
