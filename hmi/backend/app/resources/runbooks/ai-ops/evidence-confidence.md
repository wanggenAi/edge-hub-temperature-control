# Evidence Confidence

## What this means
- This is confidence in the **conclusion**, not model quality itself.
- Low confidence means sample volume/freshness is weak, so judgments should be treated cautiously.

## How this page detects it
- Uses:
  - validation sample sizes
  - recent feedback sample count
  - recent evaluated AI/manual outcome sample counts
  - availability of recent labeled data for drift

## Common causes
- Small validation sets.
- Post-apply evaluation jobs not completing.
- Feedback samples missing labels or not training-eligible.
- Offline artifacts present but stale.

## How to investigate
1. Check validation size in offline model cards.
2. Check evaluated sample counts in Online Outcome Quality.
3. Check recent feedback volume and label coverage in Drift/Data Health.

## How to fix / improve
1. Increase validated/labeled sample volume.
2. Ensure post-apply evaluation and feedback writing are healthy.
3. Regenerate offline metrics after retraining.

## What to watch after fixing
- Evidence confidence should move Low -> Medium -> High.
- Recent sample counts and label coverage should trend upward.
