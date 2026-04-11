# Runtime Reliability / Fallback

## What this means
- This is runtime-system reliability for AI path execution, not only model quality.
- High fallback means runtime frequently bypasses ranking/model influence.

## How this page detects it
- Uses:
  - runtime fallback ratio
  - ranking_fallback_used ratio
  - ranking used ratio
- Correlates with Runtime Influence to detect bypass behavior.

## Common causes
- Runtime service unavailable or timing out.
- Missing/stale model artifacts in runtime.
- Backend-runtime connectivity issues.
- Fail-open path activating frequently.

## How to investigate
1. Check fallback and ranking usage metrics.
2. Inspect runtime service health/logs and artifact freshness.
3. Validate timeout and connectivity behavior.

## How to fix / improve
1. Restore runtime service health and reduce runtime exceptions.
2. Ensure artifacts are present and loadable.
3. Tune timeouts/retries when runtime is healthy but slow.

## What to watch after fixing
- Fallback ratio should decrease.
- Ranking-used ratio should increase.
- Runtime Influence should recover from Bypassed/Low.
