# AI Module

This directory centralizes AI runtime and offline model workflows to keep HMI
web-layer code isolated from model lifecycle changes.

## Layout

- `scripts/`: runtime service, model training, ranking, feedback export/seed
- `docs/`: usage guides for each AI script
- `../artifacts/`: local model artifacts and reports

## Primary Entrypoints

Run AI runtime service:

```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/run_ai_service.py --host 127.0.0.1 --port 8010
```

Train models:

```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_problem_classifier.py
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_recommendation_success_model.py
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_preview_gap_model.py
```

Rank recommendation candidates:

```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/rank_candidate_recommendations.py
```

Prepare or refresh recommendation feedback dataset:

```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/export_recommendation_feedback_dataset.py
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/seed_recommendation_feedback_demo.py
```

## Notes

- Legacy wrappers under `hmi/backend/scripts/` have been removed.
- Keep command references aligned to `hmi/backend/ai/scripts/*`.

Documentation sync date: 2026-04-07.
