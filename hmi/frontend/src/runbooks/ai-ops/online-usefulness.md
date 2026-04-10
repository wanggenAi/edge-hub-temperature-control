# Online Usefulness

## What this means
- This answers whether AI is creating value versus manual actions in production.
- `Unknown` means insufficient evidence, not automatically good or bad.

## How this page detects it
- Uses:
  - AI vs manual improved-ratio delta
  - AI worse-ratio vs manual worse-ratio
  - recent evaluated sample counts (AI and manual)
- If sample counts are below threshold, status is `Unknown`.

## Common causes
- Too few recent evaluated samples.
- Preview-gap model weak in current regime.
- Ranking objective too conservative or misweighted.
- Feedback loop or evaluation window problems.

## How to investigate
1. Compare AI/manual improved ratios and worse ratios.
2. Check whether `Unknown` is caused by low evaluated sample volume.
3. Cross-check Runtime Influence to verify model decisions are actually applied.

## How to fix / improve
1. Stabilize post-apply evaluation throughput.
2. Review outcomes by scenario/problem type.
3. Tune ranking strategy and retrain with recent data when needed.

## What to watch after fixing
- AI vs manual improved delta should improve.
- AI worse ratio should not exceed manual worse ratio.
- Online Usefulness should move away from Unknown/Negative.
