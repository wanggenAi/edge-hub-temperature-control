# EdgeHub Temperature Control

This repository contains a three-layer temperature-control engineering project:

1. Edge Control Layer: ESP32 simulation node, closed-loop control, MQTT telemetry.
2. Data Hub Layer: Java ingestion pipeline, buffering/backpressure, persistence abstraction.
3. Application Layer: HMI backend and frontend for monitoring, history, and parameter operations.

## Current Active Modules

- `simulator/wokwi`: runnable ESP32 + thermal-model simulation.
- `data-hub`: Java/Spring Boot data ingestion and storage pipeline.
- `hmi`: FastAPI backend + Vue frontend portal.
- `docs/deployment`: deployment and integration guides.

## Quick Start

1. Run edge simulation: `simulator/wokwi/README.md`
2. Run data hub: `data-hub/README.md`
3. Run HMI: `hmi/README.md`
4. Deployment docs: `docs/deployment/README.md`

## Repository Structure

```text
edge-hub-temperature-control/
├── data-hub/              Java data hub layer
├── hmi/                   Application layer (backend + frontend)
├── simulator/             Wokwi simulation and edge control validation
├── docs/                  Architecture and deployment docs
├── hardware/              Hardware and enclosure design notes
├── experiments/           Experiment records and comparison notes
├── scripts/               Helper scripts (MQTT test client, tools)
├── runtime/               Local runtime data/logs (ignored by git)
└── README.md
```

## Notes

- This repository now uses a single mainline branch (`main`).
- Removed legacy placeholder directories: `firmware/`, `edge-node/`.
- Ignore rules are aligned to prevent `node_modules`, `dist`, and similar artifacts from polluting source control.

## Documentation Sync

Last synchronized: 2026-04-04.
