#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import random
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from paho.mqtt import client as mqtt
from sqlalchemy import select


CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import Device, DeviceParameter, User, UserDevice  # noqa: E402


def calc_error_c(target_temp_c: float, sensor_temp_c: float) -> float:
    return float(target_temp_c) - float(sensor_temp_c)


@dataclass(frozen=True)
class ThermalEnvironment:
    key: str
    label: str
    default_start_temp: float
    default_target_temp: float
    ambient_temp: float
    heater_gain_c_per_s: float
    heat_loss_per_s: float
    max_pwm: float
    sensor_alpha: float
    sensor_noise_std: float
    dead_time_steps: int
    feedforward_pwm: float
    controller_gain: float
    disturbance_bias_c_per_s: float = 0.0
    disturbance_std_c_per_s: float = 0.0
    periodic_disturbance_c_per_s: float = 0.0
    ambient_drift_c: float = 0.0


ENVIRONMENTS: dict[str, ThermalEnvironment] = {
    "defense_live": ThermalEnvironment(
        key="defense_live",
        label="Defense live loop with visible setpoint response",
        default_start_temp=34.8,
        default_target_temp=37.0,
        ambient_temp=25.0,
        heater_gain_c_per_s=0.130,
        heat_loss_per_s=0.0054,
        max_pwm=82.0,
        sensor_alpha=0.16,
        sensor_noise_std=0.008,
        dead_time_steps=2,
        feedforward_pwm=50.0,
        controller_gain=1.2,
        disturbance_std_c_per_s=0.00025,
        periodic_disturbance_c_per_s=0.00025,
        ambient_drift_c=0.1,
    ),
    "balanced_cell": ThermalEnvironment(
        key="balanced_cell",
        label="Balanced thermal cell",
        default_start_temp=36.6,
        default_target_temp=37.0,
        ambient_temp=25.0,
        heater_gain_c_per_s=0.145,
        heat_loss_per_s=0.0052,
        max_pwm=86.0,
        sensor_alpha=0.24,
        sensor_noise_std=0.025,
        dead_time_steps=1,
        feedforward_pwm=46.0,
        controller_gain=3.2,
        disturbance_std_c_per_s=0.0008,
        periodic_disturbance_c_per_s=0.0015,
        ambient_drift_c=0.4,
    ),
    "high_mass_load": ThermalEnvironment(
        key="high_mass_load",
        label="High thermal mass / slow heater",
        default_start_temp=33.8,
        default_target_temp=38.0,
        ambient_temp=24.0,
        heater_gain_c_per_s=0.090,
        heat_loss_per_s=0.0058,
        max_pwm=94.0,
        sensor_alpha=0.12,
        sensor_noise_std=0.035,
        dead_time_steps=4,
        feedforward_pwm=68.0,
        controller_gain=2.7,
        disturbance_bias_c_per_s=-0.001,
        disturbance_std_c_per_s=0.0012,
        periodic_disturbance_c_per_s=0.001,
        ambient_drift_c=0.6,
    ),
    "laggy_loop": ThermalEnvironment(
        key="laggy_loop",
        label="Laggy loop with delayed heat transfer",
        default_start_temp=37.8,
        default_target_temp=37.0,
        ambient_temp=25.0,
        heater_gain_c_per_s=0.170,
        heat_loss_per_s=0.0065,
        max_pwm=100.0,
        sensor_alpha=0.08,
        sensor_noise_std=0.045,
        dead_time_steps=7,
        feedforward_pwm=52.0,
        controller_gain=3.4,
        disturbance_std_c_per_s=0.0015,
        periodic_disturbance_c_per_s=0.002,
        ambient_drift_c=0.5,
    ),
    "fast_heater": ThermalEnvironment(
        key="fast_heater",
        label="Fast heater / low thermal capacity",
        default_start_temp=35.9,
        default_target_temp=36.5,
        ambient_temp=26.0,
        heater_gain_c_per_s=0.220,
        heat_loss_per_s=0.0070,
        max_pwm=100.0,
        sensor_alpha=0.30,
        sensor_noise_std=0.03,
        dead_time_steps=2,
        feedforward_pwm=42.0,
        controller_gain=3.2,
        disturbance_std_c_per_s=0.001,
        periodic_disturbance_c_per_s=0.001,
        ambient_drift_c=0.3,
    ),
    "weak_actuator": ThermalEnvironment(
        key="weak_actuator",
        label="Weak actuator / high heat loss",
        default_start_temp=34.2,
        default_target_temp=40.0,
        ambient_temp=22.5,
        heater_gain_c_per_s=0.075,
        heat_loss_per_s=0.0105,
        max_pwm=76.0,
        sensor_alpha=0.17,
        sensor_noise_std=0.035,
        dead_time_steps=3,
        feedforward_pwm=72.0,
        controller_gain=2.8,
        disturbance_bias_c_per_s=-0.0015,
        disturbance_std_c_per_s=0.001,
        periodic_disturbance_c_per_s=0.0015,
        ambient_drift_c=0.7,
    ),
    "loss_drift": ThermalEnvironment(
        key="loss_drift",
        label="Heat loss drift / integral needed",
        default_start_temp=35.8,
        default_target_temp=37.5,
        ambient_temp=23.0,
        heater_gain_c_per_s=0.120,
        heat_loss_per_s=0.0088,
        max_pwm=90.0,
        sensor_alpha=0.20,
        sensor_noise_std=0.03,
        dead_time_steps=2,
        feedforward_pwm=62.0,
        controller_gain=2.6,
        disturbance_bias_c_per_s=-0.0012,
        disturbance_std_c_per_s=0.001,
        periodic_disturbance_c_per_s=0.0012,
        ambient_drift_c=1.0,
    ),
}


