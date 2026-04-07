# AI Module (Isolated)

This directory centralizes AI-related runtime and training assets so the HMI web layer can stay thin and stable.

## Layout

- `scripts/`: AI runtime server, model training, ranking, feedback export/seed scripts
- `docs/`: AI script usage docs
- `../artifacts/`: trained model artifacts and reports

## Recommended entrypoints

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

## Backward compatibility

Legacy wrappers remain in `hmi/backend/scripts/*.py` and forward to `hmi/backend/ai/scripts/*`.
