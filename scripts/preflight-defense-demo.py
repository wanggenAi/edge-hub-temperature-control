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
from app.models.entities import (  # noqa: E402
    AIRecommendation,
    ControlAction,
    ControlActionEvalJob,
    ControlActionFeedbackSample,
    Device,
    DeviceAlarm,
    User,
    UserDevice,
)
from app.services.ai.recommendation_service import RecommendationService  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


DEFENSE_SCENARIOS = {
    "normal_stable": "DEF-101",
    "slow_response": "DEF-102",
    "overshoot_high": "DEF-103",
    "oscillation": "DEF-104",
    "post_apply_success": "DEF-105",
    "preview_mismatch": "DEF-106",
    "insufficient_data": "DEF-107",
    "steady_state_error": "DEF-108",
    "saturation_limited": "DEF-109",
    "sensor_invalid": "DEF-110",
    "over_temperature_safety": "DEF-111",
    "ack_success": "DEF-112",
    "ack_failure_validation_error": "DEF-113",
    "post_apply_partial": "DEF-114",
}

RANKING_REQUIRED_CODES = {
    "DEF-108": "steady_state_error",
    "DEF-105": "post_apply_success",
    "DEF-106": "preview_mismatch",
}

ACTIVE_ARTIFACTS_DIR = BACKEND_ROOT / "artifacts" / "active"
REQUIRED_RANKING_ARTIFACTS = {
    "recommendation_success_tree.joblib": {"improved", "unchanged", "worse"},
    "preview_gap_tree.joblib": {"low", "medium", "high"},
}

OPTIONAL_WARN_FALLBACKS = {
    "ai:runtime": "AI runtime unavailable -> use seeded recommendations/backend fallback.",
    "datahub:actuator": "DataHub actuator unavailable -> use seeded ACK data or MQTT loopback.",
    "wokwi:serial-4000": "Wokwi unavailable -> use seeded DEF telemetry.",
    "port:18080 DataHub": "DataHub port is not listening -> seeded ACK data still supports the controlled demo.",
    "port:8080 should not be DataHub": "Port 8080 conflict is not a seeded-demo blocker; use HMI on 5173 and backend on 8000.",
    "backend:pytest": "pytest unavailable -> frontend build and DataHub tests are the lightweight verification path.",
}


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


def _count_value(row: dict[str, Any] | str | None) -> int:
    if not isinstance(row, dict):
        return 0
    for key in ("cnt", "count(*)", "COUNT(*)"):
        if key in row:
            try:
                return int(row.get(key) or 0)
            except (TypeError, ValueError):
                return 0
    for value in row.values():
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            continue
    return 0


def _runtime_decision_for_latest_rec(db, device: Device) -> dict[str, Any]:
    rec = db.scalar(
        select(AIRecommendation)
        .where(AIRecommendation.device_id == device.id)
        .order_by(AIRecommendation.last_run_at.desc(), AIRecommendation.id.desc())
    )
    if rec is None:
        return {}
    meta = RecommendationService().read_storage_metadata(rec.suggestion)
    decision = meta.get("ard")
    return dict(decision) if isinstance(decision, dict) else {}


