#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/hmi/backend"
FRONTEND_DIR="$ROOT_DIR/hmi/frontend"
PID_DIR="$ROOT_DIR/runtime/pids"
LOG_DIR="$ROOT_DIR/runtime/logs/dev"

AI_PID_FILE="$PID_DIR/ai-runtime.pid"
BACKEND_PID_FILE="$PID_DIR/hmi-backend.pid"
FRONTEND_PID_FILE="$PID_DIR/hmi-frontend.pid"
AI_LOG_FILE="$LOG_DIR/ai-runtime.log"
BACKEND_LOG_FILE="$LOG_DIR/hmi-backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/hmi-frontend.log"

WITH_DOCKER=0
SKIP_INSTALL=0
WITH_AI=1
RESTART=0
STATUS_ONLY=0

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start-hmi-dev.sh [options]

Options:
  --with-docker   Start PostgreSQL via docker compose first.
  --skip-install  Skip pip/npm install steps.
  --without-ai    Do not start standalone AI runtime service.
  --restart       Stop old processes then start fresh.
  --status        Show status only, do not start.
EOF
}

is_pid_alive() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

cleanup_stale_pid_file() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return
  fi
  local pid
  pid="$(cat "$pid_file" || true)"
  if [[ -z "${pid:-}" ]] || ! is_pid_alive "$pid"; then
    rm -f "$pid_file"
  fi
}

wait_http() {
  local url="$1"
  local retries="${2:-30}"
  local delay="${3:-1}"
  local i
  for ((i=1; i<=retries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

print_status() {
  cleanup_stale_pid_file "$AI_PID_FILE"
  cleanup_stale_pid_file "$BACKEND_PID_FILE"
  cleanup_stale_pid_file "$FRONTEND_PID_FILE"

  echo "[status]"
  if [[ -f "$AI_PID_FILE" ]]; then
    echo "  ai-runtime: running pid=$(cat "$AI_PID_FILE")"
  else
    echo "  ai-runtime: stopped"
  fi
  if [[ -f "$BACKEND_PID_FILE" ]]; then
    echo "  backend:    running pid=$(cat "$BACKEND_PID_FILE")"
  else
    echo "  backend:    stopped"
  fi
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    echo "  frontend:   running pid=$(cat "$FRONTEND_PID_FILE")"
  else
    echo "  frontend:   stopped"
  fi

  if curl -fsS "http://127.0.0.1:8010/health" >/dev/null 2>&1; then
    echo "  ai-health:  ok (http://127.0.0.1:8010/health)"
  else
    echo "  ai-health:  down"
  fi
  if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    echo "  api-health: ok (http://127.0.0.1:8000/health)"
  else
    echo "  api-health: down"
  fi
  if curl -fsS "http://127.0.0.1:5173" >/dev/null 2>&1; then
    echo "  web-health: ok (http://127.0.0.1:5173)"
  else
    echo "  web-health: down"
  fi
}

for arg in "$@"; do
  case "$arg" in
    --with-docker) WITH_DOCKER=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    --without-ai) WITH_AI=0 ;;
    --restart) RESTART=1 ;;
    --status) STATUS_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

mkdir -p "$PID_DIR" "$LOG_DIR"

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  print_status
  exit 0
fi

if [[ "$RESTART" -eq 1 ]]; then
  "$ROOT_DIR/scripts/stop-hmi-dev.sh"
fi

if [[ "$WITH_DOCKER" -eq 1 ]]; then
  echo "[start] starting PostgreSQL docker service..."
  (cd "$ROOT_DIR" && docker compose -f docker-compose.postgresql.yml up -d)
fi

if [[ "$WITH_AI" -eq 1 ]]; then
  cleanup_stale_pid_file "$AI_PID_FILE"
  if [[ ! -f "$AI_PID_FILE" ]]; then
    echo "[start] starting ai runtime..."
    if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
      python3 -m venv "$BACKEND_DIR/.venv"
    fi
    if [[ "$SKIP_INSTALL" -eq 0 ]]; then
      "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" >/dev/null
    fi
    (
      cd "$BACKEND_DIR/ai/scripts"
      nohup "$BACKEND_DIR/.venv/bin/python" run_ai_service.py --host 127.0.0.1 --port 8010 \
        >"$AI_LOG_FILE" 2>&1 &
      echo $! >"$AI_PID_FILE"
    )
  else
    echo "[start] ai runtime already running (pid=$(cat "$AI_PID_FILE"))"
  fi
