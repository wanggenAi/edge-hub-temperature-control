#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.tdengine_client import TdengineClient  # noqa: E402


tdengine = TdengineClient()


@dataclass
class ApiResponse:
    status: int
    body: Any
    text: str


def json_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 12.0,
) -> ApiResponse:
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            body = json.loads(text) if text else None
            return ApiResponse(status=response.status, body=body, text=text)
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text) if text else None
        except json.JSONDecodeError:
            body = None
        return ApiResponse(status=exc.code, body=body, text=text)
    except URLError as exc:
        raise SystemExit(f"[fail] api unavailable url={url} reason={exc.reason}") from exc


def sql_value(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def row_dict(sql: str) -> dict[str, Any] | None:
    result = tdengine.query(sql)
    if not result.rows:
        return None
    return tdengine.row_to_dict(result.columns, result.rows[0])


def ts_to_ms(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def nearly_equal(left: Any, right: float, tol: float) -> bool:
    try:
        return abs(float(left) - float(right)) <= tol
    except (TypeError, ValueError):
        return False


def wait_for_row(label: str, query_factory, predicate, timeout_s: float, interval_s: float) -> tuple[bool, dict[str, Any] | None]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        row = row_dict(query_factory())
        if row is not None:
            last = row
            if predicate(row):
                return True, row
        time.sleep(interval_s)
    return False, last


def find_device(api_base: str, token: str, device_code: str) -> dict[str, Any]:
    response = json_request("GET", f"{api_base}/devices", token=token)
    if response.status != 200 or not isinstance(response.body, list):
        raise SystemExit(f"[fail] cannot list devices status={response.status} body={response.text}")
    for device in response.body:
        if str(device.get("code")) == device_code:
            return device
    raise SystemExit(f"[fail] device not found code={device_code}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify HMI -> MQTT -> edge ACK -> DataHub -> TDengine -> HMI target update flow."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--device-code", default="edge-node-001")
    parser.add_argument("--target-temp", type=float, required=True)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--tolerance", type=float, default=0.01)
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="Publish even when DataHub currently reports the device offline.",
    )
    args = parser.parse_args()

    api_base = args.api_base.rstrip("/")
    target = float(args.target_temp)
    tol = max(0.001, float(args.tolerance))
    device_code_sql = sql_value(args.device_code)

    login = json_request(
        "POST",
        f"{api_base}/auth/login",
        payload={"username": args.username, "password": args.password},
    )
    if login.status != 200 or not isinstance(login.body, dict) or not login.body.get("access_token"):
        print(f"[fail] login status={login.status} body={login.text}")
        return 2
    token = str(login.body["access_token"])
    print("[ok] hmi login")

    device = find_device(api_base, token, args.device_code)
    device_id = int(device["id"])
    print(
        "[info] hmi device "
        f"id={device_id} code={args.device_code} target={device.get('target_temp')} online={device.get('is_online')}"
    )

    status_row = row_dict(
        "SELECT ts,last_seen_ts,online,status_reason,last_message_kind "
        f"FROM {settings.tdengine_database}.device_status "
        f"WHERE device_id={device_code_sql} ORDER BY ts DESC LIMIT 1"
    )
    if status_row:
        print(
            "[info] datahub status "
            f"online={status_row.get('online')} reason={status_row.get('status_reason')} "
            f"last_seen={status_row.get('last_seen_ts')}"
        )
        if status_row.get("online") is False and not args.allow_offline:
            print("[fail] device is offline; not publishing target update. Use --allow-offline to test publish-only path.")
            return 3

    params = json_request("GET", f"{api_base}/devices/{device_id}/parameters", token=token)
    if params.status != 200 or not isinstance(params.body, dict):
        print(f"[fail] read params status={params.status} body={params.text}")
        return 2
    param = params.body
    payload = {
        "target_temp": target,
        "kp": float(param["kp"]),
        "ki": float(param["ki"]),
        "kd": float(param["kd"]),
        "control_mode": str(param["control_mode"]),
        "sampling_period_ms": int(param["sampling_period_ms"]),
    }

    dispatch_ms = int(time.time() * 1000)
    print(f"[step] dispatch target={target:.2f} after_ms={dispatch_ms}")
    update = json_request(
        "PUT",
        f"{api_base}/devices/{device_id}/parameters",
        token=token,
        payload=payload,
        timeout=max(15.0, args.timeout + 5.0),
    )
    api_apply_ok = update.status == 200
    if api_apply_ok:
        print("[ok] hmi api apply returned 200")
    else:
        print(f"[warn] hmi api apply status={update.status} body={update.text}")

    params_set_ok, params_set_row = wait_for_row(
        "params_set",
        lambda: (
            "SELECT ts,target_temp_c,kp,ki,kd,control_mode "
            f"FROM {settings.tdengine_database}.params_set "
            f"WHERE device_id={device_code_sql} AND ts >= {dispatch_ms} "
            "ORDER BY ts DESC LIMIT 1"
        ),
        lambda row: nearly_equal(row.get("target_temp_c"), target, tol),
        args.timeout,
        args.interval,
    )
    if params_set_ok:
        print(f"[ok] datahub consumed params_set target={params_set_row.get('target_temp_c')} ts={params_set_row.get('ts')}")
    else:
        print(f"[fail] no matching params_set target={target:.2f}; latest_after_dispatch={params_set_row}")
        return 4

    ack_ok, ack_row = wait_for_row(
        "params_ack",
        lambda: (
            "SELECT ts,ack_type,success,reason,target_temp_c,kp,ki,kd,control_mode "
            f"FROM {settings.tdengine_database}.params_ack "
            f"WHERE device_id={device_code_sql} AND ts >= {dispatch_ms} "
            "ORDER BY ts DESC LIMIT 1"
        ),
        lambda row: bool(row.get("success") is True) and nearly_equal(row.get("target_temp_c"), target, tol),
        args.timeout,
        args.interval,
    )
    if ack_ok:
        print(
            f"[ok] edge ack target={ack_row.get('target_temp_c')} "
            f"ack_type={ack_row.get('ack_type')} reason={ack_row.get('reason')} ts={ack_row.get('ts')}"
        )
    else:
        print(f"[fail] no matching successful params_ack target={target:.2f}; latest_after_dispatch={ack_row}")
        return 5

    telemetry_ok, telemetry_row = wait_for_row(
        "telemetry",
        lambda: (
            "SELECT ts,target_temp_c,sensor_temp_c,sim_temp_c,pwm_duty,run_id "
            f"FROM {settings.tdengine_database}.telemetry "
            f"WHERE device_id={device_code_sql} AND ts >= {dispatch_ms} "
            "ORDER BY ts DESC LIMIT 1"
        ),
        lambda row: nearly_equal(row.get("target_temp_c"), target, tol),
        args.timeout,
        args.interval,
    )
    if telemetry_ok:
        print(
            f"[ok] telemetry target={telemetry_row.get('target_temp_c')} "
            f"sensor={telemetry_row.get('sensor_temp_c')} run={telemetry_row.get('run_id')}"
        )
    else:
        print(f"[fail] no matching telemetry target={target:.2f}; latest_after_dispatch={telemetry_row}")
        return 6

    detail = json_request("GET", f"{api_base}/devices/{device_id}", token=token)
    if detail.status != 200 or not isinstance(detail.body, dict):
        print(f"[fail] hmi detail status={detail.status} body={detail.text}")
        return 7
    if nearly_equal(detail.body.get("target_temp"), target, tol):
        print(
            f"[ok] hmi reflected target={detail.body.get('target_temp')} "
            f"online={detail.body.get('is_online')} current={detail.body.get('current_temp')}"
        )
    else:
        print(f"[fail] hmi target mismatch expected={target:.2f} detail={detail.text}")
        return 8

    print("[pass] target update closed-loop verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
