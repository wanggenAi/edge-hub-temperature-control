# EdgeHub Temperature Control

EdgeHub is an end-to-end temperature-control engineering repository with four
active runtime/data layers:

1. Edge control (`simulator/wokwi`): ESP32 firmware (simulation + real-hardware profile), MQTT telemetry, `params/set`, `params/ack`.
2. Ingestion layer (`data-hub`): Java/Spring Boot MQTT consumer with bounded backpressure and storage routing (TDengine/log).
3. Application layer (`hmi`): FastAPI backend + React frontend + AI runtime integration for recommendations.
4. Offline data pipeline (`ml`): TDengine export and feature/label dataset preparation.

## Technology Stack (Current Codebase)

- Edge firmware: PlatformIO + Arduino framework on ESP32 (`simulator/wokwi/platformio.ini`)
- Data hub: Java 17, Spring Boot 3.4.x, Gradle wrapper, Reactor, HiveMQ MQTT client
- HMI backend: Python + FastAPI + SQLAlchemy + Alembic + PostgreSQL
- HMI frontend: React 18 + TypeScript + Vite + Tailwind CSS
- AI/runtime helpers: Python scripts under `hmi/backend/ai/scripts`
- Time-series and messaging: TDengine + MQTT broker (Mosquitto or compatible)
- Infra (local dev): Docker Compose files for PostgreSQL, TDengine, Redis

## Repository Layout

```text
edge-hub-temperature-control/
├── simulator/             ESP32 firmware and Wokwi simulation assets
├── data-hub/              Java ingestion/backpressure/storage service
├── hmi/                   FastAPI backend, React frontend, AI runtime module
├── ml/                    Offline TDengine -> feature/label data pipeline
├── scripts/               Cross-module ops/debug/stress helper scripts
├── docs/                  Architecture, interfaces, deployment docs
├── hardware/              Hardware and enclosure references
├── experiments/           Experiment notes and comparative records
├── runtime/               Local runtime outputs (logs/data, git-ignored)
└── README.md
```

## Quick Start (Local Integration)

1. Start local infrastructure (pick what you need):

```bash
docker compose -f docker-compose.postgresql.yml up -d
docker compose -f docker-compose.tdengine.yml up -d
docker compose -f docker-compose.redis.yml up -d
```

2. Start Data Hub (MQTT -> TDengine/log):

```bash
cd data-hub
./gradlew bootRun
```

3. Start HMI backend:

```bash
cd hmi/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/db_migrate.py
python scripts/db_seed.py --rules
uvicorn app.main:app --reload
```

4. Optional: start AI runtime service (decoupled process):

```bash
cd hmi/backend
.venv/bin/python ai/scripts/run_ai_service.py --host 127.0.0.1 --port 8010
```

5. Start HMI frontend:

```bash
cd hmi/frontend
npm install
npm run dev
```

## Core Runtime Interfaces

- MQTT telemetry and control topics:
  - telemetry stream
  - `params/set` (HMI/ops -> edge intent)
  - `params/ack` (edge -> applied/ack status)
- HMI backend uses:
  - PostgreSQL for relational control-plane data
  - TDengine for telemetry/history/alarm time-series reads (when enabled)
- AI recommendation path:
  - remote runtime service when configured
  - automatic backend fallback to local logic when remote runtime is unavailable

## Module Documentation

- Edge firmware + simulator: `simulator/wokwi/README.md`
- Data hub: `data-hub/README.md`
- HMI backend/frontend: `hmi/README.md`
- AI module docs: `hmi/backend/ai/README.md`
- Offline ML pipeline: `ml/README.md`
- Deployment docs: `docs/deployment/README.md`
- Cross-module script index: `scripts/README.md`

## Notes

- Keep module-specific run commands in module READMEs as the source of truth.
- Root README is an integration index and should reflect current code structure,
  active entrypoints, and real technology choices.

Documentation sync date: 2026-04-07.