@dataclass
class EdgeNodeState:
    device_id: str
    env: ThermalEnvironment
    target_temp_c: float
    true_temp_c: float
    sensor_temp_c: float
    kp: float
    ki: float
    kd: float
    control_mode: str
    control_period_ms: int
    run_id: str
    integral_error: float = 0.0
    last_control_error: float = 0.0
    last_pwm: float = 0.0
    last_raw_output: float = 0.0
    last_derivative: float = 0.0
    started_monotonic: float = field(default_factory=time.monotonic)
    last_step_monotonic: float = field(default_factory=time.monotonic)
    delayed_pwm: list[float] = field(default_factory=list)
    mqtt_reconnect_count: int = 0
    mqtt_publish_fail_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if not self.delayed_pwm:
            self.delayed_pwm = [self.env.feedforward_pwm] * max(1, int(self.env.dead_time_steps))
        self.last_control_error = self.target_temp_c - self.sensor_temp_c


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def topic_template_to_subscribe_pattern(template: str) -> str:
    return template.replace("{device_id}", "+")


def extract_device_id(topic: str, template: str) -> Optional[str]:
    left, right = template.split("{device_id}", 1)
    if not topic.startswith(left) or not topic.endswith(right):
        return None
    device_id = topic[len(left) : len(topic) - len(right) if right else len(topic)]
    return device_id or None


def parse_device_specs(raw: str, default_environment: str) -> list[tuple[str, str]]:
    specs: list[tuple[str, str]] = []
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        if "=" in text:
            device_id, env_key = [part.strip() for part in text.split("=", 1)]
        elif ":" in text:
            device_id, env_key = [part.strip() for part in text.split(":", 1)]
        else:
            device_id, env_key = text, default_environment
        if not device_id:
            raise SystemExit("Device id cannot be empty in --devices")
        if env_key not in ENVIRONMENTS:
            raise SystemExit(f"Unknown environment '{env_key}'. Use --list-environments.")
        specs.append((device_id, env_key))
    if not specs:
        raise SystemExit("No devices configured")
    return specs


