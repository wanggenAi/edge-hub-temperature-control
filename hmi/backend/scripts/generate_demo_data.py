from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import Device, DeviceAlarm, DeviceMetric, DeviceParameter, DeviceSummary


ALARM_TEMPLATES = [
    ("out_of_band", "rule_engine", "warning", "Out of Band", "Temperature remains outside target band."),
    ("sensor_invalid", "telemetry", "critical", "Sensor Invalid", "Sensor signal invalid or disconnected."),
    ("high_saturation", "telemetry", "warning", "High Saturation", "PWM remains high for too long."),
    ("param_apply_failed", "params_ack", "warning", "Param Apply Failed", "Controller rejected parameter update."),
    ("device_offline", "device_status", "critical", "Device Offline", "No telemetry for configured timeout."),
]


def calc_settling_like_trigger(avg_error: float, saturation_ratio: float) -> str:
    if saturation_ratio >= 0.6:
        return "saturation_window"
    if avg_error > 0.5:
        return "error_window"
    return "steady_state_window"


def generate_for_device(
    device: Device,
    param: DeviceParameter,
    windows_per_device: int,
    samples_per_window: int,
    minutes_step: int,
    alarm_probability: float,
) -> tuple[int, int, int]:
    now = datetime.utcnow()
    metrics_added = 0
    summaries_added = 0
    alarms_added = 0

    base_temp = device.current_temp
    target = device.target_temp
    base_pwm = device.pwm_output

    for w in range(windows_per_device):
        # Build a historical window going backwards in time.
        window_end = now - timedelta(minutes=w * samples_per_window * minutes_step)
        window_start = window_end - timedelta(minutes=(samples_per_window - 1) * minutes_step)
        points: List[dict] = []

        for i in range(samples_per_window):
            ts = window_start + timedelta(minutes=i * minutes_step)
            phase = (w * samples_per_window + i) / 6.0
            # Small oscillation + trend to simulate realistic control drift.
            drift = math.sin(phase) * 0.35 + math.cos(phase / 2.5) * 0.12
            current = base_temp + drift
            error = current - target
            pwm = max(0.0, min(100.0, base_pwm + error * 12.0 + math.sin(phase * 1.7) * 6.0))
            in_spec = abs(error) <= param.target_band
            is_alarm_point = abs(error) > max(1.5, param.target_band * 3)

            points.append(
                {
                    "timestamp": ts,
                    "current_temp": round(current, 3),
                    "target_temp": round(target, 3),
                    "error": round(error, 3),
                    "pwm_output": round(pwm, 2),
                    "in_spec": in_spec,
                    "is_alarm": is_alarm_point,
                }
            )

        for p in points:
            metric = DeviceMetric(
                device_id=device.id,
                timestamp=p["timestamp"],
                current_temp=p["current_temp"],
                target_temp=p["target_temp"],
                error=p["error"],
                pwm_output=p["pwm_output"],
                status="active" if device.is_online else "offline",
                in_spec=p["in_spec"],
                is_alarm=p["is_alarm"],
            )
            db_add(metric)
            metrics_added += 1

        avg_temp = sum(p["current_temp"] for p in points) / len(points)
        avg_error = sum(abs(p["error"]) for p in points) / len(points)
        max_overshoot_pct = (
            max(max(0.0, (p["current_temp"] - p["target_temp"]) / max(p["target_temp"], 0.001)) for p in points)
            * 100.0
        )
        saturation_ratio = sum(1 for p in points if p["pwm_output"] >= param.pwm_saturation_threshold) / len(points)
        trigger = calc_settling_like_trigger(avg_error, saturation_ratio)

        summary = DeviceSummary(
            device_id=device.id,
            window_start=points[0]["timestamp"],
            window_end=points[-1]["timestamp"],
            sample_count=len(points),
            avg_temp=round(avg_temp, 3),
            avg_error=round(avg_error, 3),
            max_overshoot_pct=round(max_overshoot_pct, 3),
            saturation_ratio=round(saturation_ratio, 3),
            trigger_event=trigger,
        )
        db_add(summary)
        summaries_added += 1

        should_add_alarm = random.random() < alarm_probability or trigger in {"error_window", "saturation_window"}
        if should_add_alarm:
            rule_code, source, level, title, message = random.choice(ALARM_TEMPLATES)
            alarm = DeviceAlarm(
                device_id=device.id,
                level=level,
                rule_code=rule_code,
                source=source,
                title=title,
                message=f"{device.code}: {message}",
                is_active=random.random() < 0.45,
                acknowledged=random.random() < 0.3,
                created_at=points[-1]["timestamp"],
                cleared_at=None if random.random() < 0.45 else points[-1]["timestamp"] + timedelta(minutes=random.randint(2, 40)),
            )
            db_add(alarm)
            alarms_added += 1

    return metrics_added, summaries_added, alarms_added


_SESSION = None


def db_add(model) -> None:
    if _SESSION is None:
        raise RuntimeError("Session not initialized")
    _SESSION.add(model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo alarms/history data.")
    parser.add_argument("--windows-per-device", type=int, default=24)
    parser.add_argument("--samples-per-window", type=int, default=8)
    parser.add_argument("--minutes-step", type=int, default=2)
    parser.add_argument("--alarm-probability", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    global _SESSION
    db = SessionLocal()
    _SESSION = db
    try:
        devices = db.scalars(select(Device).order_by(Device.id.asc())).all()
        if not devices:
            print("No devices found. Start backend once to run initial seed.")
            return

        metrics_total = 0
        summaries_total = 0
        alarms_total = 0

        for device in devices:
            param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
            if not param:
                continue
            m, s, a = generate_for_device(
                device=device,
                param=param,
                windows_per_device=max(1, args.windows_per_device),
                samples_per_window=max(3, args.samples_per_window),
                minutes_step=max(1, args.minutes_step),
                alarm_probability=max(0.0, min(1.0, args.alarm_probability)),
            )
            metrics_total += m
            summaries_total += s
            alarms_total += a

            if a > 0:
                device.is_alarm = True

        db.commit()
        print(
            f"Demo data generated: metrics={metrics_total}, summaries={summaries_total}, alarms={alarms_total}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
