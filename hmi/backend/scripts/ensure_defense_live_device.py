#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select


CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import Device, DeviceParameter, User, UserDevice  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure the Wokwi/live defense device exists in HMI PostgreSQL.")
    parser.add_argument("--device-code", default="edge-node-001")
    parser.add_argument("--name", default="Defense Live Wokwi Edge Node")
    parser.add_argument("--line", default="Defense Live Line")
    parser.add_argument("--location", default="Wokwi / Hardware Loop")
    parser.add_argument("--target-temp", type=float, default=23.0)
    parser.add_argument("--current-temp", type=float, default=23.0)
    parser.add_argument("--kp", type=float, default=120.0)
    parser.add_argument("--ki", type=float, default=12.0)
    parser.add_argument("--kd", type=float, default=0.0)
    parser.add_argument("--control-mode", default="pid_control")
    parser.add_argument("--sampling-period-ms", type=int, default=1000)
    parser.add_argument("--updated-by", default="defense_live_setup")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        device = db.scalar(select(Device).where(Device.code == args.device_code))
        created = False
        if device is None:
            device = Device(code=args.device_code, name=args.name)
            db.add(device)
            db.flush()
            created = True

        device.name = args.name
        device.line = args.line
        device.location = args.location
        device.status = "active"
        device.current_temp = float(args.current_temp)
        device.target_temp = float(args.target_temp)
        device.pwm_output = 0.0
        device.is_alarm = False
        # DataHub device_status is the live authority once telemetry arrives.
        device.is_online = False
        device.updated_at = datetime.utcnow()

        param = db.scalar(select(DeviceParameter).where(DeviceParameter.device_id == device.id))
        if param is None:
            param = DeviceParameter(device_id=device.id)
            db.add(param)
            db.flush()
        param.kp = float(args.kp)
        param.ki = float(args.ki)
        param.kd = float(args.kd)
        param.control_mode = str(args.control_mode)
        param.target_band = 0.5
        param.overshoot_limit_pct = 3.0
        param.saturation_warn_ratio = 0.3
        param.saturation_high_ratio = 0.6
        param.pwm_saturation_threshold = 85.0
        param.steady_window_samples = 12
        param.sampling_period_ms = int(args.sampling_period_ms)
        param.upload_period_s = max(1, int(round(args.sampling_period_ms / 1000.0)))
        param.updated_at = datetime.utcnow()
        param.updated_by = args.updated_by

        linked_users = 0
        for user in db.scalars(select(User)).all():
            exists = db.scalar(
                select(UserDevice.id).where(UserDevice.user_id == user.id, UserDevice.device_id == device.id)
            )
            if not exists:
                db.add(UserDevice(user_id=user.id, device_id=device.id))
                linked_users += 1

        db.commit()
        print(
            "[ok] defense live device "
            f"{'created' if created else 'updated'} code={device.code} id={device.id} "
            f"target={device.target_temp:.2f} kp={param.kp:.2f} ki={param.ki:.2f} kd={param.kd:.2f} "
            f"linked_users={linked_users}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
