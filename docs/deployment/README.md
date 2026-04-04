# Deployment Documents

This directory stores deployment-oriented documents for services and system
components that will appear as the project evolves from simulation to integrated
engineering implementation.

The current goal is not to claim that every deployable service already exists.
Instead, this directory is used to establish a clear documentation skeleton so
that later deployment work can be recorded consistently and reused in the
thesis.

## Current Scope

At the current stage, the available deployment documents are:

- `mqtt-broker-ubuntu.md`
- `tdengine-docker-local.md`

This document records the minimum practical deployment path for a self-managed
MQTT broker based on Mosquitto on Ubuntu, with public access and username /
password authentication.

The TDengine document records the recommended local Docker-based deployment
path, including Docker Desktop preparation, Compose startup, REST verification,
and integration with the Java `data-hub`.

These documents currently support three active runtime paths:

- edge simulation runtime (`simulator/wokwi`)
- data-hub runtime (`data-hub`)
- HMI runtime (`hmi`)

## Planned Deployment Topics

The following deployment documents are expected to be added later:

- backend service deployment
- frontend service deployment
- HMI deployment
- edge node deployment
- Docker-based deployment
- TLS-enabled MQTT deployment
- ACL and broker hardening notes

## Suggested Organization

The deployment documentation can continue to grow under this directory with a
flat and readable naming style, for example:

- `mqtt-broker-ubuntu.md`
- `backend-service-ubuntu.md`
- `frontend-service-nginx.md`
- `hmi-service-deployment.md`
- `edge-node-raspberry-pi.md`
- `docker-compose-stack.md`

This keeps the structure simple while making later expansion straightforward.

Documentation sync date: 2026-04-04.
