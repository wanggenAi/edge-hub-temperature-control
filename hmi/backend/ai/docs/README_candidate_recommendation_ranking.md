# Candidate Recommendation Ranking (Prototype)

## What this does
This is a decision-layer prototype (Layer 4) that **ranks multiple PID candidates** instead of directly generating PID params end-to-end.

Pipeline:
1. Generate 3~8 candidate PID recommendations around a context recommendation.
2. Score each candidate with:
   - Recommendation Success Predictor
   - Preview Gap Predictor
3. Compute a combined score.
4. Return ranked candidates and top-1.

## Not in scope
- No HMI integration
- No online API serving
- No direct PID-regression model

## Dependencies
- Feedback dataset parquet (context source)
- Trained success predictor model artifact
- Trained preview gap model artifact

## Run
```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/rank_candidate_recommendations.py \
  --data /tmp/recommendation_feedback.parquet \
  --success-model hmi/backend/artifacts/recommendation_success/recommendation_success_tree.joblib \
  --preview-gap-model hmi/backend/artifacts/preview_gap/preview_gap_baseline.joblib \
  --output hmi/backend/artifacts/candidate_ranking_result.json
```

Optional:
- `--recommendation-id <id>`
- `--device-id <id>`

If none is passed, script uses latest usable row from dataset as context.

## Candidate count
Current prototype generates 6 candidates:
- `rule_center`
- `conservative`
- `aggressive`
- `overshoot_guard`
- `settling_focus`
- `baseline_hold`

## Scoring formula
- `success_score = P(improved) - 0.5 * P(unchanged) - 1.0 * P(worse)`
- `gap_score = P(low) - 0.5 * P(medium) - 1.0 * P(high)`
- `total_score = 0.65 * success_score + 0.35 * gap_score`

Candidates are ranked by descending `total_score`.

## Output interpretation
For each candidate:
- baseline/recommended/delta params
- preview summary
- success model probabilities
- preview gap model probabilities
- total score + rank

Top-1 candidate is the recommendation with highest total score.

## Current limitations
- Context is built from dataset rows (offline mode), not yet online runtime state.
- Candidate generation uses heuristic perturbations (not optimization search).
- Weight coefficients are fixed and hand-tuned for interpretability.
