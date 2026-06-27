#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DEFENSE_PYTHON:-$ROOT_DIR/hmi/backend/.venv/bin/python}"

cd "$ROOT_DIR"

SCENARIO="${DEFENSE_SCENARIO:-all}"
SEED="${DEFENSE_SEED:-20260517}"

echo "[defense] preparing controlled defense demo data"
echo "[defense] root: $ROOT_DIR"
echo "[defense] scenario: $SCENARIO"
echo "[defense] seed: $SEED"
echo "[defense] python: $PYTHON_BIN"
echo

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[FAIL] Python runtime not found: $PYTHON_BIN"
  echo "       Start HMI once with ./scripts/start-hmi-dev.sh, or set DEFENSE_PYTHON=/path/to/python."
  exit 1
fi

if [[ "${DEFENSE_WITH_LOCAL_MQTT:-1}" == "1" ]]; then
  echo "[0/5] Ensuring local MQTT broker configuration..."
  ./scripts/use-local-mqtt.sh --no-rebuild-wokwi
  ./scripts/start-data-hub-local.sh --build --restart
  echo
else
  echo "[0/5] Skipping local MQTT setup because DEFENSE_WITH_LOCAL_MQTT=0"
  echo
fi

echo "[1/5] Checking active ranking model artifacts..."
"$PYTHON_BIN" scripts/train_defense_ranking_models.py --report
echo

echo "[2/5] Re-seeding DEF demo dataset..."
"$PYTHON_BIN" scripts/seed_defense_demo_data.py --reset --scenario "$SCENARIO" --seed "$SEED"
echo

echo "[3/5] Printing defense demo report..."
"$PYTHON_BIN" scripts/seed_defense_demo_data.py --report
echo

echo "[4/5] Running defense preflight..."
"$PYTHON_BIN" scripts/preflight-defense-demo.py
echo

echo "[5/5] Live MQTT note..."
echo "  Wokwi live closed-loop check:"
echo "  Start Wokwi Simulator from VS Code"
echo "  ./scripts/check-live-mqtt-edge.sh"
echo "  Expected path: HMI/backend params_set -> DataHub -> Wokwi params/ack -> TDengine telemetry -> HMI curve."
echo

echo "[defense] ready."
echo "[defense] HMI: http://127.0.0.1:5173"
echo "[defense] Backend docs: http://127.0.0.1:8000/docs"
