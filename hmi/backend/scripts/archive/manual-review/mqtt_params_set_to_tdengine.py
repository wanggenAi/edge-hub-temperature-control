from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from paho.mqtt import client as mqtt


# Make sure `app.*` imports work when running this script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Ensure pydantic Settings(env_file=".env") resolves to hmi/backend/.env
os.chdir(ROOT)

from app.core.config import settings  # noqa: E402
from app.services.tdengine_client import TdengineClient  # noqa: E402


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return sql_quote(str(value))


def safe_table_suffix(device_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", device_id).strip("_")
    if not cleaned:
        cleaned = "unknown"
    if cleaned[0].isdigit():
        cleaned = f"d_{cleaned}"
    return cleaned.lower()


def topic_template_to_subscribe_pattern(template: str) -> str:
    # Convert only the device placeholder to single-level wildcard.
    return template.replace("{device_id}", "+")


def extract_device_id_from_topic(topic: str, template: str) -> Optional[str]:
    escaped = re.escape(template).replace(re.escape("{device_id}"), "([^/]+)")
    match = re.fullmatch(escaped, topic)
    if not match:
        return None
    return match.group(1)


def ensure_params_ack_table(tdc: TdengineClient, database: str, device_id: str, mqtt_topic: str) -> str:
    stable_sql = (
        f"CREATE STABLE IF NOT EXISTS {database}.params_ack ("
        f"ts TIMESTAMP, "
        f"ack_type NCHAR(32), "
        f"success BOOL, "
        f"reason NCHAR(128), "
        f"target_temp_c FLOAT, "
        f"kp FLOAT, "
        f"ki FLOAT, "
        f"kd FLOAT, "
        f"control_mode NCHAR(32)"
        f") TAGS (device_id NCHAR(64), mqtt_topic NCHAR(255))"
    )
    tdc.query(stable_sql)

    subtable = f"{database}.params_ack_{safe_table_suffix(device_id)}"
    subtable_sql = (
        f"CREATE TABLE IF NOT EXISTS {subtable} "
        f"USING {database}.params_ack TAGS ({sql_quote(device_id)}, {sql_quote(mqtt_topic)})"
    )
    tdc.query(subtable_sql)
    return subtable


def parse_payload(raw_payload: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Payload must be a JSON object")
    return parsed


def build_insert_sql(
    *,
    table_name: str,
    now_ms: int,
    payload: dict[str, Any],
    default_ack_type: str,
    default_reason: str,
) -> str:
    ack_type = str(payload.get("ack_type") or default_ack_type)
    success = bool(payload.get("success", True))
    reason = str(payload.get("reason") or default_reason)
    target_temp_c = payload.get("target_temp_c")
    kp = payload.get("kp")
    ki = payload.get("ki")
    kd = payload.get("kd")
    control_mode = payload.get("control_mode")

    return (
        f"INSERT INTO {table_name} "
        f"(ts, ack_type, success, reason, target_temp_c, kp, ki, kd, control_mode) VALUES ("
        f"{now_ms}, "
        f"{sql_value(ack_type)}, "
        f"{sql_value(success)}, "
        f"{sql_value(reason)}, "
        f"{sql_value(target_temp_c)}, "
        f"{sql_value(kp)}, "
        f"{sql_value(ki)}, "
        f"{sql_value(kd)}, "
        f"{sql_value(control_mode)}"
        f")"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Subscribe MQTT params/set and persist successful params_ack rows to TDengine."
    )
    parser.add_argument("--mqtt-host", default=settings.mqtt_broker_host)
    parser.add_argument("--mqtt-port", type=int, default=settings.mqtt_broker_port)
    parser.add_argument("--mqtt-username", default=settings.mqtt_username)
    parser.add_argument("--mqtt-password", default=settings.mqtt_password)
    parser.add_argument("--mqtt-client-id", default=f"{settings.mqtt_client_id_prefix}-params-ack-worker")
    parser.add_argument(
        "--topic-template",
        default=settings.mqtt_params_set_topic_template,
        help="Topic template containing {device_id}, e.g. edge/temperature/{device_id}/params/set",
    )
    parser.add_argument("--ack-type", default="applied")
    parser.add_argument("--ack-reason", default="ok")
    parser.add_argument("--simulate-delay-ms", type=int, default=0, help="Optional delay before writing ack row.")
    parser.add_argument("--qos", type=int, default=0)
    parser.add_argument("--database", default=settings.tdengine_database)
    args = parser.parse_args()

    tdc = TdengineClient()
    if not tdc.enabled():
        raise SystemExit("TDengine is disabled by current settings. Set tdengine_enabled=true first.")

    subscribe_topic = topic_template_to_subscribe_pattern(args.topic_template)
    print(f"[{datetime.now(tz=timezone.utc).isoformat()}] Subscribe topic: {subscribe_topic}")
    print(f"[{datetime.now(tz=timezone.utc).isoformat()}] TDengine DB: {args.database}")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=args.mqtt_client_id,
        protocol=mqtt.MQTTv311,
    )
    if args.mqtt_username:
        client.username_pw_set(args.mqtt_username, args.mqtt_password or None)

    def on_connect(cli: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        rc_value = getattr(reason_code, "value", reason_code)
        try:
            rc_int = int(rc_value)
        except Exception:  # noqa: BLE001
            rc_int = 0 if str(reason_code).lower() == "success" else -1

        if rc_int != 0:
            print(f"[mqtt] connect failed, rc={reason_code}")
            return
        cli.subscribe(subscribe_topic, qos=max(0, min(2, int(args.qos))))
        print(f"[mqtt] connected and subscribed, rc={reason_code}")

    def on_message(_cli: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        device_id = extract_device_id_from_topic(msg.topic, args.topic_template)
        if not device_id:
            print(f"[{now_iso}] skip unknown topic: {msg.topic}")
            return

        try:
            payload = parse_payload(msg.payload)
            if args.simulate_delay_ms > 0:
                time.sleep(args.simulate_delay_ms / 1000.0)

            table_name = ensure_params_ack_table(tdc, args.database, device_id, msg.topic)
            insert_sql = build_insert_sql(
                table_name=table_name,
                now_ms=int(time.time() * 1000),
                payload=payload,
                default_ack_type=args.ack_type,
                default_reason=args.ack_reason,
            )
            tdc.query(insert_sql)
            print(
                f"[{now_iso}] ACK saved device={device_id} "
                f"kp={payload.get('kp')} ki={payload.get('ki')} kd={payload.get('kd')} "
                f"mode={payload.get('control_mode')}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{now_iso}] failed topic={msg.topic} error={exc}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.mqtt_host, int(args.mqtt_port), keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
