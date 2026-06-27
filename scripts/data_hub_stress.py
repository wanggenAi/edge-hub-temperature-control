#!/usr/bin/env python3
"""
MQTT load generator for data-hub ingress stress testing.

Examples:
  python scripts/data_hub_stress.py --duration 60 --rate 1000 --devices 200
  python scripts/data_hub_stress.py --host YOUR_BROKER_HOST --port 1883 --username edgeadmin --password YOUR_PASSWORD \
    --duration 120 --rate 2000 --devices 500 --workers 4 --qos 1
"""

from __future__ import annotations

import argparse
import json
import math
import random
import signal
import string
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from paho.mqtt import client as mqtt


@dataclass
class Config:
    host: str
    port: int
    username: str
    password: str
    qos: int
    workers: int
    devices: int
    rate: float
    duration: int
    device_prefix: str
    start_index: int
    seed: int


@dataclass
class Stats:
    sent_ok: int = 0
    sent_fail: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def inc_ok(self, n: int = 1) -> None:
        with self.lock:
            self.sent_ok += n

    def inc_fail(self, n: int = 1) -> None:
        with self.lock:
            self.sent_fail += n

    def snapshot(self) -> tuple[int, int]:
        with self.lock:
            return self.sent_ok, self.sent_fail


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Stress test generator for data-hub MQTT ingestion.")
    parser.add_argument("--host", default="127.0.0.1", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--username", default="", help="MQTT username")
    parser.add_argument("--password", default="", help="MQTT password")
    parser.add_argument("--qos", type=int, default=1, choices=[0, 1, 2], help="MQTT QoS")
    parser.add_argument("--workers", type=int, default=2, help="Publisher worker threads")
    parser.add_argument("--devices", type=int, default=200, help="Number of simulated devices")
    parser.add_argument("--rate", type=float, default=1000.0, help="Total telemetry messages per second")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--device-prefix", default="TC-", help="Device code prefix")
    parser.add_argument("--start-index", type=int, default=1, help="Start index for generated device codes")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    ns = parser.parse_args()
    if ns.workers < 1:
        raise SystemExit("--workers must be >= 1")
    if ns.devices < 1:
        raise SystemExit("--devices must be >= 1")
    if ns.rate <= 0:
        raise SystemExit("--rate must be > 0")
    if ns.duration <= 0:
        raise SystemExit("--duration must be > 0")
    return Config(
        host=ns.host,
        port=ns.port,
        username=ns.username,
        password=ns.password,
        qos=ns.qos,
        workers=ns.workers,
        devices=ns.devices,
        rate=ns.rate,
        duration=ns.duration,
        device_prefix=ns.device_prefix,
        start_index=ns.start_index,
        seed=ns.seed,
    )


def make_device_codes(prefix: str, count: int, start_index: int) -> list[str]:
    width = max(3, len(str(start_index + count)))
    return [f"{prefix}{i:0{width}d}" for i in range(start_index, start_index + count)]


def calc_error_c(target_temp_c: float, sensor_temp_c: float) -> float:
    return float(target_temp_c) - float(sensor_temp_c)


def build_telemetry_payload(device_id: str, seq: int, now_ms: int) -> dict:
    phase = (hash(device_id) % 360) / 180.0 * math.pi
    wave = math.sin(seq / 12.0 + phase) * 0.8
    drift = math.sin(seq / 90.0 + phase) * 0.2
    target_temp = 36.0 + (hash(device_id) % 8) * 0.4
    sensor_temp = target_temp + wave + drift
    sim_temp = sensor_temp + math.sin(seq / 7.0) * 0.03
    error_c = calc_error_c(target_temp, sensor_temp)
    pwm_duty = max(10, min(99, int(50 + max(0.0, error_c) * 12 + abs(wave) * 8)))
    payload = {
        "device_id": device_id,
        "uptime_ms": now_ms,
        "target_temp_c": round(target_temp, 4),
        "sim_temp_c": round(sim_temp, 4),
        "sensor_temp_c": round(sensor_temp, 4),
        "error_c": round(error_c, 4),
        "integral_error": round(error_c * 30, 4),
        "control_output": round(pwm_duty * 2.0, 4),
        "pwm_duty": pwm_duty,
        "pwm_norm": round(pwm_duty / 255.0, 6),
        "control_period_ms": 1000,
        "saturation_state": "high" if pwm_duty >= 85 else ("medium" if pwm_duty >= 70 else "normal"),
        "sensor_valid": True,
        "run_id": "stress-" + "".join(random.choice(string.ascii_lowercase) for _ in range(6)),
        "control_mode": "PI",
        "controller_version": "stress-v1",
        "kp": 110.0,
        "ki": 10.0,
        "kd": 0.0,
        "system_state": "running",
        "sensor_status": "ok",
        "actual_dt_ms": 1000,
        "dt_error_ms": 0,
        "wifi_connected": True,
        "mqtt_connected": True,
        "mqtt_reconnect_count": 0,
        "mqtt_publish_fail_count": 0,
        "safety_output_forced_off": False,
        "fault_latched": False,
        "fault_reason": "",
        "software_max_safe_temp_c": 65.0,
        "has_pending_params": False,
        "pending_params_age_ms": 0,
    }
    return payload


def build_client(config: Config, worker_id: int) -> mqtt.Client:
    client_id = f"datahub-stress-{worker_id}-{int(time.time())}"
    cli = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
    if config.username:
        cli.username_pw_set(config.username, config.password or None)
    cli.connect(config.host, config.port, keepalive=20)
    cli.loop_start()
    return cli


def worker_loop(
    worker_id: int,
    config: Config,
    device_codes: list[str],
    stop_event: threading.Event,
    stats: Stats,
    deadline: float,
) -> None:
    client: Optional[mqtt.Client] = None
    try:
        client = build_client(config, worker_id)
        rate_per_worker = config.rate / config.workers
        period = 1.0 / rate_per_worker if rate_per_worker > 0 else 0.01
        next_tick = time.perf_counter()
        seq = 0
        device_index = worker_id % len(device_codes)

        while not stop_event.is_set() and time.time() < deadline:
            now_ms = int(time.time() * 1000)
            device_id = device_codes[device_index]
            topic = f"edge/temperature/{device_id}/telemetry"
            payload_text = json.dumps(build_telemetry_payload(device_id, seq, now_ms), separators=(",", ":"), ensure_ascii=True)
            result = client.publish(topic, payload_text, qos=config.qos, retain=False)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                stats.inc_ok()
            else:
                stats.inc_fail()

            seq += 1
            device_index = (device_index + 1) % len(device_codes)
            next_tick += period
            sleep_for = next_tick - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_tick = time.perf_counter()
    except Exception:
        stats.inc_fail()
        stop_event.set()
    finally:
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass


def main() -> None:
    config = parse_args()
    random.seed(config.seed)
    device_codes = make_device_codes(config.device_prefix, config.devices, config.start_index)
    stop_event = threading.Event()
    stats = Stats()
    deadline = time.time() + config.duration

    def _stop(_sig, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    threads: list[threading.Thread] = []
    for i in range(config.workers):
        t = threading.Thread(
            target=worker_loop,
            args=(i + 1, config, device_codes, stop_event, stats, deadline),
            daemon=True,
        )
        t.start()
        threads.append(t)

    print(
        f"data-hub stress started host={config.host}:{config.port} "
        f"devices={config.devices} workers={config.workers} rate={config.rate:.1f} msg/s duration={config.duration}s"
    )
    start = time.time()
    prev_ok, prev_fail = 0, 0
    while not stop_event.is_set() and time.time() < deadline:
        time.sleep(1.0)
        ok, fail = stats.snapshot()
        d_ok, d_fail = ok - prev_ok, fail - prev_fail
        prev_ok, prev_fail = ok, fail
        elapsed = int(time.time() - start)
        print(
            f"[{elapsed:>4}s] sent_ok={ok} sent_fail={fail} "
            f"rate_ok={d_ok}/s rate_fail={d_fail}/s"
        )

    stop_event.set()
    for t in threads:
        t.join(timeout=2.0)

    total_ok, total_fail = stats.snapshot()
    elapsed = max(0.001, time.time() - start)
    print(
        "data-hub stress finished "
        f"elapsed={elapsed:.1f}s sent_ok={total_ok} sent_fail={total_fail} "
        f"avg_ok_rate={total_ok / elapsed:.1f}/s"
    )


if __name__ == "__main__":
    main()
