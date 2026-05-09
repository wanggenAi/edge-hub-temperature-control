# Documentation Index

This directory stores architecture, interface, deployment, and project framing
documents for the active system.

## Scope

- Keep runtime-facing docs here:
  - architecture
  - MQTT/interface contracts
  - deployment and operations
  - project profile / defense framing
- Keep experiment logs in `experiments/`
- Keep hardware design references in `hardware/`
- Keep module-specific commands in each module README

## Current Documents

- `project-profile.md`: concise project identity, implementation map, AI/MQTT
  status, and thesis-defense framing
- `architecture-overview.md`: end-to-end active architecture and runtime flow
- `mqtt_interface.md`: implemented MQTT topic/payload contract and reserved
  extension points
- `development-roadmap.md`: historical roadmap and milestones
- `repository-maintenance-audit.md`: cleanup classification and phased
  maintenance plan
- `deployment/README.md`: deployment document index
- `deployment/mqtt-broker-ubuntu.md`: Mosquitto broker deployment guide
- `deployment/tdengine-docker-local.md`: TDengine local deployment guide

## Maintenance Rules

- Avoid duplicating run commands already maintained in module READMEs.
- Prefer linking to source module docs (`simulator/`, `data-hub`, `hmi`, `ml`)
  for module-specific operations.
- Mark reserved/future topics explicitly instead of presenting them as already
  implemented.
- If a document becomes historical-only, move it to an archive subfolder instead
  of deleting it.

Documentation sync date: 2026-05-09.
