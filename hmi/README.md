# Multi-Device Intelligent Temperature Control (HMI)

## Structure

```text
hmi/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── users.py
│   │   │       ├── devices.py
│   │   │       ├── alarms.py
│   │   │       ├── storage_rules.py
│   │   │       ├── history.py
│   │   │       ├── stream.py
│   │   │       └── ai_runtime.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   └── session.py
│   │   ├── models/
│   │   │   └── entities.py
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── device.py
│   │   │   ├── alarm.py
│   │   │   └── history.py
│   │   ├── services/
│   │   │   └── seed.py
│   │   └── main.py
│   ├── ai/
│   │   ├── scripts/
│   │   └── docs/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── routes/
│   │   ├── lib/
│   │   └── types/
│   ├── .env.example
│   ├── package.json
│   ├── tailwind.config.ts
│   └── vite.config.ts
└── README.md
```

## Backend Run

Start PostgreSQL first:

```bash
cd ..
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

Optional: run AI runtime as an independent process (recommended for model lifecycle isolation):

```bash
cd hmi/backend
.venv/bin/python ai/scripts/run_ai_service.py --host 127.0.0.1 --port 8010
```

Then enable remote inference in backend `.env`:

```env
AI_RUNTIME_REMOTE_ENABLED=true
AI_RUNTIME_REMOTE_BASE_URL=http://127.0.0.1:8010
AI_RUNTIME_REMOTE_TIMEOUT_SECONDS=5
AI_RUNTIME_REMOTE_API_KEY=
```

Behavior:

- HMI backend calls AI service first when remote mode is enabled.
- If AI service is unavailable or inference fails, backend automatically falls back to local runtime decision logic.
- Core recommendation flow remains available (no hard dependency on remote service uptime).

API docs: `http://127.0.0.1:8000/docs`

Seed accounts:

- admin / admin123
- operator1 / operator123
- viewer1 / viewer123

## Backend Logging (File + Rotation)

HMI backend now writes logs to both console and rolling files.

Default log directory:

- `runtime/logs/hmi-backend` (relative to repo root)

Default files:

- `app.log` : application logs
- `error.log` : `ERROR` and above
- `access.log` : HTTP access logs (`uvicorn.access`)

Rotation strategy:

- size-based rolling (managed by `loguru`)
- each file rotates at `HMI_LOG_MAX_BYTES` (default `10MB`)
- retain `HMI_LOG_BACKUP_COUNT` files (default `14`)

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

## Frontend Run

```bash
cd hmi/frontend
cp .env.example .env
npm install
npm run dev
```

Frontend: `http://127.0.0.1:5173`

## Implemented Scope

- JWT login + `/auth/me`
- RBAC (`admin`, `operator`, `viewer`)
- Multi-device access control (`user_devices`)
- Device overview page
- Device management page (search + pagination + create + edit + delete)
- Alarm center page (global alarm list, time/level ordered, search)
- Storage rules admin page (global/device scoped raw + summary persistence controls)
- History page (summary window list + click-through detail metrics)
- Single device detail page (trend + control-performance panels + gauges + status assessment)
- Alarm acknowledge action (admin/operator)
- AI suggestion apply action (admin/operator)
- Admin user management page (create/edit role/status/delete)
- PostgreSQL-ready relational backend with Alembic migrations

## TDengine + MQTT Integration

HMI backend uses `DATA_SOURCE_MODE=tdengine` for telemetry/alarm/history reads from TDengine.

To enable end-to-end integration:

1. Configure backend `.env`:

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

2. Keep `data-hub` running with MQTT ingest + TDengine write.

3. Start backend and frontend as usual.

Notes:

- Device detail/history/alarm pages will read from TDengine when enabled.
- Parameter updates from HMI are published to MQTT `params/set` topic.
- PostgreSQL is used for HMI relational control-plane data (auth/rbac/devices/parameters/rules).

## Database Modes (Relational Control Plane)

HMI backend relational/business data (users, rbac, devices, parameters, alarm rules) is managed by SQLAlchemy + Alembic on PostgreSQL.

Telemetry/time-series responsibilities are unchanged:

- TDengine remains the source for telemetry/history/alarm time-series views when enabled.
- Relational DB is for control-plane/business tables.

### Recommended Production `.env`

```env
DATABASE_URL=postgresql+psycopg://edgehub:edgehub@127.0.0.1:5432/edgehub
DATA_SOURCE_MODE=tdengine
TDENGINE_ENABLED=true
RUN_DB_MIGRATIONS_ON_STARTUP=false
SEED_DEFAULT_ALARM_RULES_ON_STARTUP=false
SEED_DEMO_DATA_ON_STARTUP=false
```

## Migrations And Seed

### Install deps

```bash
cd hmi/backend
pip install -r requirements.txt
```

### Run migrations (preferred)

```bash
cd hmi/backend
alembic upgrade head
# or
python scripts/db_migrate.py
```

### Seed default alarm rules only (idempotent)

```bash
cd hmi/backend
python scripts/db_seed.py --rules
```

### Seed demo data (optional, local only)

```bash
cd hmi/backend
python scripts/db_seed.py --rules --demo
```

Notes:

- Startup does not perform runtime schema patching.
- Use Alembic for schema evolution in all environments.
- In production, keep startup migration/seed flags disabled and run migration in deployment pipeline.

## API Snapshot

- Auth
  - `POST /auth/login`
  - `GET /auth/me`
- Users (admin)
  - `GET /users`
  - `POST /users`
  - `PUT /users/{id}`
  - `DELETE /users/{id}`
- Devices
  - `GET /devices` (admin sees all, others only own devices)
  - `GET /devices/manage?page=&page_size=&q=`
  - `GET /devices/{id}`
  - `POST /devices` (new device auto-binds to creator)
  - `PUT /devices/{id}` (admin/operator + access)
  - `DELETE /devices/{id}` (admin/operator + access)
  - `GET /devices/{id}/metrics`
  - `GET /devices/{id}/parameters`
  - `PUT /devices/{id}/parameters`
  - `GET /devices/{id}/alarms`
  - `POST /devices/{id}/alarms/{alarm_id}/ack`
  - `GET /devices/{id}/ai-recommendation`
  - `POST /devices/{id}/ai-recommendation/apply`
- Alarm Center
  - `GET /alarms?page=&page_size=&q=` (latest first, severity assist sort)
  - `GET /alarms/rules`
  - `PUT /alarms/rules/{rule_id}`
- Storage Rules (admin)
  - `GET /storage-rules`
  - `POST /storage-rules`
  - `PUT /storage-rules/{id}`
  - `DELETE /storage-rules/{id}`
- History (summary window + detail)
  - `GET /history/summaries?page=&page_size=&q=&device_id=`
  - `GET /history/summaries/{id}`

Documentation sync date: 2026-04-07.
