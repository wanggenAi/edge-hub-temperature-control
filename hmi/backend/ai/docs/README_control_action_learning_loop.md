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

## Export Training Dataset

```bash
python ml/scripts/export_control_action_feedback_samples.py
```

Default output:
- `ml/data/datasets/control_action_feedback_samples.parquet`