def ensure_postgres_device(state: EdgeNodeState, *, name: str, updated_by: str) -> None:
    db = SessionLocal()
    try:
        device = db.scalar(select(Device).where(Device.code == state.device_id))
        if device is None:
            device = Device(code=state.device_id, name=name)
            db.add(device)
            db.flush()

        device.name = name
        device.line = "Defense Live Line"
        device.location = state.env.label
        device.status = "active"
        device.current_temp = round(state.sensor_temp_c, 3)
        device.target_temp = round(state.target_temp_c, 3)
        device.pwm_output = round(state.last_pwm, 2)
        device.is_alarm = False
        device.is_online = True
        device.updated_at = datetime.utcnow()

        param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
        if param is None:
            param = DeviceParameter(device_id=device.id)
            db.add(param)
            db.flush()
        param.kp = float(state.kp)
        param.ki = float(state.ki)
        param.kd = float(state.kd)
        param.control_mode = state.control_mode
        param.target_band = 0.5
        param.overshoot_limit_pct = 3.0
        param.saturation_warn_ratio = 0.3
        param.saturation_high_ratio = 0.6
        param.pwm_saturation_threshold = min(85.0, round(state.env.max_pwm * 0.95, 4))
        param.steady_window_samples = 12
        param.sampling_period_ms = int(state.control_period_ms)
        param.upload_period_s = max(1, int(round(state.control_period_ms / 1000.0)))
        param.updated_at = datetime.utcnow()
        param.updated_by = updated_by

        for user in db.scalars(select(User)).all():
            exists = db.scalar(
                select(UserDevice.id).where(UserDevice.user_id == user.id, UserDevice.device_id == device.id)
            )
            if not exists:
                db.add(UserDevice(user_id=user.id, device_id=device.id))
        db.commit()
        print(f"[postgres] ensured device={state.device_id} env={state.env.key} target={state.target_temp_c:.2f}")
    finally:
        db.close()


def apply_params_set(state: EdgeNodeState, payload: dict[str, Any]) -> tuple[bool, str]:
    try:
        next_target = float(payload.get("target_temp_c", state.target_temp_c))
        next_kp = float(payload.get("kp", state.kp))
        next_ki = float(payload.get("ki", state.ki))
        next_kd = float(payload.get("kd", state.kd))
        next_period = int(payload.get("control_period_ms", state.control_period_ms))
        next_mode = normalize_control_mode(payload.get("control_mode", state.control_mode))
    except (TypeError, ValueError) as exc:
        return False, f"payload_parse_failed:{exc}"

    if not 20.0 <= next_target <= 60.0:
        return False, "target_temp_out_of_range"
    if not 0.0 <= next_kp <= 1000.0:
        return False, "kp_out_of_range"
    if not 0.0 <= next_ki <= 1000.0:
        return False, "ki_out_of_range"
    if not 0.0 <= next_kd <= 1000.0:
        return False, "kd_out_of_range"
    if not 200 <= next_period <= 10000:
        return False, "control_period_out_of_range"

    with state.lock:
        state.target_temp_c = next_target
        state.kp = next_kp
        state.ki = next_ki
        state.kd = next_kd
        state.control_period_ms = next_period
        state.control_mode = next_mode
    return True, "applied_ok"


