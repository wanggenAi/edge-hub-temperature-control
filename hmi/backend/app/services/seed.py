from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text, select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.entities import (
    AIRecommendation,
    Device,
    DeviceAlarm,
    DeviceMetric,
    DeviceParameter,
    DeviceSummary,
    Role,
    User,
    UserDevice,
    UserRole,
)


ROLE_DATA = [
    ("admin", "Administrator"),
    ("operator", "Operator"),
    ("viewer", "Read-only Viewer"),
]


USER_DATA = [
    {"username": "admin", "email": "admin@edgehub.com", "password": "admin123", "roles": ["admin"]},
    {"username": "operator1", "email": "operator1@edgehub.com", "password": "operator123", "roles": ["operator"]},
    {"username": "viewer1", "email": "viewer1@edgehub.com", "password": "viewer123", "roles": ["viewer"]},
]


DEVICE_DATA = [
    {"code": "TC-101", "name": "Line 1 Oven", "line": "Line 1", "location": "Zone A", "current_temp": 36.8, "target_temp": 37.0, "pwm_output": 42.0, "is_alarm": False, "is_online": True},
    {"code": "TC-102", "name": "Line 1 Curing", "line": "Line 1", "location": "Zone B", "current_temp": 38.9, "target_temp": 37.0, "pwm_output": 71.0, "is_alarm": True, "is_online": True},
    {"code": "TC-201", "name": "Line 2 Tank", "line": "Line 2", "location": "Zone C", "current_temp": 34.4, "target_temp": 35.5, "pwm_output": 51.0, "is_alarm": False, "is_online": True},
    {"code": "TC-202", "name": "Line 2 Pipe", "line": "Line 2", "location": "Zone D", "current_temp": 26.1, "target_temp": 30.0, "pwm_output": 84.0, "is_alarm": True, "is_online": False},
    {"code": "TC-301", "name": "Line 3 Mixer", "line": "Line 3", "location": "Zone E", "current_temp": 31.5, "target_temp": 32.0, "pwm_output": 36.0, "is_alarm": False, "is_online": True},
]


PARAMETER_COLUMN_DEFAULTS: dict[str, str] = {
    "target_band": "0.5",
    "overshoot_limit_pct": "3.0",
    "saturation_warn_ratio": "0.3",
    "saturation_high_ratio": "0.6",
    "pwm_saturation_threshold": "85.0",
    "steady_window_samples": "12",
}


def ensure_runtime_schema(db: Session) -> None:
    """
    Keep SQLite schema forward-compatible for existing local databases without migrations.
    """
    existing_columns = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(device_parameters)")).fetchall()
    }
    for column, default in PARAMETER_COLUMN_DEFAULTS.items():
        if column in existing_columns:
            continue
        sql_type = "INTEGER" if column == "steady_window_samples" else "FLOAT"
        db.execute(
            text(
                f"ALTER TABLE device_parameters "
                f"ADD COLUMN {column} {sql_type} NOT NULL DEFAULT {default}"
            )
        )
    db.commit()


