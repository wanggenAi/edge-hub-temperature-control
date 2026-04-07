# Standalone AI Runtime Service

## Purpose
Run model inference and candidate ranking in a separate process so HMI API is isolated from model reload/retrain lifecycle.

## Run AI service
```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/run_ai_service.py --host 127.0.0.1 --port 8010
```

## Endpoints
- `GET /health`
- `GET /models/status`
- `POST /models/reload`
- `POST /infer/runtime-decision`

## HMI backend switch
In `hmi/backend/.env`:
- `AI_RUNTIME_REMOTE_ENABLED=true`
- `AI_RUNTIME_REMOTE_BASE_URL=http://127.0.0.1:8010`
- `AI_RUNTIME_REMOTE_TIMEOUT_SECONDS=5`
- `AI_RUNTIME_REMOTE_API_KEY=...` (optional)

When remote inference fails, HMI automatically falls back to local runtime logic, so recommendation flow stays available.
