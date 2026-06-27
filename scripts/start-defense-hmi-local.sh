#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start-defense-hmi-local.sh [options]

Start only the local MQTT broker and HMI services for defense day.
This script does not start DataHub and does not start Wokwi.

Options:
  --restart       Restart HMI backend/frontend. Broker is kept/recreated by Docker.
  --skip-install  Skip pip/npm install steps.
  --with-ai       Start AI runtime together with HMI.
  --status        Show broker/HMI status only.
  -h, --help      Show this help.

Typical:
  ./scripts/start-defense-hmi-local.sh --restart --skip-install

Then start manually when needed:
  ./scripts/start-data-hub-local.sh --restart
  Start Wokwi from VS Code, then run ./scripts/check-live-mqtt-edge.sh
EOF
}

RESTART=0
SKIP_INSTALL=0
WITH_AI=0
STATUS_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --restart) RESTART=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    --with-ai) WITH_AI=1 ;;
    --status) STATUS_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

cd "$ROOT_DIR"

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  docker compose -f docker-compose.mqtt.yml ps
  ./scripts/start-hmi-dev.sh --status
  exit 0
fi

echo "[defense-hmi] starting local MQTT broker only..."
./scripts/use-local-mqtt.sh --no-rebuild-wokwi

HMI_ARGS=(--without-ai)
if [[ "$WITH_AI" -eq 1 ]]; then
  HMI_ARGS=()
fi
if [[ "$RESTART" -eq 1 ]]; then
  HMI_ARGS+=(--restart)
  HMI_ARGS+=(--keep-datahub --keep-live-edge)
fi
if [[ "$SKIP_INSTALL" -eq 1 ]]; then
  HMI_ARGS+=(--skip-install)
fi

echo "[defense-hmi] starting HMI backend/frontend only..."
./scripts/start-hmi-dev.sh "${HMI_ARGS[@]}"

echo
echo "[defense-hmi] ready."
echo "  HMI:          http://127.0.0.1:5173"
echo "  Backend docs: http://127.0.0.1:8000/docs"
echo "  MQTT broker:  127.0.0.1:1883"
echo
echo "Manual next steps if you want live Wokwi:"
echo "  ./scripts/start-data-hub-local.sh --restart"
echo "  Start Wokwi in VS Code"
echo "  ./scripts/check-live-mqtt-edge.sh"
