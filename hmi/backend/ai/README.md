# AI Module

This directory contains standalone AI runtime scripts, offline training scripts,
and AI runbooks for the HMI/backend AI decision-support layer.

The online service code used by the HMI backend lives mainly in:

- `hmi/backend/app/services/ai/`

This directory complements that runtime code with process entrypoints, training
workflows, reports, and documentation.

## Implemented Online AI Flow

Current online decision path:

```text
telemetry/device context
-> feature extraction
-> problem classification
-> rule-based PID tuning
-> optional model-based candidate ranking
-> recommendation storage
-> preview simulation
-> MQTT apply through HMI backend
-> params/ack confirmation
-> post-apply evaluation
```

Important runtime components:

- `feature_extractor.py`: derives control-performance features
- `problem_classifier.py`: classifies `normal`, `slow_response`,
  `steady_state_error`, `overshoot_high`, `oscillation`, and
  `saturation_limited`
- `tuning_engine.py`: builds PID parameter recommendations
- `recommendation_orchestrator.py`: combines rule diagnosis/tuning with optional
  model-based ranking
- `recommendation_ranker.py`: ranks candidate PID settings when artifacts exist
- `preview_simulator.py`: simulates expected effect before apply
- `post_effect_evaluator.py`: compares actual telemetry after apply
- `runtime_client.py`: calls the standalone AI runtime service from the backend

## Layout

- `scripts/`: runtime service, training, ranking, feedback export, and seed tools
- `docs/`: runbooks and script-specific usage guides
- `../artifacts/`: local model artifacts and reports

## Primary Entrypoints

Run standalone AI runtime service:

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

## Model And Feedback Loop

The AI layer supports two related loops:

- online decision support: generate, preview, apply, ACK, evaluate
- offline learning: export feedback samples, train ranking/evaluation models,
  and expose lifecycle status in Ops Console

The system remains human-in-the-loop. AI recommends PID parameters, but
operator/admin apply actions still go through HMI authorization and MQTT ACK
confirmation.

## Notes

- Legacy wrappers under `hmi/backend/scripts/` have been removed.
- Keep command references aligned to `hmi/backend/ai/scripts/*`.
- Unified control-action feedback loop runbook:
  `hmi/backend/ai/docs/README_control_action_learning_loop.md`
- Runtime behavior should remain safe when optional trained artifacts are absent;
  rule-based recommendation is the baseline and model ranking is an enhancement.

Documentation sync date: 2026-05-09.
