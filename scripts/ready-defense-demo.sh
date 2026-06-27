#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DEFENSE_PYTHON:-$ROOT_DIR/hmi/backend/.venv/bin/python}"
SCENARIO="${DEFENSE_SCENARIO:-all}"
SEED="${DEFENSE_SEED:-20260517}"

cd "$ROOT_DIR"

cat <<'EOF'
[defense-ready] Preparing the defense demo.

This command STARTS:
  - MQTT broker
  - PostgreSQL
  - TDengine
  - HMI backend
  - HMI frontend
  - AI runtime

This command DOES NOT START:
  - DataHub
  - Wokwi / hardware
  - defense live edge publisher
EOF
echo

echo "[1/5] Starting display environment..."
./scripts/start-defense-showcase.sh
echo

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[FAIL] Python runtime not found: $PYTHON_BIN" >&2
  echo "       Try: ./scripts/start-defense-showcase.sh --install" >&2
  exit 1
fi

echo "[2/5] Checking active AI ranking model artifacts..."
"$PYTHON_BIN" scripts/train_defense_ranking_models.py --report
echo

echo "[3/5] Re-seeding DEF controlled demo devices..."
"$PYTHON_BIN" scripts/seed_defense_demo_data.py --reset --scenario "$SCENARIO" --seed "$SEED"
echo

echo "[4/5] Printing short defense report..."
"$PYTHON_BIN" scripts/seed_defense_demo_data.py --report
echo

echo "[5/5] Running preflight checks..."
"$PYTHON_BIN" scripts/preflight-defense-demo.py
echo

cat <<'EOF'
[defense-ready] READY.

Open:
  HMI:          http://127.0.0.1:5173
  Backend docs: http://127.0.0.1:8000/docs

Main devices to show:
  1. edge-node-001  real Wokwi/hardware path, after you manually start DataHub + Wokwi
  2. DEF-108       steady_state_error, core AI diagnosis
  3. DEF-105       post_apply_success, before/preview/actual validation
  4. DEF-106       preview_mismatch, AI honesty
  5. DEF-109       saturation_limited, actuator limit

When you want live edge-node-001:
  ./scripts/start-data-hub-local.sh --restart
  then start Wokwi / hardware yourself
EOF
