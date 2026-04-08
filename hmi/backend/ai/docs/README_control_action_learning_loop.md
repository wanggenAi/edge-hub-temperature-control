# Control-Action Learning Loop (Unified Feedback)

## Overview

The learning loop now ingests **all successfully applied control actions**, not only AI recommendation applies.

Supported action sources:
- `ai_recommendation`
- `manual_user`
- `rule_engine`
- `system`
- `imported`

Core workflow:
1. Control action is applied successfully.
2. `ControlAction` row is created.
3. `ControlActionEvalJob` is created with `pending` status.
4. Worker evaluates post-apply telemetry.
5. `ControlActionFeedbackSample` is persisted with labels and quality markers.

## Offline Retraining + Gated Promotion

This repository is intentionally **offline/batch retraining only**.

Recommended model directories:
- Active: `hmi/backend/artifacts/active/`
- Candidate: `hmi/backend/artifacts/candidates/<timestamp>/`
- Archive: `hmi/backend/artifacts/archive/`

Promotion policy:
1. Export eligible feedback samples.
2. Train candidate model offline.
3. Evaluate candidate vs active model on holdout/recent samples.
4. Promote candidate only if it clearly outperforms active.
5. Otherwise keep current active model.

No online incremental training or auto-promotion is performed in runtime APIs.

## Worker

Run pending evaluations:

```bash
cd hmi/backend
python scripts/run_control_action_feedback_worker.py --batch-size 50
```

Dry run:

```bash
python scripts/run_control_action_feedback_worker.py --dry-run
```

Execution model:
- this worker is a **one-shot batch** script
- trigger it externally (cron/systemd/K8s CronJob), do not run a tight internal loop
- recommended cadence: **every 10 minutes**

## Observation Window Policy (Default)

Centralized deterministic defaults:
- AI + `oscillation` or `overshoot_high`: `12` minutes
- AI + `steady_state_error`: `18` minutes
- AI + `slow_response` or `saturation_limited`: `25` minutes
- other AI actions: `15` minutes
- manual actions (no AI context): `20` minutes

Scheduling rule:
- eval jobs are scheduled at `applied_at + observation_window_minutes`
- this delay is intentional so post-apply telemetry can mature before evaluation

## Retry Policy

Recoverable timing/readiness cases (for example, window not mature yet, not enough post-apply points):
- reschedule as `pending`
- retry delay: `5` minutes
- max retries: `6`

Terminal insufficient:
- retry budget exhausted
- or clearly non-recoverable data quality conditions
- examples: conflicting parameter changes in window, target temp changed mid-window, device offline too long, missing required source context

## Training Eligibility Policy

Single mapping:
- `high` => training eligible
- `medium` => training eligible
- `low` => not training eligible
- `reject` => not training eligible

Why delayed evaluation is better:
- immediate evaluation often produces false `insufficient_data` outcomes
- delaying until the observation window closes yields more stable effect labels and higher-quality training samples

## Export Training Dataset

```bash
python ml/scripts/export_control_action_feedback_samples.py
```

Default output:
- `ml/data/datasets/control_action_feedback_samples.parquet`
