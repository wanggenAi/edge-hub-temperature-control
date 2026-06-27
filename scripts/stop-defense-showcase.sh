#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/stop-defense-showcase.sh [options]

Stop the defense display stack:
  - HMI frontend
  - HMI backend
  - AI runtime
  - PostgreSQL
  - TDengine
  - local MQTT broker

This script intentionally keeps:
  - DataHub, if you started it manually
  - Wokwi / hardware layer

It also stops the defense live edge publisher if it exists, because that
publisher is not part of the standard live hardware defense path.

Options:
  --status       Show current status only.
  --keep-mqtt    Keep the local MQTT broker running.
  --keep-docker  Keep PostgreSQL and TDengine running.
  -h, --help     Show this help.

Typical:
  ./scripts/stop-defense-showcase.sh
EOF
}

STATUS_ONLY=0
KEEP_MQTT=0
KEEP_DOCKER=0

for arg in "$@"; do
  case "$arg" in
    --status) STATUS_ONLY=1 ;;
    --keep-mqtt) KEEP_MQTT=1 ;;
    --keep-docker) KEEP_DOCKER=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

cd "$ROOT_DIR"

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  ./scripts/start-defense-showcase.sh --status
  exit 0
fi

echo "[defense-showcase] stopping HMI frontend/backend, AI runtime, and live edge fallback..."
STOP_ARGS=(--keep-datahub)
if [[ "$KEEP_DOCKER" -eq 0 ]]; then
  STOP_ARGS+=(--with-docker-down)
fi
./scripts/stop-hmi-dev.sh "${STOP_ARGS[@]}"

if [[ "$KEEP_MQTT" -eq 0 ]]; then
  echo "[defense-showcase] stopping local MQTT broker..."
  docker compose -f docker-compose.mqtt.yml down
else
  echo "[defense-showcase] keeping local MQTT broker"
fi

echo
echo "[defense-showcase] stopped."
echo "  kept: DataHub, Wokwi/hardware"
if [[ "$KEEP_MQTT" -eq 0 ]]; then
  echo "  stopped: MQTT broker"
fi
if [[ "$KEEP_DOCKER" -eq 0 ]]; then
  echo "  stopped: PostgreSQL, TDengine"
fi