def seed_database(db: Session) -> None:
    ensure_runtime_schema(db)

    if db.scalar(select(User.id).limit(1)):
        return

    roles: dict[str, Role] = {}
    for name, description in ROLE_DATA:
        role = Role(name=name, description=description)
        db.add(role)
        db.flush()
        roles[name] = role

    users: dict[str, User] = {}
    for item in USER_DATA:
        user = User(
            username=item["username"],
            email=item["email"],
            password_hash=get_password_hash(item["password"]),
        )
        db.add(user)
        db.flush()
        for role_name in item["roles"]:
            db.add(UserRole(user_id=user.id, role_id=roles[role_name].id))
        users[user.username] = user

    now = datetime.utcnow()
    devices: list[Device] = []
    for idx, item in enumerate(DEVICE_DATA):
        device = Device(**item, status="active")
        db.add(device)
        db.flush()

        db.add(
            DeviceParameter(
                device_id=device.id,
                kp=2.6 + idx * 0.1,
                ki=0.35 + idx * 0.05,
                kd=0.1,
                control_mode="PID",
                target_band=0.5,
                overshoot_limit_pct=3.0,
                saturation_warn_ratio=0.3,
                saturation_high_ratio=0.6,
                pwm_saturation_threshold=85.0,
                steady_window_samples=12,
                sampling_period_ms=250,
                upload_period_s=10,
                updated_by="seed",
            )
        )

        generated_metrics: list[dict] = []
        for i in range(24):
            t = now - timedelta(minutes=24 - i)
            current = device.current_temp + (i - 12) * 0.03
            target = device.target_temp
            err = round(current - target, 3)
            pwm = max(0.0, min(100.0, device.pwm_output + (12 - i) * 0.4))
            generated_metrics.append(
                {
                    "timestamp": t,
                    "current_temp": round(current, 3),
                    "target_temp": round(target, 3),
                    "error": err,
                    "pwm_output": round(pwm, 2),
                }
            )
            db.add(
                DeviceMetric(
                    device_id=device.id,
                    timestamp=t,
                    current_temp=round(current, 3),
                    target_temp=round(target, 3),
                    error=err,
                    pwm_output=round(pwm, 2),
                    status="active" if device.is_online else "offline",
                    in_spec=abs(err) <= 0.5,
                    is_alarm=abs(err) > 1.5,
                )
            )

        for window_idx in range(4):
            chunk = generated_metrics[window_idx * 6 : (window_idx + 1) * 6]
            if not chunk:
                continue
            avg_temp = sum(x["current_temp"] for x in chunk) / len(chunk)
            avg_error = sum(abs(x["error"]) for x in chunk) / len(chunk)
            max_overshoot_pct = (
                max(max(0.0, (x["current_temp"] - x["target_temp"]) / max(x["target_temp"], 0.001)) for x in chunk)
                * 100.0
            )
            saturation_ratio = sum(1 for x in chunk if x["pwm_output"] >= 85.0) / len(chunk)
            if saturation_ratio >= 0.6:
                trigger = "saturation_window"
            elif avg_error > 0.5:
                trigger = "error_window"
            else:
                trigger = "steady_state_window"

            db.add(
                DeviceSummary(
                    device_id=device.id,
                    window_start=chunk[0]["timestamp"],
                    window_end=chunk[-1]["timestamp"],
                    sample_count=len(chunk),
                    avg_temp=round(avg_temp, 3),
                    avg_error=round(avg_error, 3),
                    max_overshoot_pct=round(max_overshoot_pct, 3),
                    saturation_ratio=round(saturation_ratio, 3),
                    trigger_event=trigger,
                )
            )

        db.add(
            AIRecommendation(
                device_id=device.id,
                reason="Steady-state error slightly above target" if device.is_alarm else "Trend stable with low oscillation",
                suggestion="Kp:+0.2 Ki:+0.05 Kd:0" if device.is_alarm else "Keep current gain set and monitor 15 minutes",
                confidence=0.78 if device.is_alarm else 0.84,
                risk="Minor overshoot risk" if device.is_alarm else "Low",
                last_run_at=now - timedelta(minutes=5),
            )
        )

        if device.is_alarm:
            db.add(
                DeviceAlarm(
                    device_id=device.id,
                    level="critical" if not device.is_online else "warning",
                    title="Temperature Out of Range",
                    message=f"{device.code} exceeded safe target band; verify sensor and load.",
                    is_active=True,
                )
            )

        devices.append(device)

    db.flush()

    admin = users["admin"]
    operator = users["operator1"]
    viewer = users["viewer1"]

    for device in devices:
        db.add(UserDevice(user_id=admin.id, device_id=device.id))

    for device in devices[:3]:
        db.add(UserDevice(user_id=operator.id, device_id=device.id))

    for device in devices[3:]:
        db.add(UserDevice(user_id=viewer.id, device_id=device.id))

    db.commit()
