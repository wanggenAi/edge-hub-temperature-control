# HMI Layer

This directory contains the independent HMI layer for the EdgeHub temperature-control project.

It is intentionally separate from the Java `data-hub` module.

## Scope

This MVP HMI is designed for thesis defense and system demonstration. It focuses on:

- login and role separation
- system overview for defense entry
- realtime monitoring
- history analysis
- parameter submission and params/ack feedback
- AI recommendation placeholder

## Structure

- `backend/`: FastAPI service for authentication, page-oriented aggregation, and parameter interactions
- `frontend/`: Vue portal-style interface for the HMI pages

## Demo Accounts

- operator: `operator / operator123`
- viewer: `viewer / viewer123`

## Planned Data Boundary

- realtime page data: realtime link
- history page data: TDengine historical query path
- overview page data: FastAPI aggregation
- AI page data: reserved AI recommendation interface

## Run

Backend:

```bash
cd hmi/backend
../../.venv/bin/pip install -r requirements.txt
../../.venv/bin/uvicorn app.main:app --reload
```

Frontend:

```bash
cd hmi/frontend
npm install
npm run dev
```

Default frontend API base URL:

- `http://127.0.0.1:8000/api`
