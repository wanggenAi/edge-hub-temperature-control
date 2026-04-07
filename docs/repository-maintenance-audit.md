# Repository Maintenance Audit (Close-out)

Date: 2026-04-07

This audit classifies files/directories into:
- `keep`
- `move/archive`
- `safe-to-delete`
- `need-manual-review`

Principle: no behavior breakage for simulator/real dual mode, MQTT telemetry + params/set + params/ack, and safety logic.

## A. Module-Level Classification

### keep

- `simulator/wokwi/` (active edge module)
- `data-hub/` (active ingest module)
- `hmi/` (active application module)
- `ml/` (active data pipeline)
- `docs/`, `hardware/`, `experiments/`
- `docker-compose.*.yml`

### move/archive

- `simulator/wokwi/src/legacy/sketch_legacy_v3_1.ino.txt`
  - candidate destination: `simulator/wokwi/src/archive/legacy/`
  - low risk, but keep until README link is updated

### safe-to-delete

- none committed at repository level in this audit pass

### need-manual-review

- `hmi/backend/scripts/archive/manual-review/generate_demo_data.py`
- `hmi/backend/scripts/archive/manual-review/setup_preview_scenario.py`
- `hmi/backend/scripts/archive/manual-review/mqtt_params_set_to_tdengine.py`

Reason: specialized workflows, not clearly referenced by main runbooks, but may still be used in internal demos/debug.

## B. Script-Level Classification

### scripts/ (root)

- keep:
  - `reset-dev-databases.sh`
  - `tdengine-retention-cleanup.sh`
  - `mqtt_test_client.py`
  - `data_hub_stress.py`
  - `seed_post_apply_validation_demo.py`
  - `mqtt_set_ack_loopback.py`
  - `tdengine_live_feed.py`
- keep (local template):
  - `mqtt_client_config.example.json`
- git-ignored local config:
  - `mqtt_client_config.json`

### hmi/backend/ai/scripts/

All files are active and should remain in place:
- `run_ai_service.py`
- `train_recommendation_success_model.py`
- `train_preview_gap_model.py`
- `train_problem_classifier.py`
- `rank_candidate_recommendations.py`
- `export_recommendation_feedback_dataset.py`
- `seed_recommendation_feedback_demo.py`

### hmi/backend/scripts/

- keep:
  - `db_migrate.py`
  - `db_seed.py`
- archived for manual review:
  - `archive/manual-review/generate_demo_data.py`
  - `archive/manual-review/setup_preview_scenario.py`
  - `archive/manual-review/mqtt_params_set_to_tdengine.py`

### ml/scripts/

All files are active and documented in `ml/README.md`.

## C. Ignore/Cleanup Notes

Current `.gitignore` already covers major local artifacts:
- virtualenvs
- frontend node_modules/dist
- runtime data/logs
- local secrets/configs
- generated parquet data

Operational recommendation:
- periodically clean local caches:
  - `find . -type d -name __pycache__ -prune -exec rm -rf {} +`
- do not commit local IDE/runtime folders (`.idea`, `.gradle`, `.pio`, `.vscode` local overrides)

## D. Do-Not-Touch Paths

To avoid breaking active behavior, do not rename/move without dedicated migration:
- `simulator/wokwi/platformio.ini`
- `simulator/wokwi/src/config/build_profile.h`
- `simulator/wokwi/src/sketch.ino`
- `hmi/backend/app/services/ai/*`
- `hmi/backend/app/api/routes/devices.py` (recommendation entrypoints)
- `data-hub/config/application*.properties`

## E. Next Steps

- Phase 1: documentation + script-index cleanup (done in this pass)
- Phase 2: archive candidate legacy/specialized scripts after owner confirmation
- Phase 3: naming consistency polish across docs and script names
