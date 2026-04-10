# Label Drift

## What this means
- Label drift means recent success/gap label distributions differ from training distributions.
- This may indicate a real regime shift or label-process mismatch.

## How this page detects it
- Compares training vs recent label ratios for:
  - success labels: improved/unchanged/worse
  - gap labels: low/medium/high
- Uses row-level status (`Low/Medium/High/Insufficient data/Unknown`).
- Missing recent evidence stays null and is **not** coerced to zero.

## Common causes
- True process shift in production.
- Changed evaluation/label thresholds.
- Insufficient recent labeled samples.
- Delayed or broken label pipeline.

## How to investigate
1. Review label drift row status and ratio columns.
2. Confirm whether drift is real or evidence-insufficient.
3. Verify label semantics/thresholds are unchanged.

## How to fix / improve
1. Stabilize label-generation logic.
2. Increase recent labeled sample volume.
3. Retrain if persistent real shift is confirmed.

## What to watch after fixing
- Label-drift summary and row statuses should stabilize.
- Recent labeled coverage should improve.
- Online usefulness should stop degrading from label mismatch.
