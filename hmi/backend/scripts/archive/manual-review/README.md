# Manual Review Archive

This folder stores backend helper scripts that are not part of the default run path.

These scripts were moved from `hmi/backend/scripts/` during repository maintenance
for better maintainability and reduced ambiguity.

Archived scripts:
- `generate_demo_data.py`
- `setup_preview_scenario.py`
- `mqtt_params_set_to_tdengine.py`

Reason for archive:
- specialized/demo/debug usage
- not in primary runbook paths
- should be reviewed before deletion or formal promotion

Policy:
- do not delete directly unless usage is confirmed obsolete
- if a script becomes active again, move it back to `hmi/backend/scripts/`
  and document it in `hmi/README.md`

Documentation sync date: 2026-04-07.