def artifact_summary() -> list[Check]:
    checks: list[Check] = []
    try:
        import joblib  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return [Check("ai:ranking artifacts import", False, f"joblib unavailable: {exc}")]

    for filename, expected_classes in REQUIRED_RANKING_ARTIFACTS.items():
        path = ACTIVE_ARTIFACTS_DIR / filename
        if not path.exists() or not path.is_file():
            checks.append(Check(f"ai:active artifact {filename}", False, f"missing {path}"))
            continue
        try:
            model = joblib.load(path)
            clf = getattr(model, "named_steps", {}).get("clf", model)
            classes = {str(item) for item in getattr(clf, "classes_", [])}
            checks.append(
                Check(
                    f"ai:active artifact {filename}",
                    bool(expected_classes <= classes) and hasattr(model, "predict_proba"),
                    f"path={path} classes={sorted(classes)} bytes={path.stat().st_size}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(Check(f"ai:active artifact {filename}", False, f"load_failed={exc}"))

    manifest = ACTIVE_ARTIFACTS_DIR / "defense_ranking_models_manifest.json"
    checks.append(
        Check(
            "ai:ranking artifact manifest",
            manifest.exists() and manifest.is_file(),
            f"path={manifest} bytes={manifest.stat().st_size if manifest.exists() else 0}",
        )
    )
    try:
        from app.services.ai.recommendation_orchestrator import RecommendationOrchestrator
        from app.services.ai.recommendation_service import RecommendationService

        ranker = RecommendationOrchestrator(RecommendationService())._load_ranker()
        checks.append(
            Check(
                "ai:runtime ranker loader",
                ranker is not None,
                f"loaded={type(ranker).__name__} candidate_count={getattr(ranker, 'candidate_count', None)}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("ai:runtime ranker loader", False, f"load_failed={exc}"))
    return checks


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
        checks.append(Check("postgres:DEF devices", int(defense_count) >= 14, f"count={defense_count}"))

        active_users = int(db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0)
        for scenario, code in DEFENSE_SCENARIOS.items():
            device = db.scalar(select(Device).where(Device.code == code))
            checks.append(
                Check(
                    f"postgres:{code} {scenario}",
                    device is not None,
                    f"id={device.id} name={device.name}" if device else "missing",
                )
            )
            if device is None:
                continue
            links = int(db.scalar(select(func.count()).select_from(UserDevice).where(UserDevice.device_id == device.id)) or 0)
            checks.append(
                Check(
                    f"postgres:{code} visibility",
                    active_users == 0 or links > 0,
                    f"active_users={active_users} user_device_links={links}",
                    required=active_users > 0,
                )
            )

        success = db.scalar(select(Device).where(Device.code == DEFENSE_SCENARIOS["post_apply_success"]))
        if success is not None:
            success_rec = int(db.scalar(select(func.count()).select_from(AIRecommendation).where(AIRecommendation.device_id == success.id)) or 0)
            success_action = int(db.scalar(select(func.count()).select_from(ControlAction).where(ControlAction.device_id == success.id)) or 0)
            success_feedback = db.scalar(
                select(ControlActionFeedbackSample)
                .where(ControlActionFeedbackSample.device_id == success.id)
                .order_by(ControlActionFeedbackSample.created_at.desc())
            )
            checks.append(
                Check(
                    "postgres:post_apply_success rec/action/feedback",
                    success_rec > 0
                    and success_action > 0
                    and success_feedback is not None
                    and success_feedback.actual_effect_label == "improved"
                    and success_feedback.preview_gap_label == "low",
                    (
                        f"recommendations={success_rec} actions={success_action} "
                        f"actual_effect={getattr(success_feedback, 'actual_effect_label', None)} "
                        f"preview_gap={getattr(success_feedback, 'preview_gap_label', None)}"
                    ),
                )
            )

        mismatch = db.scalar(select(Device).where(Device.code == DEFENSE_SCENARIOS["preview_mismatch"]))
        if mismatch is not None:
            high_gap = db.scalar(
                select(ControlActionFeedbackSample)
                .where(
                    ControlActionFeedbackSample.device_id == mismatch.id,
                    ControlActionFeedbackSample.preview_gap_label == "high",
                )
                .order_by(ControlActionFeedbackSample.created_at.desc())
            )
            checks.append(
                Check(
                    "postgres:preview_mismatch high gap",
                    high_gap is not None,
                    "preview_gap_label=high" if high_gap else "missing high gap feedback marker",
                )
            )

        insufficient = db.scalar(select(Device).where(Device.code == DEFENSE_SCENARIOS["insufficient_data"]))
        if insufficient is not None:
            insuff_feedback = db.scalar(
                select(ControlActionFeedbackSample)
                .where(
                    ControlActionFeedbackSample.device_id == insufficient.id,
                    ControlActionFeedbackSample.insufficient_data.is_(True),
                )
                .order_by(ControlActionFeedbackSample.created_at.desc())
            )
            pending_job = db.scalar(
                select(ControlActionEvalJob)
                .where(
                    ControlActionEvalJob.device_id == insufficient.id,
                    ControlActionEvalJob.status.in_(["pending", "insufficient", "not_enough_data"]),
                )
                .order_by(ControlActionEvalJob.created_at.desc())
            )
            checks.append(
                Check(
                    "postgres:insufficient_data marker",
                    insuff_feedback is not None or pending_job is not None,
                    (
                        f"feedback_insufficient={insuff_feedback is not None} "
                        f"eval_job_status={getattr(pending_job, 'status', None)}"
                    ),
                )
            )

        partial = db.scalar(select(Device).where(Device.code == DEFENSE_SCENARIOS["post_apply_partial"]))
        if partial is not None:
            partial_feedback = db.scalar(
                select(ControlActionFeedbackSample)
                .where(
                    ControlActionFeedbackSample.device_id == partial.id,
                    ControlActionFeedbackSample.preview_gap_label == "medium",
                    ControlActionFeedbackSample.actual_effect_label.in_(["unchanged", "partial", "limited_improvement"]),
                )
                .order_by(ControlActionFeedbackSample.created_at.desc())
            )
            checks.append(
                Check(
                    "postgres:post_apply_partial marker",
                    partial_feedback is not None,
                    (
                        f"actual_effect={getattr(partial_feedback, 'actual_effect_label', None)} "
                        f"preview_gap={getattr(partial_feedback, 'preview_gap_label', None)}"
                    ),
                )
            )

        ack_success = db.scalar(select(Device).where(Device.code == DEFENSE_SCENARIOS["ack_success"]))
        if ack_success is not None:
            applied_action = db.scalar(
                select(ControlAction)
                .where(ControlAction.device_id == ack_success.id, ControlAction.status.in_(["applied", "success", "evaluated"]))
                .order_by(ControlAction.applied_at.desc())
            )
            checks.append(
                Check(
                    "postgres:ack_success action",
                    applied_action is not None,
                    f"status={getattr(applied_action, 'status', None)}",
                )
            )

        ack_failure = db.scalar(select(Device).where(Device.code == DEFENSE_SCENARIOS["ack_failure_validation_error"]))
        if ack_failure is not None:
            rejected_action = db.scalar(
                select(ControlAction)
                .where(ControlAction.device_id == ack_failure.id, ControlAction.status.in_(["rejected", "failed"]))
                .order_by(ControlAction.applied_at.desc())
            )
            context = getattr(rejected_action, "context_snapshot", None) or {}
            reason = context.get("failure_reason") if isinstance(context, dict) else None
            checks.append(
                Check(
                    "postgres:ack_failure validation marker",
                    rejected_action is not None and bool(reason),
                    f"status={getattr(rejected_action, 'status', None)} failure_reason={reason}",
                )
            )

        for scenario, reason in (
            ("sensor_invalid", "sensor_invalid"),
            ("over_temperature_safety", "over_temperature"),
        ):
            device = db.scalar(select(Device).where(Device.code == DEFENSE_SCENARIOS[scenario]))
            if device is None:
                continue
            alarm = db.scalar(
                select(DeviceAlarm)
                .where(DeviceAlarm.device_id == device.id, DeviceAlarm.rule_code == reason, DeviceAlarm.is_active.is_(True))
                .order_by(DeviceAlarm.created_at.desc())
            )
            checks.append(
                Check(
                    f"postgres:{scenario} active alarm",
                    alarm is not None and bool(device.is_alarm),
                    f"device_alarm={device.is_alarm} rule_code={getattr(alarm, 'rule_code', None)}",
                )
            )

        for code, scenario in RANKING_REQUIRED_CODES.items():
            device = db.scalar(select(Device).where(Device.code == code))
            if device is None:
                checks.append(Check(f"postgres:{code} ranking decision", False, "device missing"))
                continue
            decision = _runtime_decision_for_latest_rec(db, device)
            selected = str(decision.get("selected_candidate_id") or "")
            evaluated = int(decision.get("evaluated_candidate_count") or 0)
            ranked = decision.get("ranked_candidates")
            ranked_count = len(ranked) if isinstance(ranked, list) else 0
            checks.append(
                Check(
                    f"postgres:{code} {scenario} ranking decision",
                    bool(decision.get("ranking_used"))
                    and selected
                    and selected != "rule_center"
                    and evaluated >= 3
                    and ranked_count >= 3,
                    (
                        f"ranking_used={decision.get('ranking_used')} selected={selected or 'missing'} "
                        f"evaluated={evaluated} ranked_candidates={ranked_count}"
                    ),
                )
            )
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

    for scenario, code in DEFENSE_SCENARIOS.items():
        ok_row, row = td_first_row(f"select count(*) AS cnt from {settings.tdengine_database}.telemetry where device_id='{code}'")
        if not ok_row:
            checks.append(Check(f"tdengine:{code} telemetry", False, str(row)))
            continue
        count = _count_value(row)
        checks.append(Check(f"tdengine:{code} {scenario} telemetry", count > 0, f"count={count}"))

    semantic_queries = [
        (
            "tdengine:DEF-108 steady_state_error same-sign",
            "select count(*) AS cnt, min(error_c) AS min_error, avg(error_c) AS avg_error "
            f"from {settings.tdengine_database}.telemetry "
            "where device_id='DEF-108' and run_id='defense_steady_state_error_baseline'",
            lambda row: _count_value(row) > 0
            and float((row or {}).get("min_error") or 0.0) > 0.6
            and float((row or {}).get("avg_error") or 0.0) > 0.8,
        ),
        (
            "tdengine:DEF-109 saturation high PWM",
            "select count(*) AS cnt, avg(pwm_duty) AS avg_pwm, min(pwm_duty) AS min_pwm "
            f"from {settings.tdengine_database}.telemetry "
            "where device_id='DEF-109' and run_id='defense_saturation_limited_baseline'",
            lambda row: _count_value(row) > 0
            and float((row or {}).get("avg_pwm") or 0.0) >= 93.0
            and float((row or {}).get("min_pwm") or 0.0) >= 90.0,
        ),
        (
            "tdengine:DEF-110 sensor invalid safety",
            "select count(*) AS cnt from "
            f"{settings.tdengine_database}.telemetry "
            "where device_id='DEF-110' and sensor_valid=false and fault_latched=true and pwm_duty=0",
            lambda row: _count_value(row) > 0,
        ),
        (
            "tdengine:DEF-111 over-temperature safety",
            "select count(*) AS cnt from "
            f"{settings.tdengine_database}.telemetry "
            "where device_id='DEF-111' and sensor_temp_c > software_max_safe_temp_c and fault_latched=true and pwm_duty=0 and error_c < 0",
            lambda row: _count_value(row) > 0,
        ),
        (
            "tdengine:DEF-112 ACK success",
            "select count(*) AS cnt from "
            f"{settings.tdengine_database}.params_ack "
            "where device_id='DEF-112' and success=true and ack_type='applied'",
            lambda row: _count_value(row) > 0,
        ),
        (
            "tdengine:DEF-113 ACK validation failure",
            "select count(*) AS cnt from "
            f"{settings.tdengine_database}.params_ack "
            "where device_id='DEF-113' and success=false and ack_type='validation_error' and reason='kp_out_of_range'",
            lambda row: _count_value(row) > 0,
        ),
        (
            "tdengine:safety alarm events",
            "select count(*) AS cnt from "
            f"{settings.tdengine_database}.alarm_events "
            "where device_id in ('DEF-110','DEF-111') and reason in ('sensor_invalid','over_temperature')",
            lambda row: _count_value(row) >= 2,
        ),
    ]
    for name, sql, predicate in semantic_queries:
        ok_row, row = td_first_row(sql)
        if not ok_row:
            checks.append(Check(name, False, str(row)))
            continue
        try:
            ok_semantic = isinstance(row, dict) and predicate(row)
        except (TypeError, ValueError):
            ok_semantic = False
        checks.append(Check(name, ok_semantic, json.dumps(row, ensure_ascii=False, default=str) if row else "no rows"))

    mismatch_count = 0
    sample_count = 0
    for code in DEFENSE_SCENARIOS.values():
        ok_sample, body = tdengine_query(
            f"select target_temp_c, sensor_temp_c, error_c from {settings.tdengine_database}.telemetry "
            f"where device_id='{code}' order by ts desc limit 20"
        )
        if not ok_sample or not isinstance(body, dict):
            continue
        columns = [str(col[0]) for col in body.get("column_meta") or [] if isinstance(col, list) and col]
        for row in body.get("data") or []:
            record = {columns[i]: row[i] if i < len(row) else None for i in range(len(columns))}
            try:
                target = float(record.get("target_temp_c"))
                sensor = float(record.get("sensor_temp_c"))
                error = float(record.get("error_c"))
            except (TypeError, ValueError):
                mismatch_count += 1
                continue
            sample_count += 1
            if abs((target - sensor) - error) > 0.03:
                mismatch_count += 1
    checks.append(
        Check(
            "tdengine:error_c direction sample",
            sample_count > 0 and mismatch_count == 0,
            f"samples={sample_count} mismatches={mismatch_count}; expected error_c=target_temp_c-sensor_temp_c",
        )
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for the thesis defense demo.")
    parser.add_argument("--require-wokwi", action="store_true", help="Fail if Wokwi serial bridge port 4000 is not open.")
    parser.add_argument("--require-ai-runtime", action="store_true", help="Fail if the optional AI runtime service is not open.")
    parser.add_argument("--require-datahub", action="store_true", help="Fail if Data Hub actuator/ports are not open.")
    args = parser.parse_args()

    checks: list[Check] = []
    checks.extend([docker_status("edgehub-postgres"), docker_status("edgehub-tdengine")])

    ai_runtime_required = bool(args.require_ai_runtime or settings.ai_runtime_enabled)
    datahub_required = bool(args.require_datahub)
    for name, url, required in (
        ("hmi:backend", "http://127.0.0.1:8000/health", True),
        ("hmi:frontend", "http://127.0.0.1:5173", True),
        ("ai:runtime", "http://127.0.0.1:8010/health", ai_runtime_required),
        ("datahub:actuator", "http://127.0.0.1:8081/actuator/health", datahub_required),
    ):
        ok, detail = http_get(url)
        checks.append(Check(name, ok, detail, required=required))

    ok, detail = tcp_connect(settings.mqtt_broker_host, int(settings.mqtt_broker_port))
    checks.append(Check("mqtt:broker", ok, detail))

    ok, detail = tcp_connect("127.0.0.1", 4000)
    checks.append(Check("wokwi:serial-4000", ok, detail, required=bool(args.require_wokwi)))

    checks.append(Check("port:18080 DataHub", "free" not in port_owner(18080), port_owner(18080), required=datahub_required))
    owner_8080 = port_owner(8080)
    checks.append(Check("port:8080 should not be DataHub", "data-hub" not in owner_8080.lower(), owner_8080, required=False))

    checks.extend(artifact_summary())
    checks.extend(postgres_summary())
    checks.extend(tdengine_summary())

    rc, out = run_cmd([str(BACKEND_ROOT / ".venv" / "bin" / "python"), "-m", "pytest", "--version"], timeout=5.0)
    checks.append(
        Check(
            "backend:pytest",
            rc == 0,
            out.splitlines()[0] if out else "pytest unavailable",
            required=False,
        )
    )

    failed_required = 0
    warn_optional = 0
    warn_checks: list[Check] = []
    for check in checks:
        status = "PASS" if check.ok else ("FAIL" if check.required else "WARN")
        print(f"[{status}] {check.name}: {check.detail}")
        if not check.ok and check.required:
            failed_required += 1
        elif not check.ok:
            warn_optional += 1
            warn_checks.append(check)

    print(f"[summary] required_failed={failed_required} optional_warn={warn_optional}")
    if failed_required == 0:
        print("DEFENSE DEMO REQUIRED CHECKS PASSED")
    if warn_checks:
        print("Optional runtime WARN items and fallbacks:")
        for check in warn_checks:
            fallback = OPTIONAL_WARN_FALLBACKS.get(check.name, "Optional warning; seeded DEF demo remains the primary fallback.")
            print(f"- {check.name}: {fallback}")
        print("Runtime WARN items do not block the controlled seeded defense demo unless you explicitly require that runtime.")
    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
