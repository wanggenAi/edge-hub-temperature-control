#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/hmi/backend/.venv/bin/python}"
DEVICE_ID="${DEVICE_ID:-edge-node-001}"
BROKER_HOST="${BROKER_HOST:-127.0.0.1}"
BROKER_PORT="${BROKER_PORT:-1883}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-25}"
TARGET_TEMP="${TARGET_TEMP:-auto}"
RESTORE_TARGET="${RESTORE_TARGET:-auto}"
KP="${KP:-120}"
KI="${KI:-12}"
KD="${KD:-0}"
CONTROL_MODE="${CONTROL_MODE:-pid_control}"

cat <<EOF
[live-check] verifying MQTT edge closed loop
  device:      $DEVICE_ID
  broker:      $BROKER_HOST:$BROKER_PORT
  target:      $TARGET_TEMP
  restore:     $RESTORE_TARGET
  params:      kp=$KP ki=$KI kd=$KD mode=$CONTROL_MODE
  timeout:     ${TIMEOUT_SECONDS}s
EOF

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[fail] python not found or not executable: $PYTHON_BIN" >&2
  exit 2
fi

ROOT_DIR="$ROOT_DIR" \
DEVICE_ID="$DEVICE_ID" \
BROKER_HOST="$BROKER_HOST" \
BROKER_PORT="$BROKER_PORT" \
TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
TARGET_TEMP="$TARGET_TEMP" \
RESTORE_TARGET="$RESTORE_TARGET" \
KP="$KP" \
KI="$KI" \
KD="$KD" \
CONTROL_MODE="$CONTROL_MODE" \
"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paho.mqtt import client as mqtt

root = Path(os.environ.get("ROOT_DIR", ".")).resolve()
backend_root = root / "hmi" / "backend"
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.core.config import settings  # noqa: E402
from app.services.tdengine_client import TdengineClient  # noqa: E402


@dataclass
class Seen:
    telemetry: dict[str, Any] | None = None
    ack: dict[str, Any] | None = None
    set_payload: dict[str, Any] | None = None


device_id = os.environ.get("DEVICE_ID", "edge-node-001")
host = os.environ.get("BROKER_HOST", "127.0.0.1")
port = int(os.environ.get("BROKER_PORT", "1883"))
timeout_s = float(os.environ.get("TIMEOUT_SECONDS", "25"))
target_raw = os.environ.get("TARGET_TEMP", "auto").strip()
restore_target_raw = os.environ.get("RESTORE_TARGET", "auto")
kp = float(os.environ.get("KP", "120"))
ki = float(os.environ.get("KI", "12"))
kd = float(os.environ.get("KD", "0"))
control_mode = os.environ.get("CONTROL_MODE", "pid_control")
set_topic = f"edge/temperature/{device_id}/params/set"
ack_topic = f"edge/temperature/{device_id}/params/ack"
telemetry_topic = f"edge/temperature/{device_id}/telemetry"
seen = Seen()


def decode(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8", "replace"))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def matches_target(value: Any, expected: float, tol: float = 0.05) -> bool:
    try:
        return abs(float(value) - expected) <= tol
    except (TypeError, ValueError):
        return False


def on_connect(client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any = None) -> None:
    print(f"[mqtt] connected rc={reason_code}")
    client.subscribe(telemetry_topic, qos=0)
    client.subscribe(ack_topic, qos=0)


def on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
    payload = decode(msg.payload)
    if msg.topic == telemetry_topic:
        seen.telemetry = payload
    elif msg.topic == ack_topic:
        seen.ack = payload


client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"edgehub-live-check-{int(time.time())}",
    protocol=mqtt.MQTTv311,
)
client.on_connect = on_connect
client.on_message = on_message
client.connect(host, port, keepalive=20)
client.loop_start()

deadline = time.monotonic() + timeout_s
while time.monotonic() < deadline and seen.telemetry is None:
    time.sleep(0.2)

if seen.telemetry is None:
    client.loop_stop()
    client.disconnect()
    raise SystemExit("[fail] no live telemetry received. Check Wokwi is running and connected to local broker.")

print(
    "[ok] live telemetry "
    f"target={seen.telemetry.get('target_temp_c')} "
    f"sensor={seen.telemetry.get('sensor_temp_c')} "
    f"kp={seen.telemetry.get('kp')} ki={seen.telemetry.get('ki')} kd={seen.telemetry.get('kd')}"
)
initial_target = seen.telemetry.get("target_temp_c")
if target_raw.lower() == "auto":
    target = float(initial_target) + 1.0
else:
    target = float(target_raw)
if restore_target_raw.strip().lower() == "auto":
    restore_target = float(initial_target)
elif restore_target_raw.strip().lower() in {"none", "off", "false", "0"}:
    restore_target = None
else:
    restore_target = float(restore_target_raw)

