# Offline Model Quality

## What this means
- This indicates whether the **success model** and **preview-gap model** learned useful patterns offline.
- In this project, **Macro F1 is more important than raw accuracy**, because accuracy can hide poor behavior on minority risky classes.

## How this page detects it
- Uses offline evaluation artifacts for:
  - success model `macro_f1`
  - preview-gap model `macro_f1`
  - dangerous-class recall: `Recall(worse)` and `Recall(high)`
  - validation size and artifact freshness
- Cross-checks confusion-matrix behavior for risky misclassification patterns.

## Common causes
- Validation split too small.
- Class imbalance, especially too few `worse` / `high` samples.
- Weak feature quality for risky scenarios.
- Stale artifact relative to current production regime.

## How to investigate
1. Open **Offline Model Evaluation (Compact)** and check `macro_f1`, dangerous-class recall, and validation size.
2. Open deeper offline details and inspect confusion matrices.
3. Confirm artifact timestamp is recent enough for current production behavior.

## How to fix / improve
1. Collect more labeled samples, prioritizing `worse` and `high`.
2. Improve feature quality and label consistency in the feedback pipeline.
3. Retrain and compare candidate vs active artifact before promotion.

## What to watch after fixing
- Success and preview-gap `macro_f1` should improve.
- `Recall(worse)` and `Recall(high)` should improve first.
- Risky confusion patterns should shrink.
