from __future__ import annotations

import argparse
import atexit
import json
import os
import random
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from paho.mqtt import client as mqtt
from sqlalchemy import select


# Make sure `app.*` imports work when running this script directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "hmi" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
# Ensure pydantic Settings(env_file=".env") resolves to hmi/backend/.env
os.chdir(BACKEND_ROOT)

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import Device, DeviceParameter  # noqa: E402
from app.services.tdengine_client import TdengineClient  # noqa: E402


LOCK_FILE = Path("/tmp/mqtt_set_ack_loopback.lock")


def _acquire_single_instance_lock(*, allow_multi: bool) -> None:
    if allow_multi:
        return
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
        except Exception:  # noqa: BLE001
            old_pid = -1
        if old_pid > 0:
            try:
                os.kill(old_pid, 0)
                raise SystemExit(
                    f"Another mqtt_set_ack_loopback instance is running (pid={old_pid}). "
                    f"Stop it first or pass --allow-multi."
                )
            except OSError:
                pass
    LOCK_FILE.write_text(str(os.getpid()))

    def _cleanup() -> None:
        try:
            if LOCK_FILE.exists():
                lock_pid = int(LOCK_FILE.read_text().strip())
                if lock_pid == os.getpid():
                    LOCK_FILE.unlink()
        except Exception:  # noqa: BLE001
            pass

    atexit.register(_cleanup)


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
    return template.replace("{device_id}", "+")


def extract_device_id_from_topic(topic: str, template: str) -> Optional[str]:
    escaped = re.escape(template).replace(re.escape("{device_id}"), "([^/]+)")
    match = re.fullmatch(escaped, topic)
    if not match:
        return None
    return match.group(1)


def normalize_control_mode(value: Optional[str]) -> str:
    if value is None:
        return "pid_control"
    mode = str(value).strip().lower()
    if mode in {"pid", "pid_control"}:
        return "pid_control"
    if mode in {"pi", "pi_control"}:
        return "pi_control"
    if mode in {"p", "p_control"}:
        return "p_control"
    return mode


