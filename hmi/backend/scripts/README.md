# Backend Scripts (Operational)

This directory is intentionally minimal.

## Active scripts

- `db_migrate.py`: run Alembic migration to head
- `db_seed.py`: seed default rules/demo relational data (supports `TC-PREVIEW-*` AI demo cases)
- `seed_defense_demo.py`: seed a curated defense demo dataset (`DEF-*`) from multiple thermal environments, with device curves, alarms, AI recommendations, applied actions, feedback samples, optional model lifecycle rows, and optional MQTT telemetry replay
- `ensure_defense_live_device.py`: ensure the Wokwi/live closed-loop device (`edge-node-001` by default) exists in PostgreSQL and is assigned to HMI users
- `live_thermal_edge_node.py`: run a real MQTT edge simulator for the live defense flow; it receives `params/set`, publishes `params/ack`, and continuously emits thermal telemetry for Data Hub to write into TDengine
- `run_control_action_feedback_worker.py`: one-shot batch evaluator for pending control-action feedback jobs

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
python scripts/ensure_defense_live_device.py
python scripts/seed_defense_demo.py --reset
python scripts/seed_defense_demo.py --mqtt-replay --mqtt-replay-limit 120
python scripts/live_thermal_edge_node.py --device-id LIVE-DEMO-01 --environment defense_live
python scripts/run_control_action_feedback_worker.py --batch-size 50
```

Defense demo intent:
- `DEF-STABLE-01`: stable closed-loop baseline
- `DEF-SLOW-01`: slow response and safe gain-increase recommendation
- `DEF-OSC-01`: oscillation, damping recommendation, applied action, and feedback sample
- `DEF-OVS-01`: overshoot reduction recommendation with post-apply comparison
- `DEF-SAT-01`: actuator saturation boundary and high-risk warning
- `DEF-SSE-01`: steady-state error and integral correction with feedback sample

Thermal environments used by `seed_defense_demo.py`:
- `balanced_cell`: normal cell with enough actuator headroom
- `high_mass_load`: large thermal capacity, slow response under weak gains
- `laggy_loop`: delayed heat transfer, prone to oscillation
- `fast_heater`: low thermal inertia, prone to overshoot
- `weak_actuator`: limited actuator and high heat loss
- `loss_drift`: heat-loss drift where integral action matters

Use `--mqtt-replay` only when the configured broker is reachable. It publishes
generated telemetry to `edge/temperature/{device_id}/telemetry` using the HMI
backend MQTT settings by default.

Live defense flow:
- Start PostgreSQL and TDengine Docker.
- Run migrations and seed rules.
- Start Data Hub with `datahub.storage.mode=tdengine-rest`.
- Start HMI backend/frontend.
- Start `live_thermal_edge_node.py`.
- In the HMI page, open `LIVE-DEMO-01` and change the target temperature. The
  expected path is: HMI `params/set` publish -> live edge node applies it ->
  live edge node publishes `params/ack` -> Data Hub writes `params_ack` and
  telemetry into TDengine -> HMI chart moves toward the new target.

`live_thermal_edge_node.py` is intentionally different from the seed script:
it does not write TDengine directly. TDengine rows should appear only after Data
Hub consumes the MQTT telemetry/ACK messages.

Recommended scheduling:
- trigger `run_control_action_feedback_worker.py` externally every `10` minutes
- avoid per-minute execution; delayed batches reduce premature insufficient-data evaluations

Documentation sync date: 2026-05-09.
