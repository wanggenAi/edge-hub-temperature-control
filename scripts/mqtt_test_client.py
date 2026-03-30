#!/usr/bin/env python3
"""
Install dependency:
pip install paho-mqtt
"""

import argparse
import json
import threading
import time

import paho.mqtt.client as mqtt


BROKER_HOST = "broker.emqx.io"
BROKER_PORT = 1883

TELEMETRY_TOPIC = "edge/temperature/edge-node-001/telemetry"
PARAMS_SET_TOPIC = "edge/temperature/edge-node-001/params/set"
PARAMS_ACK_TOPIC = "edge/temperature/edge-node-001/params/ack"

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


def build_test_payload(mode: str) -> dict:
    if mode == "staged":
        return STAGED_TEST_PAYLOAD
    return IMMEDIATE_TEST_PAYLOAD


def publish_test_message(client: mqtt.Client, mode: str) -> None:
    time.sleep(3)
    payload = build_test_payload(mode)
    payload_text = json.dumps(payload, separators=(",", ":"))

    print_section("Publish Params")
    print(f"mode: {mode}")
    print(f"topic: {PARAMS_SET_TOPIC}")
    print("payload:")
    print(pretty_json(payload_text))

    client.publish(PARAMS_SET_TOPIC, payload_text)


def on_connect(client: mqtt.Client, userdata, flags, reason_code, properties=None):
    mode = userdata["mode"]

    print_section("MQTT Connected")
    print(f"broker: {BROKER_HOST}:{BROKER_PORT}")
    print(f"reason_code: {reason_code}")

    client.subscribe(TELEMETRY_TOPIC)
    client.subscribe(PARAMS_ACK_TOPIC)

    print_section("Subscriptions")
    print(f"- {TELEMETRY_TOPIC}")
    print(f"- {PARAMS_ACK_TOPIC}")

    publisher = threading.Thread(
        target=publish_test_message, args=(client, mode), daemon=True
    )
    publisher.start()


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
    payload_text = msg.payload.decode("utf-8", errors="replace")

    if msg.topic == TELEMETRY_TOPIC:
        print_section("Telemetry")
    elif msg.topic == PARAMS_ACK_TOPIC:
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


def main() -> None:
    args = parse_args()

    print_section("Test Client")
    print(f"mode: {args.mode}")
    print("The client will subscribe first, then publish one params/set payload after 3 seconds.")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, userdata={"mode": args.mode}
    )
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
