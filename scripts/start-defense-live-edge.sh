#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/hmi/backend"
PID_DIR="$ROOT_DIR/runtime/pids"
LOG_DIR="$ROOT_DIR/runtime/logs/dev"
DAEMONIZE="$ROOT_DIR/scripts/daemonize.py"
PID_FILE="$PID_DIR/defense-live-edge.pid"
LOG_FILE="$LOG_DIR/defense-live-edge.log"

BACKGROUND=0
RESTART=0
STATUS_ONLY=0
STOP_ONLY=0

for arg in "$@"; do
  if [[ "$arg" == "-h" || "$arg" == "--help" ]]; then
    cat <<'EOF'
Usage: ./scripts/start-defense-live-edge.sh [--background] [--restart] [--stop] [--status] [live_thermal_edge_node.py options]

Start the live defense MQTT edge publisher for edge-node-001.
It publishes telemetry to MQTT, listens for params/set, emits params/ack,
and relies on Data Hub to write telemetry/ACK rows into TDengine.

Environment overrides:
  DEFENSE_LIVE_DEVICE_ID      default: edge-node-001
  DEFENSE_LIVE_TARGET_TEMP    default: 37.0
  DEFENSE_LIVE_START_TEMP     default: 36.9
  DEFENSE_LIVE_KP             default: 1.0
  DEFENSE_LIVE_KI             default: 0.02
  DEFENSE_LIVE_KD             default: 0.01
  DEFENSE_LIVE_ENVIRONMENT    default: defense_live
  DEFENSE_LIVE_INTERVAL       default: 1
  DEFENSE_LIVE_LOG_EVERY      default: 15

Common:
  ./scripts/start-defense-live-edge.sh
  DEFENSE_LIVE_TARGET_TEMP=38 ./scripts/start-defense-live-edge.sh
  ./scripts/start-defense-live-edge.sh --restart --background
  ./scripts/start-defense-live-edge.sh --stop

Extra arguments are passed to hmi/backend/scripts/live_thermal_edge_node.py.
EOF
    exit 0
  fi
done

FORWARD_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --background) BACKGROUND=1 ;;
    --restart) RESTART=1 ;;
    --status) STATUS_ONLY=1 ;;
    --stop) STOP_ONLY=1 ;;
    *) FORWARD_ARGS+=("$arg") ;;
  esac
done

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

stop_existing() {
  cleanup_stale_pid_file
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    echo "[defense-live] stopping old live edge pid=$pid"
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
  fi
}

DEVICE_ID="${DEFENSE_LIVE_DEVICE_ID:-edge-node-001}"
TARGET_TEMP="${DEFENSE_LIVE_TARGET_TEMP:-37.0}"
START_TEMP="${DEFENSE_LIVE_START_TEMP:-36.9}"
KP="${DEFENSE_LIVE_KP:-1.4}"
KI="${DEFENSE_LIVE_KI:-0.08}"
KD="${DEFENSE_LIVE_KD:-0.01}"
ENVIRONMENT="${DEFENSE_LIVE_ENVIRONMENT:-defense_live}"
INTERVAL="${DEFENSE_LIVE_INTERVAL:-1}"
LOG_EVERY="${DEFENSE_LIVE_LOG_EVERY:-15}"

mkdir -p "$PID_DIR" "$LOG_DIR"
cleanup_stale_pid_file

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  if [[ -f "$PID_FILE" ]]; then
    echo "[defense-live] running pid=$(cat "$PID_FILE") log=$LOG_FILE"
  else
    echo "[defense-live] stopped"
  fi
  exit 0
fi

if [[ "$STOP_ONLY" -eq 1 ]]; then
  stop_existing
  echo "[defense-live] stopped"
  exit 0
fi

if [[ "$RESTART" -eq 1 ]]; then
  stop_existing
fi

if [[ "$BACKGROUND" -eq 1 && -f "$PID_FILE" ]]; then
  echo "[defense-live] already running pid=$(cat "$PID_FILE") log=$LOG_FILE"
  exit 0
fi

cd "$BACKEND_DIR"

echo "[defense-live] ensuring HMI device row for ${DEVICE_ID}"
./.venv/bin/python scripts/ensure_defense_live_device.py \
  --device-code "$DEVICE_ID" \
  --name "Defense Live MQTT Edge Node" \
  --target-temp "$TARGET_TEMP" \
  --current-temp "$START_TEMP" \
  --kp "$KP" \
  --ki "$KI" \
  --kd "$KD"

echo "[defense-live] starting MQTT live edge publisher"
echo "[defense-live] device=${DEVICE_ID} target=${TARGET_TEMP} start=${START_TEMP} params=(${KP},${KI},${KD})"
if [[ "$BACKGROUND" -eq 1 ]]; then
  echo "[defense-live] background mode log=$LOG_FILE"
else
  echo "[defense-live] this process runs until you press Ctrl+C"
fi

CMD=(
  ./.venv/bin/python scripts/live_thermal_edge_node.py
  --skip-postgres
  --device-id "$DEVICE_ID"
  --environment "$ENVIRONMENT"
  --name "Defense Live MQTT Edge Node"
  --start-temp "$START_TEMP"
  --target-temp "$TARGET_TEMP"
  --kp "$KP"
  --ki "$KI"
  --kd "$KD"
  --control-period-ms 1000
  --interval "$INTERVAL"
  --seconds 0
  --log-every "$LOG_EVERY"
)
if [[ "${#FORWARD_ARGS[@]}" -gt 0 ]]; then
  CMD+=("${FORWARD_ARGS[@]}")
fi

if [[ "$BACKGROUND" -eq 1 ]]; then
  python3 "$DAEMONIZE" --cwd "$BACKEND_DIR" --pid-file "$PID_FILE" --log-file "$LOG_FILE" "${CMD[@]}"
  sleep 2
  cleanup_stale_pid_file
  if [[ -f "$PID_FILE" ]]; then
    echo "[ok] defense live edge running pid=$(cat "$PID_FILE")"
  else
    echo "[fail] defense live edge did not stay running; check $LOG_FILE"
    exit 1
  fi
else
  exec "${CMD[@]}"
fi
