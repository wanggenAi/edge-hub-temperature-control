# Backend Scripts (Operational)

This directory is intentionally minimal.

## Active scripts

- `db_migrate.py`: run Alembic migration to head
- `db_seed.py`: seed default rules/demo relational data

## Archived scripts

Specialized/demo scripts are archived under:

- `archive/manual-review/`

They are kept for traceability and can be restored if they become part of
active runbooks.

## Usage

```bash
cd hmi/backend
python scripts/db_migrate.py
python scripts/db_seed.py --rules
```
