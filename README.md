# EdgeHub Temperature Control

EdgeHub is a three-layer temperature-control engineering repository:

1. Edge Control Layer: ESP32 control loop (simulator + real-hardware build profile), MQTT telemetry, params/set + params/ack.
2. Data Hub Layer: Java/Spring ingestion, buffering/backpressure, persistence abstraction.
3. Application Layer: HMI backend/frontend, recommendation workflow, AI runtime integration.

## Active Modules

- `simulator/wokwi`: edge firmware baseline (simulator + real hardware profiles).
- `data-hub`: MQTT ingest + TDengine/other storage routing.
- `hmi`: FastAPI backend + frontend portal + AI runtime integration.
- `ml`: offline training-data pipeline.
- `docs/deployment`: deployment and integration guides.

## Quick Start

1. Edge simulation / firmware profile guide: `simulator/wokwi/README.md`
2. Data hub setup: `data-hub/README.md`
3. HMI + AI runtime setup: `hmi/README.md`
4. Deployment docs: `docs/deployment/README.md`
5. Repository cleanup/audit notes: `docs/repository-maintenance-audit.md`

## Repository Layout

```text
edge-hub-temperature-control/
├── simulator/             Edge firmware (Wokwi + real-hardware profile)
├── data-hub/              Java ingestion and routing service
├── hmi/                   Backend, frontend, AI runtime module
├── ml/                    Offline data pipeline for model preparation
├── docs/                  Architecture and deployment documentation
├── hardware/              Hardware and enclosure references
├── experiments/           Experiment records and comparison notes
├── scripts/               Cross-module ops/debug helper scripts
├── runtime/               Local runtime/log outputs (git-ignored)
└── README.md
```

## Scope Boundaries

- Keep behavior stable for:
  - simulator/real dual build mode
  - MQTT `params/set`, `params/ack`, telemetry flow
  - safety/protection paths and hardware-related logic
- Repository cleanup should prioritize:
  - archival over deletion when usage is uncertain
  - README normalization and discoverability
  - minimizing path changes for active build/runtime entrypoints

## Status

- Mainline branch: `main`
- Current objective: maintenance-grade cleanup and documentation normalization (no behavior change)
