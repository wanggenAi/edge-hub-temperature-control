# Cross-Module Scripts

This directory contains repository-level operational and integration scripts.

Goal:
- keep runtime code in module directories (`simulator`, `data-hub`, `hmi`, `ml`)
- keep cross-module helpers here
- avoid one-off temporary scripts leaking into core modules

## Script Index

### Active (Keep)

- `start-hmi-dev.sh`
  - One-command local startup for standalone AI runtime + HMI backend + frontend.
  - No manual `cd` required.
  - Supports `--status`, `--restart`, `--with-docker`, `--without-ai`.

- `stop-hmi-dev.sh`
  - Stops processes started by `start-hmi-dev.sh` (AI runtime/backend/frontend).
  - Supports `--status`, `--with-docker-down`.

- `reset-dev-databases.sh`
  - Resets PostgreSQL + TDengine dev data while preserving schema/stables.
  - Used by local integration workflows.

- `tdengine-retention-cleanup.sh`
  - Retention cleanup by age for TDengine super tables.
  - Referenced by deployment docs.

- `mqtt_test_client.py`
  - Manual MQTT smoke tool for telemetry/params-set/ack topic flow.

- `data_hub_stress.py`
  - MQTT ingest pressure tool for `data-hub` throughput and saturation testing.

- `seed_post_apply_validation_demo.py`
  - End-to-end demo seeding for post-apply validation scenarios.

### Archived (Manual Review)

- `hmi/backend/scripts/archive/manual-review/generate_demo_data.py`
- `hmi/backend/scripts/archive/manual-review/setup_preview_scenario.py`
- `hmi/backend/scripts/archive/manual-review/mqtt_params_set_to_tdengine.py`

These scripts were moved out of active backend script root to reduce ambiguity.
They are retained for traceability and can be restored if needed.

### Active But Specialist (Keep, expert-only)

- `mqtt_set_ack_loopback.py`
  - Bridge-like loopback for params/set -> params/ack simulation and state writeback.
  - Keep, but treat as specialist debug tooling.

- `tdengine_live_feed.py`
  - Synthetic telemetry feeder for demo environments.
  - Useful for UI/live feed demos and TDengine visibility checks.

## Local Config

- `mqtt_client_config.example.json`: template for local MQTT test settings.
- `mqtt_client_config.json`: local credentials/config override (git-ignored).

## Naming Convention

Use one of the prefixes for new scripts:

- `reset-*` : destructive/cleanup operations
- `seed-*` : deterministic demo data generation
- `mqtt-*` : broker/topic testing tools
- `tdengine-*` : TDengine maintenance or feed tools
- `stress-*` : load/performance tools

## Safety Notes

- Scripts in this folder can modify PostgreSQL/TDengine data.
- Read script help before running:

```bash
python scripts/<name>.py --help
./scripts/<name>.sh --help
```

- Prefer `--reset` and destructive options only in local dev/staging.

Documentation sync date: 2026-04-07.
