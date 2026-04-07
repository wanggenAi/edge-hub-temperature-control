# Documentation Index

This directory stores architecture and deployment documents for active modules.

## Scope

- Keep runtime-facing docs here:
  - architecture
  - interfaces/protocols
  - deployment and operations
- Keep experiment logs in `experiments/`
- Keep hardware design references in `hardware/`

## Current Documents

- `architecture-overview.md`: end-to-end system architecture overview
- `development-roadmap.md`: project roadmap and milestones
- `mqtt_interface.md`: MQTT topic/payload contract
- `repository-maintenance-audit.md`: cleanup classification and phased maintenance plan
- `deployment/README.md`: deployment document index
- `deployment/mqtt-broker-ubuntu.md`: broker deployment guide
- `deployment/tdengine-docker-local.md`: TDengine local deployment guide

Documentation sync date: 2026-04-07.

## Maintenance Rules

- Avoid duplicating run commands already maintained in module READMEs.
- Prefer linking to source module docs (`simulator/`, `data-hub/`, `hmi/`, `ml/`) for module-specific operations.
- If a document is historical-only, move it to an archive subfolder instead of deleting.
