# EdgeHub Temperature Control

EdgeHub is an end-to-end intelligent temperature-control engineering repository.
It combines edge closed-loop control, MQTT communication, Java-based ingestion,
time-series persistence, HMI operations, and AI-assisted PID parameter
optimization.

The strongest current project framing is:

> An intelligent temperature-control platform with edge execution, MQTT-based
> communication, data-hub ingestion, HMI operations, AI recommendation, preview,
> MQTT apply, ACK confirmation, and post-apply validation.

## Active Runtime/Data Layers

1. Edge control (`simulator/wokwi`): ESP32 firmware for Wokwi simulation and
   real-hardware profile, MQTT telemetry, `params/set`, `params/ack`, safety
   status, and runtime parameter handling.
2. Communication and ingestion (`MQTT broker` + `data-hub`): Java/Spring Boot
   MQTT consumer with bounded backpressure, TDengine/log/file persistence,
   device status tracking, and runtime metrics.
3. Application and operations (`hmi`): FastAPI backend, React frontend,
   PostgreSQL control plane, TDengine history reads, MQTT command publishing,
   AI recommendation UI, and Ops Console.
4. AI and offline learning (`hmi/backend/app/services/ai`, `hmi/backend/ai`,
   `ml`): feature extraction, problem classification, PID tuning, preview
   simulation, optional model ranking, post-apply evaluation, and feedback data
   preparation.

## Technology Stack

- Edge firmware: PlatformIO + Arduino framework on ESP32
- MQTT broker: Mosquitto or compatible broker
- Data hub: Java 17, Spring Boot 3.4.x, Gradle Wrapper, Reactor, HiveMQ MQTT client
- Time-series storage: TDengine
- HMI backend: Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL
- HMI frontend: React 18, TypeScript, Vite, Tailwind CSS
- AI/runtime helpers: Python modules and scripts under `hmi/backend/app/services/ai`
  and `hmi/backend/ai/scripts`
- Local infrastructure: Docker Compose files for PostgreSQL, TDengine, and Redis

## Repository Layout

```text
edge-hub-temperature-control/
├── simulator/             ESP32 firmware and Wokwi simulation assets
├── data-hub/              Java MQTT ingestion/backpressure/storage service
├── hmi/                   FastAPI backend, React frontend, AI runtime integration
├── ml/                    Offline TDengine -> feature/label/feedback pipeline
├── scripts/               Cross-module ops/debug/demo/stress helper scripts
├── docs/                  Architecture, MQTT contract, deployment docs
├── hardware/              Hardware and enclosure references
├── experiments/           Experiment notes and comparative records
├── runtime/               Local runtime outputs (logs/data, git-ignored)
└── README.md
```

## Quick Start (Local Integration)

1. Start local infrastructure as needed:

```bash
docker compose -f docker-compose.postgresql.yml up -d
docker compose -f docker-compose.tdengine.yml up -d
docker compose -f docker-compose.redis.yml up -d
```

2. Start Data Hub:

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

4. Optional: start standalone AI runtime service:

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

Implemented MQTT topics:

- `edge/temperature/<device_id>/telemetry`
- `edge/temperature/<device_id>/params/set`
- `edge/temperature/<device_id>/params/ack`
- `edgehub/config/alarm-rules/updated`
- `edgehub/config/storage-rules/updated`

Implemented AI decision path:

```text
telemetry/history
-> feature extraction and problem classification
-> PID recommendation
-> preview simulation
-> operator/admin apply
-> MQTT params/set
-> device params/ack
-> post-apply telemetry evaluation
-> feedback sample / model lifecycle data
```

## Documentation Map

- Project profile and defense framing: `docs/project-profile.md`
- Architecture overview: `docs/architecture-overview.md`
- MQTT contract: `docs/mqtt_interface.md`
- Edge firmware + simulator: `simulator/wokwi/README.md`
- Data hub: `data-hub/README.md`
- HMI backend/frontend: `hmi/README.md`
- AI module: `hmi/backend/ai/README.md`
- Offline ML pipeline: `ml/README.md`
- Deployment docs: `docs/deployment/README.md`
- Cross-module script index: `scripts/README.md`

## Notes

- Keep module-specific run commands in module READMEs as the source of truth.
- Root README is an integration index and should reflect current code structure,
  active entrypoints, and real technology choices.
- Do not commit local MQTT credentials, broker passwords, or generated runtime
  data.

Documentation sync date: 2026-05-09.
