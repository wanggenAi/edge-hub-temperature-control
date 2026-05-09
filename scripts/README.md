# Cross-Module Scripts

This directory contains repository-level operational, integration, demo, and
stress scripts.

Goal:

- keep runtime code in module directories (`simulator`, `data-hub`, `hmi`, `ml`)
- keep cross-module helpers here
- avoid one-off temporary scripts leaking into core modules
- provide stable demo/defense tooling when live edge behavior is partially
  unstable

## Script Index

### Active Core Scripts

- `start-hmi-dev.sh`
  - One-command local startup for standalone AI runtime, HMI backend, and
    frontend.
  - Supports `--status`, `--restart`, `--with-docker`, `--without-ai`.

- `stop-hmi-dev.sh`
  - Stops processes started by `start-hmi-dev.sh`.
  - Supports `--status`, `--with-docker-down`.

- `reset-dev-databases.sh`
  - Resets PostgreSQL + TDengine dev data while preserving schema/stables.
  - Useful before controlled demo-data regeneration.

- `tdengine-retention-cleanup.sh`
  - Retention cleanup by age for TDengine supertables.
  - Referenced by deployment docs.

### MQTT And Integration Tools

- `mqtt_test_client.py`
  - Manual MQTT smoke tool for telemetry, `params/set`, and `params/ack` topic
    flow.

- `mqtt_set_ack_loopback.py`
  - Bridge-like loopback for `params/set -> params/ack` simulation and state
    writeback.
  - Useful when demonstrating HMI apply/ACK behavior without relying on a live
    Wokwi edge session.

- `data_hub_stress.py`
  - MQTT ingest pressure tool for Data Hub throughput, buffering, and saturation
    testing.
  - Useful for showing system-engineering value beyond the UI.

### Demo And Defense Data Tools

- `tdengine_live_feed.py`
  - Synthetic telemetry feeder for live HMI and TDengine visibility demos.
  - Useful for keeping charts moving during a presentation.

- `seed_post_apply_validation_demo.py`
  - End-to-end post-apply validation seeding for scenarios such as success,
    partial improvement, preview mismatch, and insufficient data.
  - This is one of the highest-value scripts for thesis defense because it
    supports the AI preview vs actual-effect story.

## Recommended Defense Demo Chain

For a reliable 15-minute defense, prefer a controlled chain instead of depending
only on live device timing:

1. Use `tdengine_live_feed.py` or the Wokwi node to create visible telemetry.
2. Use HMI to generate an AI recommendation.
3. Use HMI preview to show expected effect before apply.
4. Use real edge MQTT ACK or `mqtt_set_ack_loopback.py` to demonstrate apply
   confirmation.
5. Use `seed_post_apply_validation_demo.py` to show success / partial / mismatch
   post-apply validation cases.
6. Use Ops Console and Data Hub stats to show ingestion health and system depth.

## Archived (Manual Review)

- `hmi/backend/scripts/archive/manual-review/generate_demo_data.py`
- `hmi/backend/scripts/archive/manual-review/setup_preview_scenario.py`
- `hmi/backend/scripts/archive/manual-review/mqtt_params_set_to_tdengine.py`

These scripts were moved out of the active backend script root to reduce
ambiguity. They are retained for traceability and can be restored if needed.

## Local Config

- `mqtt_client_config.example.json`: template for local MQTT test settings
- `mqtt_client_config.json`: local credentials/config override, git-ignored

Do not commit real broker passwords or private server credentials.

## Naming Convention

Use one of these prefixes for new scripts:

- `reset-*`: destructive/cleanup operations
- `seed-*`: deterministic demo data generation
- `mqtt-*`: broker/topic testing tools
- `tdengine-*`: TDengine maintenance or feed tools
- `stress-*`: load/performance tools

## Safety Notes

- Scripts in this folder can modify PostgreSQL/TDengine data.
- Read script help before running:

```bash
python scripts/<name>.py --help
./scripts/<name>.sh --help
```

- Prefer destructive options such as `--reset` only in local dev/staging.
- Keep production credentials in local config files or environment variables, not
  in committed scripts or README files.

Documentation sync date: 2026-05-09.
