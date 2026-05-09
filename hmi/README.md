# Multi-Device Intelligent Temperature Control (HMI)

The HMI module is the operator-facing control plane for EdgeHub. It is not only
a dashboard: it manages users/devices/rules, reads telemetry and history,
publishes parameter updates through MQTT, and exposes the AI recommendation,
preview, apply, ACK, and post-apply validation workflow.

## Structure

```text
hmi/
├── backend/               FastAPI backend, SQLAlchemy models, API routes, services
│   ├── app/
│   ├── ai/                Standalone AI runtime scripts and AI docs
│   ├── scripts/           DB migration/seed and feedback worker scripts
│   ├── .env.example
│   └── requirements.txt
├── frontend/              React + TypeScript + Vite frontend
│   ├── src/
│   ├── .env.example
│   └── package.json
└── README.md
```

## Backend Run

Start PostgreSQL first from the repository root:

```bash
docker compose -f docker-compose.postgresql.yml up -d
```

Then run backend:

```bash
cd hmi/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/db_migrate.py
python scripts/db_seed.py --rules
uvicorn app.main:app --reload
```

API docs:

- `http://127.0.0.1:8000/docs`

## Frontend Run

```bash
cd hmi/frontend
cp .env.example .env
npm install
npm run dev
```

Frontend:

- `http://127.0.0.1:5173`

## Optional AI Runtime Service

The backend can call a standalone AI runtime service and safely fall back to the
local backend AI logic when that runtime is unavailable.

```bash
cd hmi/backend
.venv/bin/python ai/scripts/run_ai_service.py --host 127.0.0.1 --port 8010
```

Relevant settings:

```env
AI_RUNTIME_ENABLED=true
AI_RUNTIME_URL=http://127.0.0.1:8010
AI_RUNTIME_TIMEOUT_SECONDS=2
```

## Implemented Scope

Control-plane and user features:

- JWT login + `/auth/me`
- RBAC (`admin`, `operator`, `viewer`)
- multi-device access control (`user_devices`)
- device overview and single-device detail pages
- device management page with search, pagination, create, edit, and delete
- alarm center and alarm acknowledge action
- storage rules administration
- history summary/detail views
- admin user management
- PostgreSQL-ready relational backend with Alembic migrations

AI and closed-loop decision features:

- AI recommendation generation from device telemetry/context
- AI recommendation history and state tracking
- preview simulation before applying a recommendation
- AI recommendation apply through MQTT `params/set`
- ACK-aware apply path using device `params/ack`
- actual post-apply effect evaluation from telemetry
- baseline / preview / actual telemetry comparison for defense demos
- unified control-action feedback samples for later model training

Operations features:

- Data Hub / MQTT ingest health
- runtime metrics and log-derived trends
- learning-loop health
- model lifecycle and active/candidate artifact visibility
- AI observability endpoint for runtime source, fallback, ranking, and quality
  signals

Seed accounts:

- `admin` / `admin123`
- `operator1` / `operator123`
- `viewer1` / `viewer123`

## TDengine + MQTT Integration

HMI backend uses `DATA_SOURCE_MODE=tdengine` for telemetry, alarm, and history
reads from TDengine.

Example backend `.env` values:

```env
DATA_SOURCE_MODE=tdengine
TDENGINE_ENABLED=true
TDENGINE_URL=http://127.0.0.1:6041
TDENGINE_DATABASE=edgehub
TDENGINE_USERNAME=root
TDENGINE_PASSWORD=taosdata

MQTT_PUBLISH_ENABLED=true
MQTT_BROKER_HOST=127.0.0.1
MQTT_BROKER_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_PARAMS_SET_TOPIC_TEMPLATE=edge/temperature/{device_id}/params/set
MQTT_PUBLISH_QOS=1
```

Integration notes:

- Device detail, history, and alarm pages read from TDengine when enabled.
- Parameter updates and AI recommendation apply actions publish to MQTT
  `params/set`.
- The backend waits for compatible `params/ack` records for ACK-aware apply
  confirmation.
- PostgreSQL stores relational control-plane data such as auth, RBAC, devices,
  parameters, recommendations, control actions, rules, and model lifecycle data.
- TDengine stores telemetry/time-series facts such as telemetry, summaries,
  `params_set`, `params_ack`, alarms, and device status.

## Developer Ops Console (Admin)

Frontend route:

- `/ops`

Backend endpoints:

- `GET /ops/overview`
- `GET /ops/data-hub`
- `GET /ops/runtime`
- `GET /ops/learning-loop`
- `GET /ops/models`
- `GET /ops/ai/observability`
- `GET /ops/ai/model-lifecycle/status`
- `GET /ops/ai/model-lifecycle/runs`
- `POST /ops/ai/model-lifecycle/run`

Data Hub key metrics are sourced from real `datahub.stats` log groups, including
`mqtt[...]`, `accounting[...]`, `outcome_delta[...]`, `tdengine[...]`,
`buffer[...]`, and `delta[...]`.

