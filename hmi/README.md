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
│   │   │       └── history.py
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

```bash
cd hmi/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: `http://127.0.0.1:8000/docs`

Seed accounts:

- admin / admin123
- operator1 / operator123
- viewer1 / viewer123

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
- History page (summary window list + click-through detail metrics)
- Single device detail page (trend + control-performance panels + gauges + status assessment)
- Alarm acknowledge action (admin/operator)
- AI suggestion apply action (admin/operator)
- Admin user management page (create/edit role/status/delete)
- SQLite with startup seed data

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
- History (summary window + detail)
  - `GET /history/summaries?page=&page_size=&q=&device_id=`
  - `GET /history/summaries/{id}`
