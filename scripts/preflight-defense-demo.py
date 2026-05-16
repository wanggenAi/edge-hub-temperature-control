#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "hmi" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import Device  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def run_cmd(args: list[str], timeout: float = 5.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout.strip()
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "timeout"


def http_get(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    req = Request(url, method="GET")
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            text = response.read(300).decode("utf-8", errors="replace")
            return 200 <= int(response.status) < 300, f"status={response.status} body={text[:120]}"
    except HTTPError as exc:
        detail = exc.read(200).decode("utf-8", errors="replace")
        return False, f"http={exc.code} body={detail[:120]}"
    except URLError as exc:
        return False, f"unavailable reason={exc.reason}"
    except TimeoutError:
        return False, "timeout"


def tcp_connect(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} reachable"
    except OSError as exc:
        return False, f"{host}:{port} not reachable ({exc})"


def docker_status(container: str) -> Check:
    rc, out = run_cmd(
        ["docker", "inspect", "-f", "{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}", container]
    )
    return Check(f"docker:{container}", rc == 0 and out.startswith("running"), out or "missing")


def port_owner(port: int) -> str:
    rc, out = run_cmd(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], timeout=3.0)
    if rc != 0 or not out:
        return "free"
    lines = out.splitlines()
    return " | ".join(lines[:3])


def tdengine_query(sql: str, timeout: float = 5.0) -> tuple[bool, dict[str, Any] | str]:
    auth = base64.b64encode(f"{settings.tdengine_username}:{settings.tdengine_password}".encode()).decode()
    endpoint = settings.tdengine_url.rstrip("/") + "/rest/sql"
    req = Request(endpoint, data=sql.encode("utf-8"), method="POST")
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "text/plain; charset=UTF-8")
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return False, raw[:200]
    if int(body.get("code", -1)) != 0:
        return False, str(body.get("desc") or body)
    return True, body


def td_first_row(sql: str) -> tuple[bool, dict[str, Any] | str | None]:
    ok, body = tdengine_query(sql)
    if not ok or not isinstance(body, dict):
        return False, body
    rows = body.get("data") or []
    meta = body.get("column_meta") or []
    if not rows:
        return True, None
    columns = [str(col[0]) for col in meta if isinstance(col, list) and col]
    row = rows[0]
    return True, {columns[i]: row[i] if i < len(row) else None for i in range(len(columns))}


def postgres_summary() -> list[Check]:
    checks: list[Check] = []
    db = SessionLocal()
    try:
        edge = db.scalar(select(Device).where(Device.code == "edge-node-001"))
        checks.append(
            Check(
                "postgres:edge-node-001",
                edge is not None,
                f"id={edge.id} name={edge.name} target={edge.target_temp}" if edge else "missing",
            )
        )
        defense_count = db.scalar(select(func.count()).select_from(Device).where(Device.code.like("DEF-%"))) or 0
        checks.append(Check("postgres:DEF devices", int(defense_count) >= 6, f"count={defense_count}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("postgres:query", False, str(exc)))
    finally:
        db.close()
    return checks


def tdengine_summary() -> list[Check]:
    checks: list[Check] = []
    ok, body = tdengine_query(f"show databases")
    checks.append(Check("tdengine:rest", ok, "REST query ok" if ok else str(body)))
    if not ok:
        return checks

    for table, label in (
        ("device_status", "tdengine:device_status edge-node-001"),
        ("telemetry", "tdengine:telemetry edge-node-001"),
        ("params_ack", "tdengine:params_ack edge-node-001"),
    ):
        ok_row, row = td_first_row(
            f"select * from {settings.tdengine_database}.{table} "
            "where device_id='edge-node-001' order by ts desc limit 1"
        )
        if not ok_row:
            checks.append(Check(label, False, str(row)))
            continue
        checks.append(Check(label, row is not None, json.dumps(row, ensure_ascii=False, default=str) if row else "no rows"))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for the thesis defense demo.")
    parser.add_argument("--require-wokwi", action="store_true", help="Fail if Wokwi serial bridge port 4000 is not open.")
    args = parser.parse_args()

    checks: list[Check] = []
    checks.extend([docker_status("edgehub-postgres"), docker_status("edgehub-tdengine")])

    for name, url in (
        ("hmi:backend", "http://127.0.0.1:8000/health"),
        ("hmi:frontend", "http://127.0.0.1:5173"),
        ("ai:runtime", "http://127.0.0.1:8010/health"),
        ("datahub:actuator", "http://127.0.0.1:8081/actuator/health"),
    ):
        ok, detail = http_get(url)
        checks.append(Check(name, ok, detail))

    ok, detail = tcp_connect(settings.mqtt_broker_host, int(settings.mqtt_broker_port))
    checks.append(Check("mqtt:broker", ok, detail))

    ok, detail = tcp_connect("127.0.0.1", 4000)
    checks.append(Check("wokwi:serial-4000", ok, detail, required=bool(args.require_wokwi)))

    checks.append(Check("port:18080 DataHub", "free" not in port_owner(18080), port_owner(18080)))
    owner_8080 = port_owner(8080)
    checks.append(Check("port:8080 should not be DataHub", "data-hub" not in owner_8080.lower(), owner_8080, required=False))

    checks.extend(postgres_summary())
    checks.extend(tdengine_summary())

    failed_required = 0
    warn_optional = 0
    for check in checks:
        status = "OK" if check.ok else ("FAIL" if check.required else "WARN")
        print(f"[{status}] {check.name}: {check.detail}")
        if not check.ok and check.required:
            failed_required += 1
        elif not check.ok:
            warn_optional += 1

    print(f"[summary] required_failed={failed_required} optional_warn={warn_optional}")
    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
