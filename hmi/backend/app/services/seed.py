from __future__ import annotations

from datetime import datetime, timedelta
import math

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.entities import (
    AIRecommendation,
    AlarmRule,
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
from app.services.ai.enums import ExpectedEffect, ProblemType, RiskLevel
from app.services.ai.recommendation_service import RecommendationService
from app.services.ai.schemas import PIDParams, RecommendationGenerateOutput


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


DEFAULT_ALARM_RULES = [
    {
        "rule_code": "out_of_band",
        "name": "Out of Band",
        "target": "temperature_error",
        "operator": ">",
        "threshold": "0.5",
        "hold_seconds": 30,
        "severity": "warning",
        "enabled": True,
        "scope_type": "global",
        "scope_value": "*",
    },
    {
        "rule_code": "sensor_invalid",
        "name": "Sensor Invalid",
        "target": "sensor_valid",
        "operator": "==",
        "threshold": "false",
        "hold_seconds": 10,
        "severity": "critical",
        "enabled": True,
        "scope_type": "global",
        "scope_value": "*",
    },
    {
        "rule_code": "high_saturation",
        "name": "High Saturation",
        "target": "pwm_output",
        "operator": ">=",
        "threshold": "85",
        "hold_seconds": 60,
        "severity": "warning",
        "enabled": True,
        "scope_type": "global",
        "scope_value": "*",
    },
    {
        "rule_code": "param_apply_failed",
        "name": "Param Apply Failed",
        "target": "params_ack",
        "operator": "==",
        "threshold": "failed",
        "hold_seconds": 5,
        "severity": "warning",
        "enabled": True,
        "scope_type": "global",
        "scope_value": "*",
    },
    {
        "rule_code": "device_offline",
        "name": "Device Offline",
        "target": "telemetry_gap",
        "operator": ">",
        "threshold": "60",
        "hold_seconds": 60,
        "severity": "critical",
        "enabled": True,
        "scope_type": "global",
        "scope_value": "*",
    },
]

PREVIEW_AI_CASES = [
    {
        # Legacy demo code kept for backward compatibility in existing UIs.
        "code": "TC-PREVIEW-SLOW-01",
        "name": "Preview Slow-Response Cell",
        "line": "Preview Lab",
        "location": "Simulation Rack",
        "target_temp": 38.0,
        "current_temp": 33.4,
        "pwm_output": 96.0,
        "is_alarm": True,
        "primary_problem_type": ProblemType.SATURATION_LIMITED,
        "secondary_problem_types": [ProblemType.SLOW_RESPONSE],
        "problem_flags": {
            "saturation_limited": True,
            "severe_saturation": True,
            "oscillation": False,
            "overshoot_high": False,
            "steady_state_error": False,
            "slow_response": True,
        },
        "expected_effect": ExpectedEffect.SPEED_UP_RESPONSE,
        "risk_level": RiskLevel.MEDIUM,
        "confidence": 0.89,
        "recommend_scale": {"kp": 1.85, "ki": 1.6, "kd_add": 0.1},
        "telemetry": {"start_error": -4.8, "end_error": -2.6, "osc_amp": 0.2, "osc_cycles": 1.5, "pwm_base": 94.0, "pwm_amp": 8.0},
    },
    {
        # Legacy demo code kept for backward compatibility in existing UIs.
        "code": "TC-PREVIEW-OSC-01",
        "name": "Preview Oscillation Cell",
        "line": "Preview Lab",
        "location": "Simulation Rack",
        "target_temp": 37.0,
        "current_temp": 37.6,
        "pwm_output": 66.0,
        "is_alarm": True,
        "primary_problem_type": ProblemType.OSCILLATION,
        "secondary_problem_types": [ProblemType.OVERSHOOT_HIGH],
        "problem_flags": {
            "saturation_limited": False,
            "severe_saturation": False,
            "oscillation": True,
            "overshoot_high": True,
            "steady_state_error": False,
            "slow_response": False,
        },
        "expected_effect": ExpectedEffect.REDUCE_OSCILLATION,
        "risk_level": RiskLevel.MEDIUM,
        "confidence": 0.86,
        "recommend_scale": {"kp": 0.72, "ki": 0.6, "kd_add": 0.16},
        "telemetry": {"start_error": 1.9, "end_error": 0.8, "osc_amp": 1.4, "osc_cycles": 7.0, "pwm_base": 64.0, "pwm_amp": 20.0},
    },
    {
        "code": "TC-PREVIEW-SAT-SLOW",
        "name": "Preview Saturation + Slow",
        "line": "AI Preview",
        "location": "Demo A",
        "target_temp": 38.0,
        "current_temp": 33.4,
        "pwm_output": 96.0,
        "is_alarm": True,
        "primary_problem_type": ProblemType.SATURATION_LIMITED,
        "secondary_problem_types": [ProblemType.SLOW_RESPONSE],
        "problem_flags": {
            "saturation_limited": True,
            "severe_saturation": True,
            "oscillation": False,
            "overshoot_high": False,
            "steady_state_error": False,
            "slow_response": True,
        },
        "expected_effect": ExpectedEffect.SPEED_UP_RESPONSE,
        "risk_level": RiskLevel.MEDIUM,
        "confidence": 0.89,
        "recommend_scale": {"kp": 1.85, "ki": 1.6, "kd_add": 0.1},
        "telemetry": {"start_error": -4.8, "end_error": -2.6, "osc_amp": 0.2, "osc_cycles": 1.5, "pwm_base": 94.0, "pwm_amp": 8.0},
    },
    {
        "code": "TC-PREVIEW-OSC-OVS",
        "name": "Preview Oscillation + Overshoot",
        "line": "AI Preview",
        "location": "Demo B",
        "target_temp": 37.0,
        "current_temp": 37.6,
        "pwm_output": 66.0,
        "is_alarm": True,
        "primary_problem_type": ProblemType.OSCILLATION,
        "secondary_problem_types": [ProblemType.OVERSHOOT_HIGH],
        "problem_flags": {
            "saturation_limited": False,
            "severe_saturation": False,
            "oscillation": True,
            "overshoot_high": True,
            "steady_state_error": False,
            "slow_response": False,
        },
        "expected_effect": ExpectedEffect.REDUCE_OSCILLATION,
        "risk_level": RiskLevel.MEDIUM,
        "confidence": 0.86,
        "recommend_scale": {"kp": 0.72, "ki": 0.6, "kd_add": 0.16},
        "telemetry": {"start_error": 1.9, "end_error": 0.8, "osc_amp": 1.4, "osc_cycles": 7.0, "pwm_base": 64.0, "pwm_amp": 20.0},
    },
    {
        "code": "TC-PREVIEW-SSE",
        "name": "Preview Steady-State Error",
        "line": "AI Preview",
        "location": "Demo C",
        "target_temp": 36.5,
        "current_temp": 35.1,
        "pwm_output": 74.0,
        "is_alarm": True,
        "primary_problem_type": ProblemType.STEADY_STATE_ERROR,
        "secondary_problem_types": [],
        "problem_flags": {
            "saturation_limited": False,
            "severe_saturation": False,
            "oscillation": False,
            "overshoot_high": False,
            "steady_state_error": True,
            "slow_response": False,
        },
        "expected_effect": ExpectedEffect.REDUCE_STEADY_STATE_ERROR,
        "risk_level": RiskLevel.LOW,
        "confidence": 0.83,
        "recommend_scale": {"kp": 1.3, "ki": 1.35, "kd_add": 0.06},
        "telemetry": {"start_error": -1.7, "end_error": -1.0, "osc_amp": 0.12, "osc_cycles": 1.2, "pwm_base": 73.0, "pwm_amp": 7.0},
    },
    {
        "code": "TC-PREVIEW-NORMAL",
        "name": "Preview Near-Normal",
        "line": "AI Preview",
        "location": "Demo D",
        "target_temp": 37.2,
        "current_temp": 37.1,
        "pwm_output": 46.0,
        "is_alarm": False,
        "primary_problem_type": ProblemType.NORMAL,
        "secondary_problem_types": [],
        "problem_flags": {
            "saturation_limited": False,
            "severe_saturation": False,
            "oscillation": False,
            "overshoot_high": False,
            "steady_state_error": False,
            "slow_response": False,
        },
        "expected_effect": ExpectedEffect.KEEP_STABLE,
        "risk_level": RiskLevel.LOW,
        "confidence": 0.93,
        "recommend_scale": {"kp": 1.0, "ki": 1.0, "kd_add": 0.0},
        "telemetry": {"start_error": -0.22, "end_error": 0.12, "osc_amp": 0.08, "osc_cycles": 0.8, "pwm_base": 46.0, "pwm_amp": 4.0},
    },
]


def seed_alarm_rules(db: Session) -> None:
    existing = {
        code
        for code in db.scalars(select(AlarmRule.rule_code)).all()
    }
    for row in DEFAULT_ALARM_RULES:
        if row["rule_code"] in existing:
            continue
        db.add(AlarmRule(**row, updated_by="seed"))
    db.commit()


def seed_demo_data(db: Session) -> None:
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
                control_mode="pid_control",
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
                    rule_code="device_offline" if not device.is_online else "out_of_band",
                    source="device_status" if not device.is_online else "rule_engine",
                    title="Device Offline" if not device.is_online else "Temperature Out of Range",
                    message=(
                        f"{device.code} has no telemetry heartbeat."
                        if not device.is_online
                        else f"{device.code} exceeded safe target band; verify sensor and load."
                    ),
                    is_active=True,
                    acknowledged=False,
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


def _build_preview_series(case: dict, *, points: int = 24) -> list[dict]:
    target = float(case["target_temp"])
    telemetry = case["telemetry"]
    start_error = float(telemetry["start_error"])
    end_error = float(telemetry["end_error"])
    osc_amp = float(telemetry["osc_amp"])
    osc_cycles = float(telemetry["osc_cycles"])
    pwm_base = float(telemetry["pwm_base"])
    pwm_amp = float(telemetry["pwm_amp"])
    now = datetime.utcnow()
    out: list[dict] = []
    for idx in range(points):
        progress = 0.0 if points <= 1 else float(idx) / float(points - 1)
        phase = progress * osc_cycles * math.tau
        error = start_error + (end_error - start_error) * progress + osc_amp * math.sin(phase)
        temp = target + error
        pwm = max(0.0, min(100.0, pwm_base + pwm_amp * abs(math.sin(phase + math.pi / 8))))
        out.append(
            {
                "timestamp": now - timedelta(minutes=points - idx),
                "current_temp": round(temp, 3),
                "target_temp": round(target, 3),
                "error": round(error, 3),
                "pwm_output": round(pwm, 2),
            }
        )
    return out


def seed_preview_ai_demo_data(db: Session) -> None:
    recommendation_service = RecommendationService()
    users = db.scalars(select(User)).all()

    for idx, case in enumerate(PREVIEW_AI_CASES):
        code = str(case["code"])
        device = db.scalar(select(Device).where(Device.code == code))
        if device is None:
            device = Device(
                code=code,
                name=str(case["name"]),
                line=str(case["line"]),
                location=str(case["location"]),
                status="active",
                current_temp=float(case["current_temp"]),
                target_temp=float(case["target_temp"]),
                pwm_output=float(case["pwm_output"]),
                is_alarm=bool(case["is_alarm"]),
                is_online=True,
            )
            db.add(device)
            db.flush()
        else:
            device.name = str(case["name"])
            device.line = str(case["line"])
            device.location = str(case["location"])
            device.status = "active"
            device.current_temp = float(case["current_temp"])
            device.target_temp = float(case["target_temp"])
            device.pwm_output = float(case["pwm_output"])
            device.is_alarm = bool(case["is_alarm"])
            device.is_online = True

        db.execute(delete(DeviceMetric).where(DeviceMetric.device_id == device.id))
        db.execute(delete(DeviceSummary).where(DeviceSummary.device_id == device.id))
        db.execute(delete(AIRecommendation).where(AIRecommendation.device_id == device.id))
        db.execute(delete(DeviceAlarm).where(DeviceAlarm.device_id == device.id))
        db.flush()

        base_params = PIDParams(kp=round(2.4 + idx * 0.18, 4), ki=round(0.28 + idx * 0.06, 4), kd=0.1)
        param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
        if param is None:
            param = DeviceParameter(
                device_id=device.id,
                kp=base_params.kp,
                ki=base_params.ki,
                kd=base_params.kd,
                control_mode="pid_control",
                target_band=0.5,
                overshoot_limit_pct=3.0,
                saturation_warn_ratio=0.3,
                saturation_high_ratio=0.6,
                pwm_saturation_threshold=85.0,
                steady_window_samples=12,
                sampling_period_ms=250,
                upload_period_s=10,
                updated_by="seed_preview_ai_demo",
            )
            db.add(param)
        else:
            param.kp = base_params.kp
            param.ki = base_params.ki
            param.kd = base_params.kd
            param.control_mode = "pid_control"
            param.target_band = 0.5
            param.overshoot_limit_pct = 3.0
            param.saturation_warn_ratio = 0.3
            param.saturation_high_ratio = 0.6
            param.pwm_saturation_threshold = 85.0
            param.steady_window_samples = 12
            param.sampling_period_ms = 250
            param.upload_period_s = 10
            param.updated_by = "seed_preview_ai_demo"

        metrics = _build_preview_series(case)
        for point in metrics:
            err = float(point["error"])
            db.add(
                DeviceMetric(
                    device_id=device.id,
                    timestamp=point["timestamp"],
                    current_temp=float(point["current_temp"]),
                    target_temp=float(point["target_temp"]),
                    error=err,
                    pwm_output=float(point["pwm_output"]),
                    status="active",
                    in_spec=abs(err) <= 0.5,
                    is_alarm=abs(err) > 1.5,
                )
            )

        for window_idx in range(4):
            chunk = metrics[window_idx * 6 : (window_idx + 1) * 6]
            if not chunk:
                continue
            avg_temp = sum(x["current_temp"] for x in chunk) / len(chunk)
            avg_error = sum(abs(x["error"]) for x in chunk) / len(chunk)
            max_overshoot_pct = (
                max(max(0.0, (x["current_temp"] - x["target_temp"]) / max(x["target_temp"], 0.001)) for x in chunk)
                * 100.0
            )
            saturation_ratio = sum(1 for x in chunk if x["pwm_output"] >= 85.0) / len(chunk)
            trigger = (
                "saturation_window"
                if saturation_ratio >= 0.6
                else "error_window"
                if avg_error > 0.5
                else "steady_state_window"
            )
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

        scale = case["recommend_scale"]
        recommended = PIDParams(
            kp=round(base_params.kp * float(scale["kp"]), 4),
            ki=round(base_params.ki * float(scale["ki"]), 4),
            kd=round(base_params.kd + float(scale["kd_add"]), 4),
        )
        output = RecommendationGenerateOutput(
            problem_type=case["primary_problem_type"],
            primary_problem_type=case["primary_problem_type"],
            secondary_problem_types=case["secondary_problem_types"],
            problem_flags=case["problem_flags"],
            confidence=float(case["confidence"]),
            risk_level=case["risk_level"],
            requires_confirmation=case["primary_problem_type"] != ProblemType.NORMAL,
            current_params=base_params,
            recommended_params=recommended,
            delta=PIDParams(
                kp=round(recommended.kp - base_params.kp, 4),
                ki=round(recommended.ki - base_params.ki, 4),
                kd=round(recommended.kd - base_params.kd, 4),
            ),
            expected_effect=case["expected_effect"],
            evidence={
                "rule_saturation_limited": bool(case["problem_flags"].get("saturation_limited")),
                "rule_severe_saturation": bool(case["problem_flags"].get("severe_saturation")),
                "rule_oscillation": bool(case["problem_flags"].get("oscillation")),
                "rule_overshoot_high": bool(case["problem_flags"].get("overshoot_high")),
                "rule_steady_state_error": bool(case["problem_flags"].get("steady_state_error")),
                "rule_slow_response": bool(case["problem_flags"].get("slow_response")),
                "mean_error": round(sum(x["error"] for x in metrics) / max(1, len(metrics)), 4),
                "mean_abs_error": round(sum(abs(x["error"]) for x in metrics) / max(1, len(metrics)), 4),
                "error_std": round(math.sqrt(sum((x["error"] ** 2) for x in metrics) / max(1, len(metrics))), 4),
                "temp_swing": round(max(x["current_temp"] for x in metrics) - min(x["current_temp"] for x in metrics), 4),
                "pwm_mean": round(sum(x["pwm_output"] for x in metrics) / max(1, len(metrics)), 4),
                "pwm_max": round(max(x["pwm_output"] for x in metrics), 4),
                "zero_crossings": sum(
                    1
                    for i in range(1, len(metrics))
                    if (metrics[i - 1]["error"] > 0 and metrics[i]["error"] < 0)
                    or (metrics[i - 1]["error"] < 0 and metrics[i]["error"] > 0)
                ),
                "in_band_ratio": round(sum(1 for x in metrics if abs(x["error"]) <= 0.5) / max(1, len(metrics)), 4),
                "overshoot_pct": round(
                    max(max(0.0, (x["current_temp"] - x["target_temp"]) / max(x["target_temp"], 0.001)) for x in metrics)
                    * 100.0,
                    4,
                ),
                "settling_sec": None,
                "saturation_ratio": round(sum(1 for x in metrics if x["pwm_output"] >= 85.0) / max(1, len(metrics)), 4),
            },
            generated_at=datetime.utcnow() - timedelta(minutes=4),
        )
        reason, suggestion, risk = recommendation_service.to_storage_fields(output)
        db.add(
            AIRecommendation(
                device_id=device.id,
                reason=reason,
                suggestion=suggestion,
                confidence=float(case["confidence"]),
                risk=risk,
                last_run_at=output.generated_at,
            )
        )

        for user in users:
            exists = db.scalar(
                select(UserDevice.id).where(UserDevice.user_id == user.id, UserDevice.device_id == device.id)
            )
            if not exists:
                db.add(UserDevice(user_id=user.id, device_id=device.id))

    db.commit()


def seed_database(
    db: Session,
    *,
    with_default_alarm_rules: bool = True,
    with_demo_data: bool = False,
    with_preview_ai_demo: bool = False,
) -> None:
    if with_default_alarm_rules:
        seed_alarm_rules(db)
    if with_demo_data:
        seed_demo_data(db)
    if with_preview_ai_demo:
        seed_preview_ai_demo_data(db)