def step_thermal_model(state: EdgeNodeState, now: float, rng: random.Random) -> dict[str, Any]:
    with state.lock:
        dt = clamp(now - state.last_step_monotonic, 0.05, 5.0)
        state.last_step_monotonic = now
        elapsed = now - state.started_monotonic

        control_error = state.target_temp_c - state.sensor_temp_c
        dt_minutes = max(1e-6, dt / 60.0)
        proposed_integral = clamp(state.integral_error + control_error * dt_minutes, -80.0, 80.0)
        derivative = (control_error - state.last_control_error) / dt_minutes
        state.last_control_error = control_error

        p_term = state.kp * control_error
        i_term = state.ki * proposed_integral
        d_term = state.kd * derivative if state.control_mode == "pid_control" else 0.0
        if state.control_mode == "p_control":
            i_term = 0.0
            d_term = 0.0
        raw_output = state.env.feedforward_pwm + state.env.controller_gain * (p_term + i_term + d_term)
        pwm = clamp(raw_output, 0.0, state.env.max_pwm)

        pushing_high = pwm >= state.env.max_pwm and control_error > 0
        pushing_low = pwm <= 0.0 and control_error < 0
        if not (pushing_high or pushing_low):
            state.integral_error = proposed_integral

        state.delayed_pwm.append(pwm)
        applied_pwm = state.delayed_pwm.pop(0)

        ambient = state.env.ambient_temp + state.env.ambient_drift_c * math.sin(elapsed / 180.0)
        disturbance = (
            state.env.disturbance_bias_c_per_s
            + state.env.periodic_disturbance_c_per_s * math.sin(elapsed / 23.0 + 0.4)
            + rng.gauss(0.0, state.env.disturbance_std_c_per_s)
        )
        heating = state.env.heater_gain_c_per_s * (applied_pwm / 100.0)
        cooling = state.env.heat_loss_per_s * (state.true_temp_c - ambient)
        state.true_temp_c += (heating - cooling + disturbance) * dt
        state.sensor_temp_c += state.env.sensor_alpha * (state.true_temp_c - state.sensor_temp_c)
        state.sensor_temp_c += rng.gauss(0.0, state.env.sensor_noise_std)

        state.last_pwm = pwm
        state.last_raw_output = raw_output
        state.last_derivative = derivative

        uptime_ms = int((now - state.started_monotonic) * 1000)
        fault_latched = bool(state.sensor_temp_c >= 65.0)
        sensor_valid = bool(-20.0 < state.sensor_temp_c < 100.0)
        if fault_latched:
            saturation_state = "safety_off"
        elif pwm >= state.env.max_pwm * 0.96 or pwm >= 85.0:
            saturation_state = "high"
        elif pwm >= 70.0:
            saturation_state = "medium"
        else:
            saturation_state = "none"

        actual_dt_ms = int(dt * 1000)
        payload = {
            "device_id": state.device_id,
            "uptime_ms": uptime_ms,
            "target_temp_c": round(state.target_temp_c, 4),
            "sim_temp_c": round(state.true_temp_c, 4),
            "sensor_temp_c": round(state.sensor_temp_c, 4),
            "sensor_status": "ok" if sensor_valid else "invalid",
            "error_c": round(calc_error_c(state.target_temp_c, state.sensor_temp_c), 4),
            "integral_error": round(state.integral_error, 5),
            "derivative_error": round(derivative, 6),
            "d_term": round(d_term, 6),
            "control_output": round(raw_output, 4),
            "pwm_duty": int(round(pwm)),
            "pwm_norm": round(pwm / 100.0, 5),
            "control_period_ms": int(state.control_period_ms),
            "actual_dt_ms": actual_dt_ms,
            "dt_error_ms": int(actual_dt_ms - state.control_period_ms),
            "saturation_state": saturation_state,
            "sensor_valid": sensor_valid,
            "run_id": state.run_id,
            "control_mode": state.control_mode,
            "controller_version": "defense_live_thermal_node_v1",
            "kp": round(state.kp, 6),
            "ki": round(state.ki, 6),
            "kd": round(state.kd, 6),
            "system_state": "running",
            "wifi_connected": True,
            "mqtt_connected": True,
            "mqtt_reconnect_count": int(state.mqtt_reconnect_count),
            "mqtt_publish_fail_count": int(state.mqtt_publish_fail_count),
            "safety_output_forced_off": fault_latched,
            "fault_latched": fault_latched,
            "fault_reason": "software_max_safe_temp" if fault_latched else "none",
            "software_max_safe_temp_c": 65.0,
            "has_pending_params": False,
            "pending_params_age_ms": 0,
        }
        return payload


