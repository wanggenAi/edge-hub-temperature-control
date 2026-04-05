#!/usr/bin/env python3
"""
Realtime TDengine feeder for HMI demo.

Examples:
  python scripts/tdengine_live_feed.py
  python scripts/tdengine_live_feed.py --interval 1.0 --devices TC-101,TC-102
  python scripts/tdengine_live_feed.py --seconds 120
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import random
import signal
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "hmi" / "backend" / "app.db"


def sanitize_identifier(value: str) -> str:
    text = "".join(ch.lower() if (ch.isalnum() or ch == "_") else "_" for ch in value).strip("_")
    if not text:
        text = "unknown"
    if text[0].isdigit():
        text = "t_" + text
    return text


def q(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


@dataclass
class TdengineClient:
    url: str
    database: str
    username: str
    password: str
    timeout_seconds: int = 8

    def query(self, sql: str) -> dict:
        endpoint = self.url.rstrip("/") + "/rest/sql"
        auth = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("utf-8")
        req = Request(endpoint, data=sql.encode("utf-8"), method="POST")
        req.add_header("Authorization", "Basic " + auth)
        req.add_header("Content-Type", "text/plain; charset=UTF-8")
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"TDengine unavailable: {exc}") from exc
        if int(body.get("code", -1)) != 0:
            raise RuntimeError(f"TDengine query failed: {body.get('desc', 'unknown')}")
        return body


@dataclass
class DeviceState:
    code: str
    target_temp: float
    kp: float
    ki: float
    kd: float
    phase: float
    tick: int = 0


def load_device_codes(db_path: Path) -> list[str]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("select code from devices order by id").fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows if row and row[0]]


def build_states(device_codes: Iterable[str]) -> list[DeviceState]:
    states: list[DeviceState] = []
    for idx, code in enumerate(device_codes):
        states.append(
            DeviceState(
                code=code,
                target_temp=36.0 + idx * 0.8,
                kp=110.0 + idx * 5,
                ki=10.0 + idx * 0.7,
                kd=0.0,
                phase=idx * 0.7,
            )
        )
    return states


def insert_telemetry(td: TdengineClient, state: DeviceState, ts_ms: int) -> None:
    wave = math.sin(state.tick / 12.0 + state.phase) * 0.85
    drift = math.sin(state.tick / 80.0 + state.phase) * 0.2
    sensor = state.target_temp + wave + drift
    sim_temp = sensor + math.sin(state.tick / 9.0) * 0.03
    error_c = sensor - state.target_temp
    pwm = max(15, min(98, int(52 + wave * 18 + abs(error_c) * 8)))
    saturation_state = "high" if pwm >= 85 else ("medium" if pwm >= 70 else "normal")
    fault_latched = "true" if abs(error_c) > 1.3 and (state.tick % 9 == 0) else "false"
    fault_reason = "temp_guard" if fault_latched == "true" else ""
    safety_output_forced_off = "true" if fault_latched == "true" else "false"

    table = f"{td.database}.telemetry_{sanitize_identifier(state.code)}"
    topic = f"edge/temperature/{state.code}/telemetry"
    sql = (
        f"INSERT INTO {table} USING {td.database}.telemetry TAGS ({q(state.code)}, {q(topic)}) "
        "(ts,uptime_ms,target_temp_c,sim_temp_c,sensor_temp_c,error_c,integral_error,control_output,pwm_duty,pwm_norm,"
        "control_period_ms,saturation_state,sensor_valid,run_id,control_mode,controller_version,kp,ki,kd,system_state,"
        "sensor_status,actual_dt_ms,dt_error_ms,wifi_connected,mqtt_connected,mqtt_reconnect_count,mqtt_publish_fail_count,"
        "safety_output_forced_off,fault_latched,fault_reason,software_max_safe_temp_c,has_pending_params,pending_params_age_ms) "
        f"VALUES ({ts_ms},{2_000_000 + state.tick * 1000},{state.target_temp:.4f},{sim_temp:.4f},{sensor:.4f},{error_c:.4f},"
        f"{error_c * 30:.4f},{pwm * 2.0:.4f},{pwm},{pwm/255.0:.5f},1000,{q(saturation_state)},true,{q('live-feed')},"
        f"{q('PI')},{q('pi_tuned_v3_2')},{state.kp:.4f},{state.ki:.4f},{state.kd:.4f},{q('running')},{q('ok')},1000,"
        f"{int(math.sin(state.tick / 6.0) * 70)},true,true,0,0,{safety_output_forced_off},{fault_latched},{q(fault_reason)},"
        "65.0,false,0)"
    )
    td.query(sql)


def insert_alarm_event(td: TdengineClient, state: DeviceState, ts_ms: int, triggered: bool) -> None:
    table = f"{td.database}.alarm_events_{sanitize_identifier(state.code)}_out_of_band"
    ev_type = "triggered" if triggered else "cleared"
    reason = "Out of Band" if triggered else "back in target band"
    duration = "NULL" if triggered else "180"
    context = q('{"error_c":0.74,"threshold":0.5}')
    sql = (
        f"INSERT INTO {table} USING {td.database}.alarm_events TAGS ({q(state.code)}, {q('out_of_band')}) "
        "(ts,severity,source,reason,alarm_event_type,triggered_at,duration_seconds,context_json) "
        f"VALUES ({ts_ms},{q('warning')},{q('rule_engine')},{q(reason)},{q(ev_type)},{ts_ms},{duration},{context})"
    )
    td.query(sql)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realtime TDengine telemetry feeder for HMI demo.")
    parser.add_argument("--url", default="http://127.0.0.1:6041", help="TDengine REST base URL")
    parser.add_argument("--database", default="edgehub", help="TDengine database")
    parser.add_argument("--username", default="root", help="TDengine username")
    parser.add_argument("--password", default="taosdata", help="TDengine password")
    parser.add_argument("--interval", type=float, default=1.0, help="Insert interval seconds")
    parser.add_argument("--seconds", type=int, default=0, help="Run duration; 0 = forever")
    parser.add_argument(
        "--devices",
        default="",
        help="Comma-separated device codes. Empty means auto-load from hmi/backend/app.db",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    td = TdengineClient(
        url=args.url,
        database=args.database,
        username=args.username,
        password=args.password,
    )
    device_codes = [x.strip() for x in args.devices.split(",") if x.strip()]
    if not device_codes:
        device_codes = load_device_codes(DEFAULT_DB_PATH)
    if not device_codes:
        device_codes = ["TC-101", "TC-102", "TC-201", "TC-202"]

    states = build_states(device_codes)
    stop = {"flag": False}

    def _stop_handler(_sig, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    started = time.time()
    print(f"Live feed started: devices={','.join(device_codes)} interval={args.interval}s db={args.database}")

    while not stop["flag"]:
        now_ms = int(time.time() * 1000)
        for state in states:
            state.tick += 1
            insert_telemetry(td, state, now_ms)

            # Emit occasional triggered/cleared alarm events so alarm pages move.
            if state.tick % 30 == 0:
                insert_alarm_event(td, state, now_ms, triggered=True)
            elif state.tick % 30 == 6:
                insert_alarm_event(td, state, now_ms, triggered=False)

        elapsed = int(time.time() - started)
        print(f"tick={states[0].tick} elapsed={elapsed}s wrote={len(states)} telemetry rows")

        if args.seconds > 0 and elapsed >= args.seconds:
            break
        time.sleep(max(0.05, args.interval))

    print("Live feed stopped.")


if __name__ == "__main__":
    random.seed(42)
    main()
