# Backend Scripts (Operational)

This directory is intentionally minimal.

## Active scripts

- `db_migrate.py`: run Alembic migration to head
- `db_seed.py`: seed default rules/demo relational data (supports `TC-PREVIEW-*` AI demo cases)
- `run_control_action_feedback_worker.py`: evaluate pending control-action feedback jobs

## Archived scripts

Specialized/demo scripts are archived under:

- `archive/manual-review/`

They are kept for traceability and can be restored if they become part of
active runbooks.

AI runtime/training scripts are intentionally maintained under:

- `hmi/backend/ai/scripts/`
- `hmi/backend/ai/docs/`

## Usage

```bash
cd hmi/backend
python scripts/db_migrate.py
python scripts/db_seed.py --rules
python scripts/db_seed.py --preview-ai-demo
python scripts/run_control_action_feedback_worker.py --batch-size 50
```

Documentation sync date: 2026-04-07.