def build_ack_payload(state: EdgeNodeState, *, success: bool, reason: str) -> dict[str, Any]:
    with state.lock:
        return {
            "device_id": state.device_id,
            "ack_type": "applied" if success else "validation_error",
            "success": bool(success),
            "applied_immediately": True,
            "has_pending_params": False,
            "target_temp_c": round(state.target_temp_c, 4),
            "kp": round(state.kp, 6),
            "ki": round(state.ki, 6),
            "kd": round(state.kd, 6),
            "control_period_ms": int(state.control_period_ms),
            "control_mode": state.control_mode,
            "reason": reason,
            "uptime_ms": int((time.monotonic() - state.started_monotonic) * 1000),
            "sensor_valid": True,
            "fault_latched": False,
            "fault_reason": "none",
            "software_max_safe_temp_c": 65.0,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a live MQTT thermal edge node for the defense HMI -> MQTT -> DataHub -> TDengine demo."
    )
    parser.add_argument("--list-environments", action="store_true")
    parser.add_argument("--device-id", default="LIVE-DEMO-01", help="Primary device id when --devices is not used")
    parser.add_argument(
        "--devices",
        default="",
        help="Comma-separated CODE=environment list, for example LIVE-DEMO-01=defense_live,LIVE-SLOW-01=high_mass_load",
    )
    parser.add_argument("--environment", default="defense_live", choices=sorted(ENVIRONMENTS))
    parser.add_argument("--name", default="Defense Live MQTT Edge Node")
    parser.add_argument("--start-temp", type=float, default=None)
    parser.add_argument("--target-temp", type=float, default=None)
    parser.add_argument("--kp", type=float, default=2.6)
    parser.add_argument("--ki", type=float, default=0.34)
    parser.add_argument("--kd", type=float, default=0.06)
    parser.add_argument("--control-mode", default="pid_control")
    parser.add_argument("--control-period-ms", type=int, default=1000)
    parser.add_argument("--mqtt-host", default=settings.mqtt_broker_host)
    parser.add_argument("--mqtt-port", type=int, default=settings.mqtt_broker_port)
    parser.add_argument("--mqtt-username", default=settings.mqtt_username)
    parser.add_argument("--mqtt-password", default=settings.mqtt_password)
    parser.add_argument("--mqtt-client-id", default="")
    parser.add_argument("--set-topic-template", default=settings.mqtt_params_set_topic_template)
    parser.add_argument(
        "--ack-topic-template",
        default=settings.mqtt_params_set_topic_template.replace("/params/set", "/params/ack"),
    )
    parser.add_argument("--telemetry-topic-template", default="edge/temperature/{device_id}/telemetry")
    parser.add_argument("--qos", type=int, default=settings.mqtt_publish_qos)
    parser.add_argument("--interval", type=float, default=1.0, help="Telemetry publish interval seconds")
    parser.add_argument("--seconds", type=int, default=0, help="Run duration; 0 = forever")
    parser.add_argument("--seed", type=int, default=20260515)
    parser.add_argument("--skip-postgres", action="store_true", help="Do not create/update HMI device rows")
    parser.add_argument("--log-every", type=int, default=5, help="Print every N telemetry ticks")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_environments:
        for env in ENVIRONMENTS.values():
            print(f"{env.key}: {env.label}")
        return

    specs = (
        parse_device_specs(args.devices, args.environment)
        if args.devices.strip()
        else [(args.device_id, args.environment)]
    )
    rng = random.Random(args.seed)
    states: dict[str, EdgeNodeState] = {}
    for idx, (device_id, env_key) in enumerate(specs):
        env = ENVIRONMENTS[env_key]
        start_temp = float(args.start_temp if args.start_temp is not None else env.default_start_temp)
        target_temp = float(args.target_temp if args.target_temp is not None else env.default_target_temp)
        state = EdgeNodeState(
            device_id=device_id,
            env=env,
            target_temp_c=target_temp,
            true_temp_c=start_temp,
            sensor_temp_c=start_temp,
            kp=float(args.kp),
            ki=float(args.ki),
            kd=float(args.kd),
            control_mode=normalize_control_mode(args.control_mode),
            control_period_ms=int(args.control_period_ms),
            run_id=f"{device_id}-live-{uuid.uuid4().hex[:8]}",
        )
        states[device_id] = state
        if not args.skip_postgres:
            name = args.name if len(specs) == 1 else f"{args.name} {idx + 1}"
            ensure_postgres_device(state, name=name, updated_by="defense_live_edge_node")

    stop = {"flag": False}

    def stop_handler(_sig: int, _frame: Any) -> None:
        stop["flag"] = True

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    client_id = args.mqtt_client_id or f"{settings.mqtt_client_id_prefix}-live-edge-{uuid.uuid4().hex[:8]}"
    qos = max(0, min(2, int(args.qos)))
    set_sub_topic = topic_template_to_subscribe_pattern(args.set_topic_template)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )
    if args.mqtt_username:
        client.username_pw_set(args.mqtt_username, args.mqtt_password or None)

    def publish_json(topic: str, payload_obj: dict[str, Any]) -> None:
        payload = json.dumps(payload_obj, ensure_ascii=True, separators=(",", ":"))
        result = client.publish(topic, payload=payload, qos=qos, retain=False)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            device_id = str(payload_obj.get("device_id") or "")
            if device_id in states:
                with states[device_id].lock:
                    states[device_id].mqtt_publish_fail_count += 1
            print(f"[mqtt] publish failed topic={topic} rc={result.rc}")

    def on_connect(cli: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        rc_value = getattr(reason_code, "value", reason_code)
        rc_int = int(rc_value) if str(rc_value).isdigit() else (0 if str(reason_code).lower() == "success" else -1)
        if rc_int == 0:
            cli.subscribe(set_sub_topic, qos=qos)
            print(f"[mqtt] connected host={args.mqtt_host}:{args.mqtt_port} client_id={client_id}")
            print(f"[mqtt] subscribe params/set={set_sub_topic}")
        else:
            print(f"[mqtt] connect failed rc={reason_code}")

    def on_disconnect(_cli: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        for state in states.values():
            with state.lock:
                state.mqtt_reconnect_count += 1
        print(f"[mqtt] disconnected rc={reason_code}")

    def on_message(_cli: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        device_id = extract_device_id(msg.topic, args.set_topic_template)
        if device_id is None or device_id not in states:
            return
        state = states[device_id]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("params/set payload must be a JSON object")
            success, reason = apply_params_set(state, payload)
        except Exception as exc:  # noqa: BLE001
            success, reason = False, f"payload_parse_failed:{exc}"

        ack_topic = args.ack_topic_template.format(device_id=device_id)
        ack = build_ack_payload(state, success=success, reason=reason)
        publish_json(ack_topic, ack)
        print(
            f"[params/set] device={device_id} success={success} reason={reason} "
            f"target={ack['target_temp_c']:.2f} kp={ack['kp']:.3f} ki={ack['ki']:.3f} kd={ack['kd']:.3f}"
        )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print(f"[live-edge] devices={','.join(states)} interval={args.interval}s qos={qos}")
    for state in states.values():
        print(
            f"[live-edge] {state.device_id}: env={state.env.key} target={state.target_temp_c:.2f} "
            f"start={state.sensor_temp_c:.2f} params=({state.kp:.3f},{state.ki:.3f},{state.kd:.3f})"
        )

    client.connect(args.mqtt_host, int(args.mqtt_port), keepalive=30)
    client.loop_start()
    started = time.monotonic()
    tick = 0
    try:
        while not stop["flag"]:
            tick += 1
            now = time.monotonic()
            for state in states.values():
                telemetry = step_thermal_model(state, now, rng)
                topic = args.telemetry_topic_template.format(device_id=state.device_id)
                publish_json(topic, telemetry)
                if args.log_every > 0 and tick % args.log_every == 0:
                    print(
                        f"[telemetry] device={state.device_id} temp={telemetry['sensor_temp_c']:.2f} "
                        f"target={telemetry['target_temp_c']:.2f} error={telemetry['error_c']:.2f} "
                        f"pwm={telemetry['pwm_duty']} sat={telemetry['saturation_state']}"
                    )
            if args.seconds > 0 and time.monotonic() - started >= args.seconds:
                break
            time.sleep(max(0.05, float(args.interval)))
    finally:
        client.loop_stop()
        client.disconnect()
        print(f"[live-edge] stopped at {datetime.now(tz=timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
