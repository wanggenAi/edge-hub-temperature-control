#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT_DIR/runtime/pids"

BACKEND_PID_FILE="$PID_DIR/hmi-backend.pid"
FRONTEND_PID_FILE="$PID_DIR/hmi-frontend.pid"
AI_PID_FILE="$PID_DIR/ai-runtime.pid"
DATAHUB_PID_FILE="$PID_DIR/data-hub.pid"
LIVE_EDGE_PID_FILE="$PID_DIR/defense-live-edge.pid"

WITH_DOCKER_DOWN=0
STATUS_ONLY=0
KEEP_DATAHUB=0
KEEP_LIVE_EDGE=0

usage() {
  cat <<'EOF'
Usage:
  ./scripts/stop-hmi-dev.sh [options]

Options:
  --with-docker-down  Stop HMI middleware docker compose services as well: PostgreSQL, TDengine.
  --keep-datahub      Do not stop a manually started DataHub process.
  --keep-live-edge    Do not stop the local live edge fallback process.
  --status            Show current status only, do not stop.
EOF
}

is_pid_alive() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

print_status() {
  echo "[status]"
  if [[ -f "$AI_PID_FILE" ]] && is_pid_alive "$(cat "$AI_PID_FILE" 2>/dev/null || true)"; then
    echo "  ai-runtime: running pid=$(cat "$AI_PID_FILE")"
  else
    echo "  ai-runtime: stopped"
  fi
  if [[ -f "$BACKEND_PID_FILE" ]] && is_pid_alive "$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"; then
    echo "  backend:    running pid=$(cat "$BACKEND_PID_FILE")"
  else
    echo "  backend:    stopped"
  fi
  if [[ -f "$FRONTEND_PID_FILE" ]] && is_pid_alive "$(cat "$FRONTEND_PID_FILE" 2>/dev/null || true)"; then
    echo "  frontend:   running pid=$(cat "$FRONTEND_PID_FILE")"
  else
    echo "  frontend:   stopped"
  fi
  if [[ -f "$DATAHUB_PID_FILE" ]] && is_pid_alive "$(cat "$DATAHUB_PID_FILE" 2>/dev/null || true)"; then
    echo "  data-hub:   running pid=$(cat "$DATAHUB_PID_FILE")"
  else
    echo "  data-hub:   stopped"
  fi
  if [[ -f "$LIVE_EDGE_PID_FILE" ]] && is_pid_alive "$(cat "$LIVE_EDGE_PID_FILE" 2>/dev/null || true)"; then
    echo "  live-edge:  running pid=$(cat "$LIVE_EDGE_PID_FILE")"
  else
    echo "  live-edge:  stopped"
  fi
}

stop_by_pid_file() {
  local name="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    return
  fi
  local pid
  pid="$(cat "$pid_file" || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    echo "[stop] stopping $name pid=$pid"
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "$pid_file"
}

stop_by_port() {
  local name="$1"
  local port="$2"
  local pids
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "[stop] stopping $name by port $port: $pids"
    kill $pids >/dev/null 2>&1 || true
  fi
}

for arg in "$@"; do
  case "$arg" in
    --with-docker-down) WITH_DOCKER_DOWN=1 ;;
    --keep-datahub) KEEP_DATAHUB=1 ;;
    --keep-live-edge) KEEP_LIVE_EDGE=1 ;;
    --status) STATUS_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  print_status
  exit 0
fi

stop_by_pid_file "ai-runtime" "$AI_PID_FILE"
stop_by_pid_file "backend" "$BACKEND_PID_FILE"
stop_by_pid_file "frontend" "$FRONTEND_PID_FILE"
if [[ "$KEEP_DATAHUB" -eq 1 ]]; then
  echo "[keep] data-hub"
else
  stop_by_pid_file "data-hub" "$DATAHUB_PID_FILE"
fi
if [[ "$KEEP_LIVE_EDGE" -eq 1 ]]; then
  echo "[keep] live-edge"
else
  stop_by_pid_file "live-edge" "$LIVE_EDGE_PID_FILE"
fi

# Fallback in case pid files are stale/missing.
stop_by_port "ai-runtime" "8010"
stop_by_port "backend" "8000"
stop_by_port "frontend" "5173"
if [[ "$KEEP_DATAHUB" -eq 0 ]]; then
  stop_by_port "data-hub" "18080"
  stop_by_port "data-hub-actuator" "8081"
fi

if [[ "$WITH_DOCKER_DOWN" -eq 1 ]]; then
  echo "[stop] stopping HMI middleware docker services..."
  (cd "$ROOT_DIR" && docker compose -f docker-compose.tdengine.yml down)
  (cd "$ROOT_DIR" && docker compose -f docker-compose.postgresql.yml down)
fi

echo "[done] stopped"
