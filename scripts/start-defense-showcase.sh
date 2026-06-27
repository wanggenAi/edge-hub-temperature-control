#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start-defense-showcase.sh [options]

Start the defense display stack quickly:
  - local MQTT broker
  - PostgreSQL
  - TDengine
  - HMI backend
  - HMI frontend
  - AI runtime

This script intentionally does NOT start:
  - DataHub
  - Wokwi / hardware layer
  - defense live edge publisher

Options:
  --status      Show current status only.
  --no-restart  Keep existing HMI processes if they are already running.
  --install     Run pip/npm install steps instead of the fast skip-install path.
  --without-ai  Start HMI without the standalone AI runtime.
  -h, --help    Show this help.

Typical defense-day command:
  ./scripts/start-defense-showcase.sh

After this, start manually when you need the live hardware path:
  ./scripts/start-data-hub-local.sh --restart
  Start Wokwi / hardware
  ./scripts/check-live-mqtt-edge.sh
EOF
}

STATUS_ONLY=0
RESTART=1
SKIP_INSTALL=1
WITH_AI=1

for arg in "$@"; do
  case "$arg" in
    --status) STATUS_ONLY=1 ;;
    --no-restart) RESTART=0 ;;
    --install) SKIP_INSTALL=0 ;;
    --without-ai) WITH_AI=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

cd "$ROOT_DIR"

if [[ "$STATUS_ONLY" -eq 1 ]]; then
  echo "[defense-showcase] docker middleware"
  docker compose -f docker-compose.mqtt.yml ps
  docker compose -f docker-compose.postgresql.yml ps
  docker compose -f docker-compose.tdengine.yml ps
  ./scripts/start-hmi-dev.sh --status
  ./scripts/start-defense-live-edge.sh --status || true
  exit 0
fi

echo "[defense-showcase] contract:"
echo "  start: MQTT, PostgreSQL, TDengine, HMI backend/frontend, AI runtime"
echo "  skip:  DataHub, Wokwi/hardware, defense live edge publisher"
echo

echo "[defense-showcase] stopping defense live edge publisher if it exists..."
./scripts/start-defense-live-edge.sh --stop || true

echo "[defense-showcase] starting local MQTT broker and keeping local MQTT config..."
./scripts/use-local-mqtt.sh --no-rebuild-wokwi

HMI_ARGS=(--with-docker --keep-datahub)
if [[ "$RESTART" -eq 1 ]]; then
  HMI_ARGS+=(--restart)
fi
if [[ "$SKIP_INSTALL" -eq 1 ]]; then
  HMI_ARGS+=(--skip-install)
fi
if [[ "$WITH_AI" -eq 0 ]]; then
  HMI_ARGS+=(--without-ai)
fi

echo "[defense-showcase] starting HMI display stack..."
./scripts/start-hmi-dev.sh "${HMI_ARGS[@]}"

echo
echo "[defense-showcase] ready."
echo "  HMI:          http://127.0.0.1:5173"
echo "  Backend docs: http://127.0.0.1:8000/docs"
echo "  AI runtime:   http://127.0.0.1:8010/health"
echo "  MQTT broker:  127.0.0.1:1883"
echo "  PostgreSQL:   127.0.0.1:5432"
echo "  TDengine:     127.0.0.1:6041"
echo
echo "[defense-showcase] not started: DataHub, Wokwi/hardware, defense live edge publisher."