fi

cleanup_stale_pid_file "$BACKEND_PID_FILE"
if [[ ! -f "$BACKEND_PID_FILE" ]]; then
  echo "[start] starting backend..."
  if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
    python3 -m venv "$BACKEND_DIR/.venv"
  fi
  if [[ "$SKIP_INSTALL" -eq 0 ]]; then
    "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" >/dev/null
  fi
  "$BACKEND_DIR/.venv/bin/python" "$BACKEND_DIR/scripts/db_migrate.py"
  "$BACKEND_DIR/.venv/bin/python" "$BACKEND_DIR/scripts/db_seed.py" --rules
  (
    cd "$BACKEND_DIR"
    nohup env \
      AI_RUNTIME_ENABLED="$([[ "$WITH_AI" -eq 1 ]] && echo true || echo false)" \
      AI_RUNTIME_URL="http://127.0.0.1:8010" \
      AI_RUNTIME_FAIL_OPEN="true" \
      OPS_ENABLE_EXTERNAL_METRICS="true" \
      OPS_RUNTIME_METRICS_URL="${OPS_RUNTIME_METRICS_URL:-http://127.0.0.1:8081/actuator/prometheus}" \
      OPS_DATA_HUB_METRICS_URL="${OPS_DATA_HUB_METRICS_URL:-http://127.0.0.1:8081/actuator/prometheus}" \
      OPS_METRICS_TIMEOUT_SECONDS="${OPS_METRICS_TIMEOUT_SECONDS:-2}" \
      "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 \
      >"$BACKEND_LOG_FILE" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
else
  echo "[start] backend already running (pid=$(cat "$BACKEND_PID_FILE"))"
fi

cleanup_stale_pid_file "$FRONTEND_PID_FILE"
if [[ ! -f "$FRONTEND_PID_FILE" ]]; then
  echo "[start] starting frontend..."
  if [[ "$SKIP_INSTALL" -eq 0 ]]; then
    (cd "$FRONTEND_DIR" && npm install >/dev/null)
  fi
  (
    cd "$FRONTEND_DIR"
    nohup npm run dev -- --host 127.0.0.1 --port 5173 \
      >"$FRONTEND_LOG_FILE" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )
else
  echo "[start] frontend already running (pid=$(cat "$FRONTEND_PID_FILE"))"
fi

if [[ "$WITH_AI" -eq 1 ]]; then
  echo "[start] waiting for ai runtime..."
  if wait_http "http://127.0.0.1:8010/health" 45 1; then
    echo "[ok] ai runtime ready: http://127.0.0.1:8010/health"
  else
    echo "[warn] ai runtime not ready yet. check log: $AI_LOG_FILE"
  fi
fi

echo "[start] waiting for backend..."
if wait_http "http://127.0.0.1:8000/health" 45 1; then
  echo "[ok] backend ready: http://127.0.0.1:8000/docs"
else
  echo "[warn] backend not ready yet. check log: $BACKEND_LOG_FILE"
fi

echo "[start] waiting for frontend..."
if wait_http "http://127.0.0.1:5173" 45 1; then
  echo "[ok] frontend ready: http://127.0.0.1:5173"
else
  echo "[warn] frontend not ready yet. check log: $FRONTEND_LOG_FILE"
fi

echo "[done] pids:"
[[ -f "$AI_PID_FILE" ]] && echo "  ai:       $(cat "$AI_PID_FILE")"
[[ -f "$BACKEND_PID_FILE" ]] && echo "  backend:  $(cat "$BACKEND_PID_FILE")"
[[ -f "$FRONTEND_PID_FILE" ]] && echo "  frontend: $(cat "$FRONTEND_PID_FILE")"
