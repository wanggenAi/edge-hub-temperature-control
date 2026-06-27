#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/hmi/backend"
FRONTEND_DIR="$ROOT_DIR/hmi/frontend"
PID_DIR="$ROOT_DIR/runtime/pids"
LOG_DIR="$ROOT_DIR/runtime/logs/dev"
DAEMONIZE="$ROOT_DIR/scripts/daemonize.py"
TDENGINE_CFG_FILE="$ROOT_DIR/runtime/tdengine/taos.cfg"
PYTHON_BIN="${HMI_PYTHON:-}"

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
KEEP_DATAHUB=0
KEEP_LIVE_EDGE=0
BACKEND_VENV_RECREATED=0

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start-hmi-dev.sh [options]

Options:
  --with-docker   Start HMI middleware via docker compose first: PostgreSQL, TDengine.
  --skip-install  Skip pip/npm install steps.
  --without-ai    Do not start standalone AI runtime service.
  --restart       Stop old processes then start fresh.
  --keep-datahub  With --restart, keep a manually started DataHub process running.
  --keep-live-edge
                  With --restart, keep the local live edge fallback process running.
  --status        Show status only, do not start.
EOF
}

is_pid_alive() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

detect_python() {
  if [[ -n "$PYTHON_BIN" ]]; then
    if [[ -x "$PYTHON_BIN" ]]; then
      return
    fi
    echo "[error] HMI_PYTHON is not executable: $PYTHON_BIN"
    exit 1
  fi

  local candidate
  local candidates=(
    python3.12
    "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3.12"
    /opt/homebrew/bin/python3.12
    /usr/local/bin/python3.12
    python3.11
    /opt/homebrew/bin/python3.11
    /usr/local/bin/python3.11
    python3.10
    /opt/homebrew/bin/python3.10
    /usr/local/bin/python3.10
    python3
  )
  for candidate in "${candidates[@]}"; do
    if [[ "$candidate" = */* && -x "$candidate" ]]; then
      PYTHON_BIN="$candidate"
      return
    fi
    if [[ "$candidate" != */* ]] && command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      return
    fi
  done

  echo "[error] no python3 executable found"
  exit 1
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

container_status() {
  local container="$1"
  docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$container" 2>/dev/null || echo "missing"
}

wait_container_healthy() {
  local container="$1"
  local retries="${2:-45}"
  local delay="${3:-1}"
  local i
  local status
  for ((i=1; i<=retries; i++)); do
    status="$(container_status "$container")"
    case "$status" in
      running/healthy|running)
        return 0
        ;;
    esac
    sleep "$delay"
  done
  echo "[warn] $container not healthy yet: $(container_status "$container")"
  return 1
}

ensure_tdengine_config() {
  mkdir -p "$ROOT_DIR/runtime/tdengine/data" "$ROOT_DIR/runtime/tdengine/log"
  if [[ -d "$TDENGINE_CFG_FILE" ]]; then
    if rmdir "$TDENGINE_CFG_FILE" >/dev/null 2>&1; then
      :
    else
      echo "[error] $TDENGINE_CFG_FILE is a non-empty directory; TDengine expects a config file there."
      exit 1
    fi
  fi
  if [[ ! -f "$TDENGINE_CFG_FILE" ]]; then
    cat >"$TDENGINE_CFG_FILE" <<'EOF'
fqdn localhost
firstEp localhost:6030
serverPort 6030
timezone UTC
locale en_US.UTF-8
charset UTF-8
logDir /var/log/taos
dataDir /var/lib/taos
EOF
  fi
}

ensure_backend_venv() {
  detect_python
  local python_bin="$BACKEND_DIR/.venv/bin/python"
  local expected_prefix
  local venv_prefix
  expected_prefix="$("$PYTHON_BIN" -c 'import sys; print(sys.base_prefix)')"
  if [[ -d "$BACKEND_DIR/.venv" ]] && ! "$python_bin" -c 'import sys' >/dev/null 2>&1; then
    echo "[warn] backend virtualenv is broken; recreating $BACKEND_DIR/.venv"
    rm -rf "$BACKEND_DIR/.venv"
  fi
  if [[ -d "$BACKEND_DIR/.venv" ]]; then
    venv_prefix="$("$python_bin" -c 'import sys; print(sys.base_prefix)')"
    if [[ "$venv_prefix" != "$expected_prefix" ]]; then
      echo "[warn] backend virtualenv uses $venv_prefix; recreating with $expected_prefix"
      rm -rf "$BACKEND_DIR/.venv"
    fi
  fi
  if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
    "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
    BACKEND_VENV_RECREATED=1
  fi
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
  echo "  postgres:   $(container_status edgehub-postgres)"
  echo "  tdengine:   $(container_status edgehub-tdengine)"
}