def parse_set_payload(raw_payload: bytes) -> dict[str, Any]:
    parsed = json.loads(raw_payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("params/set payload must be a JSON object")
    return parsed


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


def write_ack_to_tdengine(
    *,
    tdc: TdengineClient,
    database: str,
    device_id: str,
    ack_topic: str,
    ack_payload: dict[str, Any],
) -> None:
    table_name = ensure_params_ack_table(tdc, database, device_id, ack_topic)
    now_ms = int(ack_payload.get("ts_ms") or time.time() * 1000)
    sql = (
        f"INSERT INTO {table_name} "
        f"(ts, ack_type, success, reason, target_temp_c, kp, ki, kd, control_mode) VALUES ("
        f"{now_ms}, "
        f"{sql_value(ack_payload.get('ack_type') or 'applied')}, "
        f"{sql_value(bool(ack_payload.get('success', True)))}, "
        f"{sql_value(ack_payload.get('reason') or 'ok')}, "
        f"{sql_value(ack_payload.get('target_temp_c'))}, "
        f"{sql_value(ack_payload.get('kp'))}, "
        f"{sql_value(ack_payload.get('ki'))}, "
        f"{sql_value(ack_payload.get('kd'))}, "
        f"{sql_value(ack_payload.get('control_mode'))}"
        f")"
    )
    tdc.query(sql)


def write_ack_to_postgres(*, device_id: str, ack_payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        device = db.scalar(select(Device).where(Device.code == device_id))
        if not device:
            return
        params = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
        if not params:
            return
        success = bool(ack_payload.get("success", True))
        if success:
            if ack_payload.get("kp") is not None:
                params.kp = float(ack_payload["kp"])
            if ack_payload.get("ki") is not None:
                params.ki = float(ack_payload["ki"])
            if ack_payload.get("kd") is not None:
                params.kd = float(ack_payload["kd"])
            if ack_payload.get("control_mode"):
                params.control_mode = normalize_control_mode(str(ack_payload["control_mode"]))
            if ack_payload.get("target_temp_c") is not None:
                device.target_temp = float(ack_payload["target_temp_c"])
        params.updated_by = "mqtt-loopback-ack"
        params.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def make_ack_topic(set_topic_template: str, ack_topic_template: str, device_id: str) -> str:
    ack_tpl = ack_topic_template or set_topic_template.replace("/params/set", "/params/ack")
    return ack_tpl.format(device_id=device_id)


def build_ack_payload(
    *,
    device_id: str,
    set_payload: dict[str, Any],
    success: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "ts_ms": int(time.time() * 1000),
        "ack_type": "applied" if success else "rejected",
        "success": bool(success),
        "reason": reason,
        "target_temp_c": set_payload.get("target_temp_c"),
        "kp": set_payload.get("kp"),
        "ki": set_payload.get("ki"),
        "kd": set_payload.get("kd"),
        "control_mode": set_payload.get("control_mode"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Simulate device + data-hub loopback: subscribe params/set, publish params/ack, "
            "then consume ack and write to TDengine/PostgreSQL."
        )
    )
    parser.add_argument("--mqtt-host", default=settings.mqtt_broker_host)
    parser.add_argument("--mqtt-port", type=int, default=settings.mqtt_broker_port)
    parser.add_argument("--mqtt-username", default=settings.mqtt_username)
    parser.add_argument("--mqtt-password", default=settings.mqtt_password)
    parser.add_argument("--mqtt-client-id", default=f"{settings.mqtt_client_id_prefix}-set-ack-loopback-{uuid.uuid4().hex[:6]}")
    parser.add_argument("--set-topic-template", default=settings.mqtt_params_set_topic_template)
    parser.add_argument("--ack-topic-template", default=settings.mqtt_params_set_topic_template.replace("/params/set", "/params/ack"))
    parser.add_argument("--database", default=settings.tdengine_database)
    parser.add_argument("--qos", type=int, default=0)
    parser.add_argument("--simulate-delay-ms", type=int, default=150)
    parser.add_argument("--allow-multi", action="store_true", help="Allow multiple loopback instances (not recommended).")
    parser.add_argument(
        "--mode",
        choices=("both", "device", "hub"),
        default="both",
        help="device: only consume set and publish ack; hub: only consume ack and write DB; both: full chain.",
    )
    parser.add_argument("--force-fail", action="store_true", help="Always return failed ack from simulated device.")
    parser.add_argument(
        "--fail-ratio",
        type=float,
        default=0.0,
        help="Random failure ratio [0..1] for simulated device ack (ignored by --force-fail).",
    )
    args = parser.parse_args()
    _acquire_single_instance_lock(allow_multi=bool(args.allow_multi))

    set_sub_topic = topic_template_to_subscribe_pattern(args.set_topic_template)
    ack_sub_topic = topic_template_to_subscribe_pattern(args.ack_topic_template)

    tdc = TdengineClient()
    if args.mode in {"both", "hub"} and not tdc.enabled():
        raise SystemExit("TDengine is disabled; enable tdengine_enabled=true or run --mode device.")

    print(f"[{datetime.now(tz=timezone.utc).isoformat()}] mode={args.mode}")
    print(f"[{datetime.now(tz=timezone.utc).isoformat()}] mqtt_client_id={args.mqtt_client_id}")
    print(f"[{datetime.now(tz=timezone.utc).isoformat()}] mqtt={args.mqtt_host}:{args.mqtt_port}")
    print(f"[{datetime.now(tz=timezone.utc).isoformat()}] subscribe set={set_sub_topic}")
    if args.mode in {"both", "hub"}:
        print(f"[{datetime.now(tz=timezone.utc).isoformat()}] subscribe ack={ack_sub_topic} -> tdengine/postgres")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=args.mqtt_client_id,
        protocol=mqtt.MQTTv311,
    )
    if args.mqtt_username:
        client.username_pw_set(args.mqtt_username, args.mqtt_password or None)

    def on_connect(cli: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        rc_value = getattr(reason_code, "value", reason_code)
        rc_int = int(rc_value) if str(rc_value).isdigit() else (0 if str(reason_code).lower() == "success" else -1)
        if rc_int != 0:
            print(f"[mqtt] connect failed rc={reason_code}")
            return
        if args.mode in {"both", "device"}:
            cli.subscribe(set_sub_topic, qos=max(0, min(2, int(args.qos))))
        if args.mode in {"both", "hub"}:
            cli.subscribe(ack_sub_topic, qos=max(0, min(2, int(args.qos))))
        print(f"[mqtt] connected rc={reason_code}")

    def on_disconnect(_cli: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        print(f"[{now_iso}] [mqtt] disconnected rc={reason_code}")

    def on_message(cli: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        set_device_id = extract_device_id_from_topic(msg.topic, args.set_topic_template)
        if set_device_id and args.mode in {"both", "device"}:
            try:
                set_payload = parse_set_payload(msg.payload)
                if args.simulate_delay_ms > 0:
                    time.sleep(args.simulate_delay_ms / 1000.0)
                should_fail = bool(args.force_fail) or (args.fail_ratio > 0 and random.random() < float(args.fail_ratio))
                success = not should_fail
                reason = "ok" if success else "simulated_reject"
                ack_payload = build_ack_payload(
                    device_id=set_device_id,
                    set_payload=set_payload,
                    success=success,
                    reason=reason,
                )
                ack_topic = make_ack_topic(args.set_topic_template, args.ack_topic_template, set_device_id)
                cli.publish(ack_topic, json.dumps(ack_payload, separators=(",", ":")), qos=max(0, min(2, int(args.qos))), retain=False)
                print(
                    f"[{now_iso}] device-sim set->ack device={set_device_id} "
                    f"success={success} kp={set_payload.get('kp')} ki={set_payload.get('ki')} kd={set_payload.get('kd')}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[{now_iso}] device-sim failed topic={msg.topic} err={exc}")
            return

        ack_device_id = extract_device_id_from_topic(msg.topic, args.ack_topic_template)
        if ack_device_id and args.mode in {"both", "hub"}:
            try:
                ack_payload = parse_set_payload(msg.payload)
                write_ack_to_tdengine(
                    tdc=tdc,
                    database=args.database,
                    device_id=ack_device_id,
                    ack_topic=msg.topic,
                    ack_payload=ack_payload,
                )
                write_ack_to_postgres(device_id=ack_device_id, ack_payload=ack_payload)
                print(
                    f"[{now_iso}] hub-sim ack->db device={ack_device_id} success={bool(ack_payload.get('success', True))} "
                    f"kp={ack_payload.get('kp')} ki={ack_payload.get('ki')} kd={ack_payload.get('kd')}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[{now_iso}] hub-sim failed topic={msg.topic} err={exc}")
            return

        print(f"[{now_iso}] ignore topic={msg.topic}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.connect(args.mqtt_host, int(args.mqtt_port), keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
