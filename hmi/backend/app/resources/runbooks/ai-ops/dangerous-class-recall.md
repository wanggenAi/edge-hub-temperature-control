# Dangerous-Class Recall (`worse`, `high`)

## What this means
- Low recall on `worse` or `high` means risky cases are missed.
- In this project, this is a high-priority safety/quality signal.

## How this page detects it
- Uses `Recall(worse)` (success model) and `Recall(high)` (preview-gap model).
- Cross-checks confusion matrices for risky-class leakage into safer classes.

## Common causes
- Too few risky examples in training/validation.
- Class imbalance suppressing minority recall.
- Features not discriminative for risky dynamics.
- Ranking/risk weighting misaligned with risky behavior.

## How to investigate
1. Review dangerous-class recall values and support counts.
2. Inspect confusion matrices for risky-class misses.
3. Check whether risky scenarios are represented in recent labeled data.

## How to fix / improve
1. Collect and label more `worse` / `high` samples.
2. Rebalance training strategy (class weighting/sampling).
3. Improve risky-case feature quality and validate targeted slices.
4. Revisit risk weighting in ranking logic.

## What to watch after fixing
- `Recall(worse)` and `Recall(high)` should rise.
- Risky confusion patterns should reduce.
- Online worse-ratio behavior should improve.
