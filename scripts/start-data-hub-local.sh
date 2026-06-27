#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATAHUB_DIR="$ROOT_DIR/data-hub"
PID_DIR="$ROOT_DIR/runtime/pids"
LOG_DIR="$ROOT_DIR/runtime/logs/dev"
PID_FILE="$PID_DIR/data-hub.pid"
LOG_FILE="$LOG_DIR/data-hub-local-mqtt.log"
DAEMONIZE="$ROOT_DIR/scripts/daemonize.py"
JAR_PATH="$DATAHUB_DIR/build/libs/data-hub-0.1.0-SNAPSHOT.jar"

REBUILD=0
RESTART=0
STATUS_ONLY=0

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start-data-hub-local.sh [options]

Options:
  --build      Build the DataHub boot jar before starting.
  --restart    Stop the existing DataHub process first.
  --status     Show status only.
  -h, --help   Show this help.

This script starts DataHub with java -jar instead of backgrounding Gradle.
That is more stable for the defense demo because the process is detached
from the Gradle wrapper and terminal lifecycle.
EOF
}

is_pid_alive() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

cleanup_stale_pid_file() {
  if [[ ! -f "$PID_FILE" ]]; then
    return
  fi
  local pid
  pid="$(cat "$PID_FILE" || true)"
  if [[ -z "${pid:-}" ]] || ! is_pid_alive "$pid"; then
    rm -f "$PID_FILE"
  fi
}

stop_datahub() {
  cleanup_stale_pid_file
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    echo "[datahub] stopping pid=$pid"
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
  fi

  local pids
  pids="$(lsof -tiTCP:18080 -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "[datahub] stopping stale listener on 18080: $pids"
    kill $pids >/dev/null 2>&1 || true
  fi
}

wait_http() {
  local url="$1"
  local retries="${2:-45}"
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
  cleanup_stale_pid_file
  if [[ -f "$PID_FILE" ]]; then
    echo "[datahub] running pid=$(cat "$PID_FILE")"
  else
    echo "[datahub] stopped"
  fi
  if curl -fsS "http://127.0.0.1:8081/actuator/health" >/dev/null 2>&1; then
    echo "[datahub] health ok: http://127.0.0.1:8081/actuator/health"
  else
    echo "[datahub] health down"
  fi
}

for arg in "$@"; do
  case "$arg" in
    --build) REBUILD=1 ;;
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
  stop_datahub
fi

cleanup_stale_pid_file

if [[ "$REBUILD" -eq 1 || ! -f "$JAR_PATH" ]]; then
  echo "[datahub] building boot jar..."
  (cd "$DATAHUB_DIR" && ./gradlew --no-daemon bootJar)
fi

if [[ -f "$PID_FILE" ]]; then
  echo "[datahub] already running pid=$(cat "$PID_FILE")"
else
  echo "[datahub] starting java -jar DataHub..."
  python3 "$DAEMONIZE" \
    --cwd "$DATAHUB_DIR" \
    --pid-file "$PID_FILE" \
    --log-file "$LOG_FILE" \
    java -jar "$JAR_PATH" --spring.config.additional-location=file:./config/application.properties
fi

if wait_http "http://127.0.0.1:8081/actuator/health" 45 1; then
  echo "[ok] datahub ready: http://127.0.0.1:8081/actuator/health"
else
  echo "[warn] datahub not ready yet. check log: $LOG_FILE"
  exit 1
fi
