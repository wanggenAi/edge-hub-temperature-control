#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ENV="$ROOT_DIR/hmi/backend/.env"
DATAHUB_CONFIG="$ROOT_DIR/data-hub/config/application.properties"
WOKWI_SECRETS="$ROOT_DIR/simulator/wokwi/src/secrets.h"

MODE="apply"
REBUILD_WOKWI=1

usage() {
  cat <<'EOF'
Usage:
  ./scripts/use-local-mqtt.sh [options]

Options:
  --check-only        Print current MQTT config and probe local broker.
  --no-rebuild-wokwi Do not rebuild the Wokwi firmware after changing secrets.h.
  -h, --help         Show this help.

What this does:
  - starts local Docker Mosquitto on 127.0.0.1:1883
  - points HMI backend and DataHub to 127.0.0.1:1883
  - points Wokwi firmware to host.wokwi.internal:1883
  - keeps broker auth empty for local-only defense stability
  - does not change MQTT QoS or ACK semantics

Why Wokwi differs:
  In Wokwi, 127.0.0.1 means the simulated ESP32 side, not your Mac.
  host.wokwi.internal routes from Wokwi to services running on your Mac.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --check-only) MODE="check" ;;
    --no-rebuild-wokwi) REBUILD_WOKWI=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

ensure_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "[fail] required file missing: $path" >&2
    exit 1
  fi
}

replace_or_append() {
  local path="$1"
  local key="$2"
  local value="$3"
  if grep -q "^${key}=" "$path"; then
    perl -0pi -e "s|^\\Q${key}\\E=.*$|${key}=${value}|m" "$path"
  else
    printf '\n%s=%s\n' "$key" "$value" >>"$path"
  fi
}

replace_cpp_secret() {
  local name="$1"
  local value="$2"
  perl -0pi -e "s|${name}\\[\\]\\s*=\\s*\"[^\"]*\"|${name}[] = \"${value}\"|" "$WOKWI_SECRETS"
}

print_config() {
  echo "[mqtt] current effective local demo config"
  printf "  backend: "
  grep -E '^(MQTT_BROKER_HOST|MQTT_BROKER_PORT|MQTT_USERNAME|MQTT_PASSWORD|MQTT_PUBLISH_QOS)=' "$BACKEND_ENV" | tr '\n' ' '
  echo
  printf "  datahub: "
  grep -E '^(datahub.mqtt.uri|datahub.mqtt.username|datahub.mqtt.password|datahub.mqtt.qos)=' "$DATAHUB_CONFIG" | tr '\n' ' '
  echo
  printf "  wokwi:   "
  python3 - <<'PY'
from pathlib import Path
import re
p = Path("simulator/wokwi/src/secrets.h")
text = p.read_text()
for key in ["kMqttHost", "kMqttPort", "kMqttUsername", "kMqttPassword"]:
    m = re.search(rf'{key}(?:\[\])?\s*=\s*([^;]+);', text)
    if m:
        value = m.group(1).strip()
        if key == "kMqttPassword" and value != '""':
            value = '"***"'
        print(f"{key}={value}", end=" ")
print()
PY
}

probe_local_broker() {
  "$ROOT_DIR/hmi/backend/.venv/bin/python" - <<'PY'
from __future__ import annotations

import time
from paho.mqtt import client as mqtt

topic = "edgehub/local-mqtt/probe"
payload = f"probe-{time.time()}"
received: list[str] = []

def on_connect(client, _userdata, _flags, reason_code, _properties):
    print(f"[mqtt] probe connect rc={reason_code}")
    client.subscribe(topic, qos=0)

def on_message(_client, _userdata, msg):
    received.append(msg.payload.decode("utf-8", "replace"))

sub = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="edgehub-local-probe-sub",
    protocol=mqtt.MQTTv311,
)
sub.on_connect = on_connect
sub.on_message = on_message
sub.connect("127.0.0.1", 1883, keepalive=20)
sub.loop_start()
time.sleep(0.5)

pub = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="edgehub-local-probe-pub",
    protocol=mqtt.MQTTv311,
)
pub.connect("127.0.0.1", 1883, keepalive=20)
pub.loop_start()
info = pub.publish(topic, payload, qos=0, retain=False)
info.wait_for_publish(timeout=3)
time.sleep(0.7)
pub.loop_stop()
pub.disconnect()
sub.loop_stop()
sub.disconnect()

if payload not in received:
    raise SystemExit("[fail] local MQTT probe did not receive its own message")
print("[ok] local MQTT broker publish/subscribe works")
PY
}

cd "$ROOT_DIR"

ensure_file "$BACKEND_ENV"
ensure_file "$DATAHUB_CONFIG"
ensure_file "$WOKWI_SECRETS"

if [[ "$MODE" == "apply" ]]; then
  echo "[mqtt] starting local Docker Mosquitto..."
  docker compose -f "$ROOT_DIR/docker-compose.mqtt.yml" up -d

  echo "[mqtt] configuring HMI backend -> 127.0.0.1:1883"
  replace_or_append "$BACKEND_ENV" "MQTT_BROKER_HOST" "127.0.0.1"
  replace_or_append "$BACKEND_ENV" "MQTT_BROKER_PORT" "1883"
  replace_or_append "$BACKEND_ENV" "MQTT_USERNAME" ""
  replace_or_append "$BACKEND_ENV" "MQTT_PASSWORD" ""

  echo "[mqtt] configuring DataHub -> 127.0.0.1:1883"
  replace_or_append "$DATAHUB_CONFIG" "datahub.mqtt.uri" "tcp://127.0.0.1:1883"
  replace_or_append "$DATAHUB_CONFIG" "datahub.mqtt.username" ""
  replace_or_append "$DATAHUB_CONFIG" "datahub.mqtt.password" ""

  echo "[mqtt] configuring Wokwi -> host.wokwi.internal:1883"
  replace_cpp_secret "kMqttHost" "host.wokwi.internal"
  perl -0pi -e 's|kMqttPort\s*=\s*[0-9]+|kMqttPort = 1883|' "$WOKWI_SECRETS"
  replace_cpp_secret "kMqttUsername" ""
  replace_cpp_secret "kMqttPassword" ""

  if [[ "$REBUILD_WOKWI" -eq 1 ]]; then
    echo "[mqtt] rebuilding Wokwi firmware..."
    (cd "$ROOT_DIR/simulator/wokwi" && pio run -e esp32dev)
  fi
fi

print_config
probe_local_broker

cat <<'EOF'

[mqtt] local broker is ready.

Next:
  1. Restart DataHub so it reconnects to local MQTT.
  2. Restart HMI backend so params/set publishes to local MQTT.
  3. Restart Wokwi Simulator so it loads the rebuilt firmware.
  4. Run ./scripts/check-live-mqtt-edge.sh
EOF