Optional lightweight external metrics integration:

```env
OPS_ENABLE_EXTERNAL_METRICS=true
OPS_RUNTIME_METRICS_URL=http://127.0.0.1:8081/actuator/prometheus
OPS_DATA_HUB_METRICS_URL=http://127.0.0.1:8081/actuator/prometheus
OPS_METRICS_TIMEOUT_SECONDS=2
```

If the external endpoint is unavailable, Ops Console keeps using local process
and log-derived metrics as a safe fallback.

## Backend Logging

HMI backend writes logs to both console and rolling files.

Default log directory:

- `runtime/logs/hmi-backend` relative to repository root

Default files:

- `app.log`: application logs
- `error.log`: `ERROR` and above
- `access.log`: HTTP access logs (`uvicorn.access`)

Example `.env` overrides:

```env
HMI_LOG_LEVEL=INFO
HMI_CONSOLE_LOG_LEVEL=INFO
HMI_ACCESS_LOG_LEVEL=INFO
HMI_LOG_DIR=../../runtime/logs/hmi-backend
HMI_LOG_MAX_BYTES=10485760
HMI_LOG_BACKUP_COUNT=14
HMI_LOG_FILE_NAME=app.log
HMI_ERROR_LOG_FILE_NAME=error.log
HMI_ACCESS_LOG_FILE_NAME=access.log
```

## Database Modes

HMI backend relational/business data is managed by SQLAlchemy + Alembic on
PostgreSQL.

Recommended production-style `.env` values:

```env
DATABASE_URL=postgresql+psycopg://edgehub:edgehub@127.0.0.1:5432/edgehub
DATA_SOURCE_MODE=tdengine
TDENGINE_ENABLED=true
RUN_DB_MIGRATIONS_ON_STARTUP=false
SEED_DEFAULT_ALARM_RULES_ON_STARTUP=false
SEED_DEMO_DATA_ON_STARTUP=false
```

## Migrations And Seed

Install dependencies:

```bash
cd hmi/backend
pip install -r requirements.txt
```

Run migrations:

```bash
cd hmi/backend
alembic upgrade head
# or
python scripts/db_migrate.py
```

Seed default alarm rules:

```bash
cd hmi/backend
python scripts/db_seed.py --rules
```

Seed local demo data:

```bash
cd hmi/backend
python scripts/db_seed.py --rules --demo
```

Seed AI preview demo devices:

```bash
cd hmi/backend
python scripts/db_seed.py --preview-ai-demo
```

Created/refreshed AI demo devices:

- `TC-PREVIEW-SAT-SLOW`: `saturation_limited` + `slow_response`
- `TC-PREVIEW-OSC-OVS`: `oscillation` + `overshoot_high`
- `TC-PREVIEW-SSE`: `steady_state_error`
- `TC-PREVIEW-NORMAL`: near-normal baseline

## Unified Control-Action Feedback Worker

```bash
cd hmi/backend
python scripts/run_control_action_feedback_worker.py --batch-size 50
```

This evaluates pending control actions, including AI apply and manual apply, and
writes structured feedback samples.

Recommended scheduling:

- run externally every `10` minutes by cron, systemd timer, or K8s CronJob
- keep it as one-shot batch execution instead of a tight internal polling loop

## API Snapshot

Auth and users:

- `POST /auth/login`
- `GET /auth/me`
- `GET /users`
- `POST /users`
- `PUT /users/{id}`
- `DELETE /users/{id}`

Devices and control:

- `GET /devices`
- `GET /devices/manage?page=&page_size=&q=`
- `GET /devices/{id}`
- `POST /devices`
- `PUT /devices/{id}`
- `DELETE /devices/{id}`
- `GET /devices/{id}/metrics`
- `GET /devices/{id}/parameters`
- `PUT /devices/{id}/parameters`
- `GET /devices/{id}/alarms`
- `POST /devices/{id}/alarms/{alarm_id}/ack`

AI recommendation workflow:

- `GET /devices/{id}/ai-recommendation`
- `POST /devices/{id}/ai-recommendation/generate`
- `POST /devices/{id}/ai-recommendation/preview`
- `POST /devices/{id}/ai-recommendation/apply`
- `POST /devices/{id}/ai-recommendation/{recommendation_id}/evaluate-actual`
- `GET /devices/{id}/ai-recommendation/{recommendation_id}/telemetry-comparison`
- `GET /devices/ai/recommendations/history`

Alarms, rules, and history:

- `GET /alarms?page=&page_size=&q=`
- `GET /alarms/rules`
- `PUT /alarms/rules/{rule_id}`
- `GET /storage-rules`
- `POST /storage-rules`
- `PUT /storage-rules/{id}`
- `DELETE /storage-rules/{id}`
- `GET /history/summaries?page=&page_size=&q=&device_id=`
- `GET /history/summaries/{id}`

Documentation sync date: 2026-05-09.