payload = {
    "target_temp_c": target,
    "kp": kp,
    "ki": ki,
    "kd": kd,
    "control_mode": control_mode,
    "control_period_ms": 1000,
    "apply_immediately": True,
    "source": "live_check",
    "requested_at": datetime.now(tz=timezone.utc).isoformat(),
}
seen.set_payload = payload
print(f"[mqtt] publishing params/set {set_topic}: {json.dumps(payload, separators=(',', ':'))}")
info = client.publish(set_topic, json.dumps(payload, separators=(",", ":")), qos=0, retain=False)
info.wait_for_publish(timeout=3)
if not info.is_published():
    client.loop_stop()
    client.disconnect()
    raise SystemExit("[fail] params/set publish timeout")

while time.monotonic() < deadline:
    if seen.ack and seen.ack.get("success") is True and matches_target(seen.ack.get("target_temp_c"), target):
        print(
            "[ok] params/ack "
            f"ack_type={seen.ack.get('ack_type')} reason={seen.ack.get('reason')} "
            f"target={seen.ack.get('target_temp_c')} kp={seen.ack.get('kp')} ki={seen.ack.get('ki')} kd={seen.ack.get('kd')}"
        )
        break
    time.sleep(0.2)
else:
    client.loop_stop()
    client.disconnect()
    raise SystemExit(f"[fail] no successful matching params/ack; latest_ack={seen.ack}")

while time.monotonic() < deadline:
    if seen.telemetry and matches_target(seen.telemetry.get("target_temp_c"), target):
        print(
            "[ok] telemetry reflects applied target "
            f"target={seen.telemetry.get('target_temp_c')} sensor={seen.telemetry.get('sensor_temp_c')}"
        )
        break
    time.sleep(0.2)
else:
    client.loop_stop()
    client.disconnect()
    raise SystemExit(f"[fail] telemetry did not reflect target={target}; latest={seen.telemetry}")

if restore_target is not None and not matches_target(restore_target, target):
    seen.ack = None
    restore_payload = {
        "target_temp_c": restore_target,
        "kp": kp,
        "ki": ki,
        "kd": kd,
        "control_mode": control_mode,
        "control_period_ms": 1000,
        "apply_immediately": True,
        "source": "live_check_restore",
        "requested_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    print(
        "[mqtt] restoring params/set "
        f"{set_topic}: {json.dumps(restore_payload, separators=(',', ':'))}"
    )
    restore_info = client.publish(set_topic, json.dumps(restore_payload, separators=(",", ":")), qos=0, retain=False)
    restore_info.wait_for_publish(timeout=3)
    if not restore_info.is_published():
        client.loop_stop()
        client.disconnect()
        raise SystemExit("[fail] restore params/set publish timeout")
    restore_deadline = time.monotonic() + timeout_s
    while time.monotonic() < restore_deadline:
        if seen.ack and seen.ack.get("success") is True and matches_target(seen.ack.get("target_temp_c"), restore_target):
            print(
                "[ok] restore params/ack "
                f"ack_type={seen.ack.get('ack_type')} reason={seen.ack.get('reason')} "
                f"target={seen.ack.get('target_temp_c')}"
            )
            break
        time.sleep(0.2)
    else:
        client.loop_stop()
        client.disconnect()
        raise SystemExit(f"[fail] no successful restore params/ack; latest_ack={seen.ack}")
    while time.monotonic() < restore_deadline:
        if seen.telemetry and matches_target(seen.telemetry.get("target_temp_c"), restore_target):
            print(
                "[ok] telemetry restored "
                f"target={seen.telemetry.get('target_temp_c')} sensor={seen.telemetry.get('sensor_temp_c')}"
            )
            break
        time.sleep(0.2)
    else:
        client.loop_stop()
        client.disconnect()
        raise SystemExit(f"[fail] telemetry did not restore target={restore_target}; latest={seen.telemetry}")

client.loop_stop()
client.disconnect()

td = TdengineClient()
device_sql = "'" + device_id.replace("'", "''") + "'"
for label, table, predicate in [
    ("telemetry", "telemetry", f"target_temp_c >= {target - 0.05} AND target_temp_c <= {target + 0.05}"),
    ("params_set", "params_set", f"target_temp_c >= {target - 0.05} AND target_temp_c <= {target + 0.05}"),
    ("params_ack", "params_ack", f"success = true AND target_temp_c >= {target - 0.05} AND target_temp_c <= {target + 0.05}"),
]:
    sql = (
        f"SELECT COUNT(*) AS n FROM {settings.tdengine_database}.{table} "
        f"WHERE device_id={device_sql} AND ts > now - 2m AND {predicate}"
    )
    result = td.query(sql)
    row = td.row_to_dict(result.columns, result.rows[0]) if result.rows else {"n": 0}
    print(f"[tdengine] recent {label} matching target={target}: {row.get('n', 0)}")

print("[pass] live MQTT target update + ACK path is working")
PY
