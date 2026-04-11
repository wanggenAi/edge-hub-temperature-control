# Runtime Influence

## What this means
- This indicates whether ranking meaningfully changes final recommendations.
- `Low` influence can be expected in stable regimes, but can also reveal over-conservative ranking.
- `Bypassed` usually indicates fallback-dominant runtime behavior.

## How this page detects it
- Uses:
  - ranking used ratio
  - runtime fallback ratio
  - rule_center selected ratio / non-rule-center share

## Common causes
- Candidate set too close to `rule_center`.
- Ranking weights suppress non-base candidates.
- Runtime fallback path activates too often.
- Runtime availability/latency issues.

## How to investigate
1. Check ranking-used and fallback ratios.
2. Check `rule_center` selected percentage.
3. Inspect candidate distribution and strategy mix.

## How to fix / improve
1. Verify runtime path and artifact loading health.
2. Revisit ranking weights and candidate diversity.
3. Confirm whether low influence is expected for current operating profile.

## What to watch after fixing
- Non-`rule_center` share should increase when appropriate.
- Fallback ratio should decrease.
- Runtime Influence should move toward Moderate/High if model is expected to drive decisions.