for arg in "$@"; do
  case "$arg" in
    --with-docker) WITH_DOCKER=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    --without-ai) WITH_AI=0 ;;
    --restart) RESTART=1 ;;
    --keep-datahub) KEEP_DATAHUB=1 ;;
    --keep-live-edge) KEEP_LIVE_EDGE=1 ;;
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
  STOP_ARGS=()
  if [[ "$KEEP_DATAHUB" -eq 1 ]]; then
    STOP_ARGS+=(--keep-datahub)
  fi
  if [[ "$KEEP_LIVE_EDGE" -eq 1 ]]; then
    STOP_ARGS+=(--keep-live-edge)
  fi
  if [[ "${#STOP_ARGS[@]}" -gt 0 ]]; then
    "$ROOT_DIR/scripts/stop-hmi-dev.sh" "${STOP_ARGS[@]}"
  else
    "$ROOT_DIR/scripts/stop-hmi-dev.sh"
  fi
fi

if [[ "$WITH_DOCKER" -eq 1 ]]; then
  echo "[start] starting HMI middleware docker services..."
  ensure_tdengine_config
  (cd "$ROOT_DIR" && docker compose -f docker-compose.postgresql.yml up -d)
  (cd "$ROOT_DIR" && docker compose -f docker-compose.tdengine.yml up -d)
  wait_container_healthy "edgehub-postgres" 45 1 || true
  wait_container_healthy "edgehub-tdengine" 60 1 || true
fi

if [[ "$WITH_AI" -eq 1 ]]; then
  cleanup_stale_pid_file "$AI_PID_FILE"
  if [[ ! -f "$AI_PID_FILE" ]]; then
    echo "[start] starting ai runtime..."
    ensure_backend_venv
    if [[ "$SKIP_INSTALL" -eq 0 || "$BACKEND_VENV_RECREATED" -eq 1 ]]; then
      "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" >/dev/null
    fi
    "$PYTHON_BIN" "$DAEMONIZE" \
      --cwd "$BACKEND_DIR/ai/scripts" \
      --pid-file "$AI_PID_FILE" \
      --log-file "$AI_LOG_FILE" \
      "$BACKEND_DIR/.venv/bin/python" run_ai_service.py --host 127.0.0.1 --port 8010
  else
    echo "[start] ai runtime already running (pid=$(cat "$AI_PID_FILE"))"
  fi
fi

cleanup_stale_pid_file "$BACKEND_PID_FILE"
if [[ ! -f "$BACKEND_PID_FILE" ]]; then
  echo "[start] starting backend..."
  ensure_backend_venv
  if [[ "$SKIP_INSTALL" -eq 0 || "$BACKEND_VENV_RECREATED" -eq 1 ]]; then
    "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" >/dev/null
  fi
  "$BACKEND_DIR/.venv/bin/python" "$BACKEND_DIR/scripts/db_migrate.py"
  "$BACKEND_DIR/.venv/bin/python" "$BACKEND_DIR/scripts/db_seed.py" --rules
  "$PYTHON_BIN" "$DAEMONIZE" \
    --cwd "$BACKEND_DIR" \
    --pid-file "$BACKEND_PID_FILE" \
    --log-file "$BACKEND_LOG_FILE" \
    env \
    AI_RUNTIME_ENABLED="$([[ "$WITH_AI" -eq 1 ]] && echo true || echo false)" \
    AI_RUNTIME_URL="http://127.0.0.1:8010" \
    AI_RUNTIME_FAIL_OPEN="true" \
    OPS_ENABLE_EXTERNAL_METRICS="true" \
    OPS_RUNTIME_METRICS_URL="${OPS_RUNTIME_METRICS_URL:-http://127.0.0.1:8081/actuator/prometheus}" \
    OPS_DATA_HUB_METRICS_URL="${OPS_DATA_HUB_METRICS_URL:-http://127.0.0.1:8081/actuator/prometheus}" \
    OPS_METRICS_TIMEOUT_SECONDS="${OPS_METRICS_TIMEOUT_SECONDS:-2}" \
    "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000
else
  echo "[start] backend already running (pid=$(cat "$BACKEND_PID_FILE"))"
fi

cleanup_stale_pid_file "$FRONTEND_PID_FILE"
if [[ ! -f "$FRONTEND_PID_FILE" ]]; then
  echo "[start] starting frontend..."
  if [[ "$SKIP_INSTALL" -eq 0 ]]; then
    (cd "$FRONTEND_DIR" && npm install >/dev/null)
  fi
  detect_python
  "$PYTHON_BIN" "$DAEMONIZE" \
    --cwd "$FRONTEND_DIR" \
    --pid-file "$FRONTEND_PID_FILE" \
    --log-file "$FRONTEND_LOG_FILE" \
    npm run dev -- --host 127.0.0.1 --port 5173
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
