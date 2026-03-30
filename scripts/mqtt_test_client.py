#!/usr/bin/env python3
"""
Install dependency:
python -m pip install -r requirements.txt
"""

import argparse
import json
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

try:
    from paho.mqtt.enums import CallbackAPIVersion
except ImportError:
    CallbackAPIVersion = None


CONFIG_PATH = Path(__file__).with_name("mqtt_client_config.json")

DEFAULT_CONFIG = {
    "broker_host": "broker.emqx.io",
    "broker_port": 1883,
    "username": "",
    "password": "",
    "telemetry_topic": "edge/temperature/edge-node-001/telemetry",
    "params_set_topic": "edge/temperature/edge-node-001/params/set",
    "params_ack_topic": "edge/temperature/edge-node-001/params/ack",
}

IMMEDIATE_TEST_PAYLOAD = {
    "target_temp_c": 38.5,
    "kp": 100,
    "ki": 10,
    "control_period_ms": 800,
    "control_mode": "pi_control",
    "apply_immediately": True,
}

STAGED_TEST_PAYLOAD = {
    "target_temp_c": 36.5,
    "kp": 110,
    "ki": 11,
    "control_period_ms": 1000,
    "control_mode": "pi_control",
    "apply_immediately": False,
}


def print_section(title: str) -> None:
    print()
    print(f"=== {title} ===")


def pretty_json(payload_text: str) -> str:
    try:
        parsed = json.loads(payload_text)
    except json.JSONDecodeError:
        return payload_text
    return json.dumps(parsed, indent=2, ensure_ascii=True)


def load_runtime_config() -> dict:
    config = dict(DEFAULT_CONFIG)

    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        config.update(loaded)

    return config


def build_test_payload(mode: str) -> dict:
    if mode == "staged":
        return STAGED_TEST_PAYLOAD
    return IMMEDIATE_TEST_PAYLOAD


def publish_test_message(client: mqtt.Client, mode: str) -> None:
    time.sleep(3)
    payload = build_test_payload(mode)
    payload_text = json.dumps(payload, separators=(",", ":"))
    params_set_topic = client._userdata["config"]["params_set_topic"]

    print_section("Publish Params")
    print(f"mode: {mode}")
    print(f"topic: {params_set_topic}")
    print("payload:")
    print(pretty_json(payload_text))

    client.publish(params_set_topic, payload_text)


def on_connect(client: mqtt.Client, userdata, flags, reason_code, properties=None):
    mode = userdata["mode"]
    config = userdata["config"]

    print_section("MQTT Connected")
    print(f"broker: {config['broker_host']}:{config['broker_port']}")
    print(f"reason_code: {reason_code}")

    client.subscribe(config["telemetry_topic"])
    client.subscribe(config["params_ack_topic"])

    print_section("Subscriptions")
    print(f"- {config['telemetry_topic']}")
    print(f"- {config['params_ack_topic']}")

    publisher = threading.Thread(
        target=publish_test_message, args=(client, mode), daemon=True
    )
    publisher.start()


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
    payload_text = msg.payload.decode("utf-8", errors="replace")
    config = userdata["config"]

    if msg.topic == config["telemetry_topic"]:
        print_section("Telemetry")
    elif msg.topic == config["params_ack_topic"]:
        print_section("Params Ack")
    else:
        print_section("MQTT Message")

    print(f"topic: {msg.topic}")
    print("payload:")
    print(pretty_json(payload_text))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MQTT test client for the Wokwi ESP32 temperature edge node."
    )
    parser.add_argument(
        "--mode",
        choices=["immediate", "staged"],
        default="immediate",
        help="Choose whether the params/set payload should be applied immediately or staged.",
    )
    return parser.parse_args()


def create_mqtt_client(mode: str, config: dict) -> mqtt.Client:
    userdata = {"mode": mode, "config": config}

    if CallbackAPIVersion is not None:
        return mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            userdata=userdata,
        )

    return mqtt.Client(userdata=userdata)


def main() -> None:
    args = parse_args()
    config = load_runtime_config()

    print_section("Test Client")
    print(f"mode: {args.mode}")
    print(f"config_file: {CONFIG_PATH}")
    print(
        "The client will subscribe first, then publish one params/set payload after 3 seconds."
    )

    client = create_mqtt_client(args.mode, config)
    client.on_connect = on_connect
    client.on_message = on_message

    if config["username"]:
        client.username_pw_set(config["username"], config["password"])

    client.connect(config["broker_host"], int(config["broker_port"]), keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
