from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import threading
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.models.entities import AIRecommendation, ControlAction, ControlActionEvalJob, ControlActionFeedbackSample
from app.schemas.ops import (
    OpsAiOverviewOut,
    OpsDataHubOut,
    OpsEvalJobStatusOut,
    OpsKeyValueCount,
    OpsLearningLoopOut,
    OpsModelRuntimeOut,
    OpsOverviewOut,
    OpsRecentEvalJobOut,
    OpsRuntimeOut,
    OpsTrendPoint,
)
from app.services.ai.recommendation_service import RecommendationService

_APP_STARTED_AT = datetime.utcnow()
_KEY_VALUE_RE = re.compile(r"([a-zA-Z0-9_]+)=([a-zA-Z0-9_.:-]+)")
_LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)")
_PROM_SAMPLE_RE = re.compile(
    r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)$'
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _parse_dt(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _latest_existing(paths: list[Path]) -> Optional[Path]:
    existing = [p for p in paths if p.exists() and p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _tail_lines(path: Path, *, max_lines: int = 500) -> list[str]:
    rows: deque[str] = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            rows.append(line.rstrip("\n"))
    return list(rows)


def _metric_num(metric_map: dict[str, str], key: str) -> Optional[float]:
    raw = metric_map.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse_section_values(line: str, section: str) -> dict[str, str]:
    marker = f"{section}["
    idx = line.find(marker)
    if idx < 0:
        return {}
    start = idx + len(marker)
    end = line.find("]", start)
    if end < 0:
        return {}
    content = line[start:end]
    return {k: v for k, v in _KEY_VALUE_RE.findall(content)}


def _parse_log_ts(line: str) -> Optional[datetime]:
    m = _LOG_TS_RE.match(line.strip())
    if not m:
        return None
    return _parse_dt(m.group(1))


def _http_get_text(url: str, timeout_seconds: float) -> Optional[str]:
    if not url:
        return None
    try:
        with urlopen(url, timeout=max(0.5, float(timeout_seconds))) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (URLError, TimeoutError, ValueError):
        return None


def _parse_prometheus_samples(text: str) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _PROM_SAMPLE_RE.match(line)
        if not m:
            continue
        metric = m.group(1)
        labels = m.group(2) or ""
        try:
            value = float(m.group(3))
        except (TypeError, ValueError):
            continue
        out.append((metric, labels, value))
    return out


def _sum_prometheus(samples: list[tuple[str, str, float]], metric: str, label_contains: Optional[str] = None) -> Optional[float]:
    vals = [v for m, lbl, v in samples if m == metric and (label_contains is None or label_contains in lbl)]
    if not vals:
        return None
    return float(sum(vals))


def _first_json_metric(obj: dict, *keys: str) -> Optional[float]:
    for key in keys:
        if key in obj:
            try:
                return float(obj.get(key))
            except (TypeError, ValueError):
                continue
    return None


class OpsConsoleService:
    def __init__(self) -> None:
        self._rec_service = RecommendationService()

    def _data_hub_log_path(self) -> Optional[Path]:
        root = _repo_root()
        candidates = [
            root / "data-hub/runtime/logs/data-hub.log",
            root / "data-hub/runtime/logs/data-hub-latest-window.log",
        ]
        return _latest_existing(candidates)

    def _data_hub_summary_csv_path(self) -> Optional[Path]:
        root = _repo_root()
        return _latest_existing(sorted((root / "data-hub/runtime/logs").glob("datahub-stats-summary-*.csv")))

    def _build_data_hub_metrics(self) -> OpsDataHubOut:
        now = datetime.utcnow()
        log_path = self._data_hub_log_path()
        if log_path is None:
            return OpsDataHubOut(as_of=now, source="data-hub-log", available=False)

        stats_line = None
        for line in reversed(_tail_lines(log_path, max_lines=1000)):
            if "datahub.stats" in line:
                stats_line = line
                break

        if not stats_line:
            return OpsDataHubOut(as_of=now, source=str(log_path), available=False)

        metric_map = {k: v for k, v in _KEY_VALUE_RE.findall(stats_line)}
        mqtt_map = _parse_section_values(stats_line, "mqtt")
        accounting_map = _parse_section_values(stats_line, "accounting")
        outcome_delta_map = _parse_section_values(stats_line, "outcome_delta")
        tdengine_map = _parse_section_values(stats_line, "tdengine")
        delta_map = _parse_section_values(stats_line, "delta")
        buffer_map = _parse_section_values(stats_line, "buffer")
        interval_ms = _metric_num(metric_map, "intervalMs") or 30000.0
        interval_sec = max(1.0, interval_ms / 1000.0)

        mqtt_recv_delta = _metric_num(mqtt_map, "mqtt_received_delta") or _metric_num(delta_map, "recv") or 0.0
        mqtt_drop_delta = _metric_num(mqtt_map, "mqtt_dropped_delta") or 0.0
        accounted_delta = _metric_num(accounting_map, "accounted_delta") or 0.0
        ingest_tps = mqtt_recv_delta / interval_sec
        consume_tps = accounted_delta / interval_sec

        reason_candidates = {
            "ingress_drop": int(_metric_num(outcome_delta_map, "ingressDrop") or 0),
            "pipeline_drop": int(_metric_num(outcome_delta_map, "pipelineDrop") or 0),
            "control_topic": int(_metric_num(outcome_delta_map, "controlTopic") or 0),
            "telemetry_skip": int(_metric_num(outcome_delta_map, "telemetrySkip") or 0),
            "parse_fail": int(_metric_num(outcome_delta_map, "parseFail") or 0),
            "persist_fail": int(_metric_num(outcome_delta_map, "persistFail") or 0),
        }
        discard_reasons = [OpsKeyValueCount(key=k, count=v) for k, v in reason_candidates.items() if v > 0]
        discard_reasons.sort(key=lambda x: x.count, reverse=True)

        trend: list[OpsTrendPoint] = self._build_data_hub_trend_from_log(log_path)

        result = OpsDataHubOut(
            as_of=now,
            source=str(log_path),
            available=True,
            interval_seconds=interval_sec,
            mqtt_ingress_tps=round(ingest_tps, 3),
            mqtt_egress_tps=None,
            data_hub_consume_tps=round(consume_tps, 3),
            queue_depth=int(_metric_num(buffer_map, "current_buffer_size") or 0),
            dropped_total=int(_metric_num(mqtt_map, "mqtt_dropped_total") or 0),
            dropped_delta=int(mqtt_drop_delta),
            outcome_ingress_drop_delta=int(_metric_num(outcome_delta_map, "ingressDrop") or 0),
            outcome_pipeline_drop_delta=int(_metric_num(outcome_delta_map, "pipelineDrop") or 0),
            outcome_parse_fail_delta=int(_metric_num(outcome_delta_map, "parseFail") or 0),
            outcome_persist_fail_delta=int(_metric_num(outcome_delta_map, "persistFail") or 0),
            outcome_telemetry_skip_delta=int(_metric_num(outcome_delta_map, "telemetrySkip") or 0),
            outcome_control_topic_delta=int(_metric_num(outcome_delta_map, "controlTopic") or 0),
            outcome_persisted_delta=int(_metric_num(outcome_delta_map, "persisted") or 0),
            accounting_unaccounted_delta=int(_metric_num(accounting_map, "unaccounted_delta") or 0),
            telemetry_persisted_delta=int(_metric_num(delta_map, "telemetryOk") or 0),
            params_set_delta=int(_metric_num(delta_map, "paramsSetOk") or 0),
            params_ack_delta=int(_metric_num(delta_map, "paramsAckOk") or 0),
            device_status_delta=int(_metric_num(delta_map, "deviceStatusOk") or 0),
            discard_reasons_top=discard_reasons[:5],
            tdengine_write_success_total=int(_metric_num(tdengine_map, "tdengine_write_success_total") or 0),
            tdengine_write_failed_total=int(_metric_num(tdengine_map, "tdengine_write_failed_total") or 0),
            tdengine_write_success_delta=int(_metric_num(tdengine_map, "tdengine_write_success_delta") or 0),
            tdengine_write_failed_delta=int(_metric_num(tdengine_map, "tdengine_write_failed_delta") or 0),
            data_hub_cpu_usage_pct=None,
            trend=trend,
        )
        # Optional external metrics endpoint overlay (lightweight).
        # This keeps log parsing as default and only augments when configured.
        if settings.ops_enable_external_metrics and settings.ops_data_hub_metrics_url:
            payload = _http_get_text(settings.ops_data_hub_metrics_url, float(settings.ops_metrics_timeout_seconds))
            if payload:
                overlay = self._parse_data_hub_metrics_overlay(payload)
                result = result.model_copy(
                    update={
                        k: v
                        for k, v in {
                            "source": overlay.get("source", result.source),
                            "mqtt_ingress_tps": overlay.get("mqtt_ingress_tps", result.mqtt_ingress_tps),
                            "mqtt_egress_tps": overlay.get("mqtt_egress_tps", result.mqtt_egress_tps),
                            "data_hub_consume_tps": overlay.get("data_hub_consume_tps", result.data_hub_consume_tps),
                            "queue_depth": overlay.get("queue_depth", result.queue_depth),
                            "dropped_total": overlay.get("dropped_total", result.dropped_total),
                            "data_hub_cpu_usage_pct": overlay.get("data_hub_cpu_usage_pct", result.data_hub_cpu_usage_pct),
                        }.items()
                        if v is not None
                    }
                )
        return result

    def _build_data_hub_trend_from_log(self, log_path: Path) -> list[OpsTrendPoint]:
        lines = _tail_lines(log_path, max_lines=4000)
        trend: list[OpsTrendPoint] = []
        for line in lines:
            if "datahub.stats" not in line:
                continue
            ts = _parse_log_ts(line)
            if ts is None:
                continue
            metric_map = {k: v for k, v in _KEY_VALUE_RE.findall(line)}
            mqtt_map = _parse_section_values(line, "mqtt")
            accounting_map = _parse_section_values(line, "accounting")
            outcome_delta_map = _parse_section_values(line, "outcome_delta")
            tdengine_map = _parse_section_values(line, "tdengine")
            buffer_map = _parse_section_values(line, "buffer")
            interval_ms = _metric_num(metric_map, "intervalMs") or 30000.0
            interval_sec = max(1.0, interval_ms / 1000.0)
            recv_delta = _metric_num(mqtt_map, "mqtt_received_delta") or 0.0
            accounted_delta = _metric_num(accounting_map, "accounted_delta") or 0.0
            trend.append(
                OpsTrendPoint(
                    ts=ts,
                    mqtt_ingress_tps=recv_delta / interval_sec,
                    consume_tps=accounted_delta / interval_sec,
                    dropped_delta=int(_metric_num(mqtt_map, "mqtt_dropped_delta") or 0),
                    queue_depth=int(_metric_num(buffer_map, "current_buffer_size") or 0),
                    parse_fail_delta=int(_metric_num(outcome_delta_map, "parseFail") or 0),
                    persist_fail_delta=int(_metric_num(outcome_delta_map, "persistFail") or 0),
                    tdengine_write_failed_delta=int(_metric_num(tdengine_map, "tdengine_write_failed_delta") or 0),
                )
            )
        return trend[-60:]

    def _parse_data_hub_metrics_overlay(self, payload: str) -> dict[str, object]:
        text = payload.strip()
        if not text:
            return {}
        if text.startswith("{"):
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                return {}
            if not isinstance(body, dict):
                return {}
            return {
                "source": "external_json",
                "mqtt_ingress_tps": _first_json_metric(body, "mqtt_ingress_tps", "mqttIngressTps"),
                "mqtt_egress_tps": _first_json_metric(body, "mqtt_egress_tps", "mqttEgressTps"),
                "data_hub_consume_tps": _first_json_metric(body, "data_hub_consume_tps", "consume_tps", "consumeTps"),
                "queue_depth": _first_json_metric(body, "queue_depth", "queueDepth"),
                "dropped_total": _first_json_metric(body, "dropped_total", "mqtt_dropped_total", "droppedTotal"),
                "data_hub_cpu_usage_pct": _first_json_metric(body, "process_cpu_usage_pct", "cpu_usage_pct"),
            }

        samples = _parse_prometheus_samples(text)
        if not samples:
            return {}
        cpu_ratio = _sum_prometheus(samples, "process_cpu_usage")
        if cpu_ratio is None:
            cpu_ratio = _sum_prometheus(samples, "system_cpu_usage")
        return {
            "source": "external_prometheus",
            # Best-effort naming: map if exporter provides these gauges/counters.
            "mqtt_ingress_tps": _sum_prometheus(samples, "datahub_mqtt_ingress_tps"),
            "mqtt_egress_tps": _sum_prometheus(samples, "datahub_mqtt_egress_tps"),
            "data_hub_consume_tps": _sum_prometheus(samples, "datahub_consume_tps"),
            "queue_depth": _sum_prometheus(samples, "datahub_queue_depth"),
            "dropped_total": _sum_prometheus(samples, "datahub_mqtt_dropped_total"),
            "data_hub_cpu_usage_pct": None if cpu_ratio is None else float(cpu_ratio) * 100.0,
        }

    def _build_runtime_metrics(self) -> OpsRuntimeOut:
        now = datetime.utcnow()
        uptime_sec = max(0.0, (now - _APP_STARTED_AT).total_seconds())
        load_avg: tuple[Optional[float], Optional[float], Optional[float]] = (None, None, None)
        if hasattr(os, "getloadavg"):
            try:
                l1, l5, l15 = os.getloadavg()
                load_avg = (float(l1), float(l5), float(l15))
            except OSError:
                pass

        pool = engine.pool
        db_pool_size = db_pool_checked_in = db_pool_checked_out = db_pool_overflow = None
        db_pool_status = None
        try:
            if hasattr(pool, "size"):
                db_pool_size = int(pool.size())  # type: ignore[call-arg]
            if hasattr(pool, "checkedin"):
                db_pool_checked_in = int(pool.checkedin())  # type: ignore[call-arg]
            if hasattr(pool, "checkedout"):
                db_pool_checked_out = int(pool.checkedout())  # type: ignore[call-arg]
            if hasattr(pool, "overflow"):
                db_pool_overflow = int(pool.overflow())  # type: ignore[call-arg]
            db_pool_status = str(pool.status()) if hasattr(pool, "status") else None
        except Exception:
            db_pool_status = None

        root = _repo_root()
        ai_runtime_log = root / "runtime/logs/dev/ai-runtime.log"
        data_hub_log = root / "data-hub/runtime/logs/data-hub.log"
        ai_runtime_log_updated_at = (
            datetime.utcfromtimestamp(ai_runtime_log.stat().st_mtime) if ai_runtime_log.exists() else None
        )
        data_hub_log_updated_at = datetime.utcfromtimestamp(data_hub_log.stat().st_mtime) if data_hub_log.exists() else None

        result = OpsRuntimeOut(
            as_of=now,
            source="local_process",
            process_uptime_seconds=round(uptime_sec, 1),
            process_thread_count=threading.active_count(),
            process_cpu_usage_pct=None,
            load_avg_1m=load_avg[0],
            load_avg_5m=load_avg[1],
            load_avg_15m=load_avg[2],
            db_pool_size=db_pool_size,
            db_pool_checked_in=db_pool_checked_in,
            db_pool_checked_out=db_pool_checked_out,
            db_pool_overflow=db_pool_overflow,
            db_pool_status=db_pool_status,
            jvm_metrics_available=False,
            ai_runtime_enabled=bool(settings.ai_runtime_enabled),
            ai_runtime_url=str(settings.ai_runtime_url),
            ai_runtime_log_updated_at=ai_runtime_log_updated_at,
            data_hub_log_updated_at=data_hub_log_updated_at,
        )
        if settings.ops_enable_external_metrics and settings.ops_runtime_metrics_url:
            payload = _http_get_text(settings.ops_runtime_metrics_url, float(settings.ops_metrics_timeout_seconds))
            if payload:
                runtime_overlay = self._parse_runtime_metrics_overlay(payload)
                result = result.model_copy(
                    update={
                        k: v
                        for k, v in {
                            "source": runtime_overlay.get("source", result.source),
                            "process_cpu_usage_pct": runtime_overlay.get("process_cpu_usage_pct", result.process_cpu_usage_pct),
                            "jvm_metrics_available": runtime_overlay.get("jvm_metrics_available", result.jvm_metrics_available),
                            "jvm_heap_used_mb": runtime_overlay.get("jvm_heap_used_mb", result.jvm_heap_used_mb),
                            "jvm_heap_max_mb": runtime_overlay.get("jvm_heap_max_mb", result.jvm_heap_max_mb),
                            "jvm_non_heap_used_mb": runtime_overlay.get("jvm_non_heap_used_mb", result.jvm_non_heap_used_mb),
                            "jvm_gc_count": runtime_overlay.get("jvm_gc_count", result.jvm_gc_count),
                            "jvm_gc_pause_ms": runtime_overlay.get("jvm_gc_pause_ms", result.jvm_gc_pause_ms),
                            "jvm_gc_pause_max_ms": runtime_overlay.get("jvm_gc_pause_max_ms", result.jvm_gc_pause_max_ms),
                            "jvm_thread_count": runtime_overlay.get("jvm_thread_count", result.jvm_thread_count),
                        }.items()
                        if v is not None
                    }
                )
        return result

    def _parse_runtime_metrics_overlay(self, payload: str) -> dict[str, object]:
        text = payload.strip()
        mb = 1024.0 * 1024.0
        if not text:
            return {}
        if text.startswith("{"):
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                return {}
            if not isinstance(body, dict):
                return {}
            heap_used = _first_json_metric(body, "jvm_heap_used_mb", "heap_used_mb")
            heap_max = _first_json_metric(body, "jvm_heap_max_mb", "heap_max_mb")
            non_heap = _first_json_metric(body, "jvm_non_heap_used_mb", "non_heap_used_mb")
            cpu_pct = _first_json_metric(body, "process_cpu_usage_pct", "cpu_usage_pct")
            gc_count = _first_json_metric(body, "jvm_gc_count", "gc_count")
            gc_pause = _first_json_metric(body, "jvm_gc_pause_ms", "gc_pause_ms")
            gc_pause_max = _first_json_metric(body, "jvm_gc_pause_max_ms", "gc_pause_max_ms")
            jvm_threads = _first_json_metric(body, "jvm_thread_count", "jvm_threads")
            available = any(v is not None for v in (heap_used, heap_max, non_heap, gc_count, gc_pause, gc_pause_max, jvm_threads))
            return {
                "source": "external_json",
                "process_cpu_usage_pct": cpu_pct,
                "jvm_metrics_available": bool(available),
                "jvm_heap_used_mb": heap_used,
                "jvm_heap_max_mb": heap_max,
                "jvm_non_heap_used_mb": non_heap,
                "jvm_gc_count": None if gc_count is None else int(gc_count),
                "jvm_gc_pause_ms": gc_pause,
                "jvm_gc_pause_max_ms": gc_pause_max,
                "jvm_thread_count": None if jvm_threads is None else int(jvm_threads),
            }

        samples = _parse_prometheus_samples(text)
        if not samples:
            return {}
        heap_used = _sum_prometheus(samples, "jvm_memory_used_bytes", 'area="heap"')
        heap_max = _sum_prometheus(samples, "jvm_memory_max_bytes", 'area="heap"')
        non_heap = _sum_prometheus(samples, "jvm_memory_used_bytes", 'area="nonheap"')
        gc_count = _sum_prometheus(samples, "jvm_gc_pause_seconds_count")
        if gc_count is None:
            gc_count = _sum_prometheus(samples, "jvm_gc_collection_seconds_count")
        gc_pause_sec = _sum_prometheus(samples, "jvm_gc_pause_seconds_sum")
        if gc_pause_sec is None:
            gc_pause_sec = _sum_prometheus(samples, "jvm_gc_collection_seconds_sum")
        gc_pause_max_sec = _sum_prometheus(samples, "jvm_gc_pause_seconds_max")
        if gc_pause_max_sec is None:
            gc_pause_max_sec = _sum_prometheus(samples, "jvm_gc_collection_seconds_max")
        cpu_ratio = _sum_prometheus(samples, "process_cpu_usage")
        if cpu_ratio is None:
            cpu_ratio = _sum_prometheus(samples, "system_cpu_usage")
        jvm_threads = _sum_prometheus(samples, "jvm_threads_live_threads")
        if jvm_threads is None:
            jvm_threads = _sum_prometheus(samples, "process_threads")
        available = any(v is not None for v in (heap_used, heap_max, non_heap, gc_count, gc_pause_sec, gc_pause_max_sec, jvm_threads))
        return {
            "source": "external_prometheus",
            "process_cpu_usage_pct": None if cpu_ratio is None else float(cpu_ratio) * 100.0,
            "jvm_metrics_available": bool(available),
            "jvm_heap_used_mb": None if heap_used is None else heap_used / mb,
            "jvm_heap_max_mb": None if heap_max is None else heap_max / mb,
            "jvm_non_heap_used_mb": None if non_heap is None else non_heap / mb,
            "jvm_gc_count": None if gc_count is None else int(gc_count),
            "jvm_gc_pause_ms": None if gc_pause_sec is None else gc_pause_sec * 1000.0,
            "jvm_gc_pause_max_ms": None if gc_pause_max_sec is None else gc_pause_max_sec * 1000.0,
            "jvm_thread_count": None if jvm_threads is None else int(jvm_threads),
        }

    def _rows_to_key_counts(self, rows: list[tuple[str, int]]) -> list[OpsKeyValueCount]:
        return [OpsKeyValueCount(key=str(k), count=int(v)) for k, v in rows]

    def _normalize_runtime_source(self, raw_source: object, *, fallback_used: Optional[bool]) -> str:
        source = str(raw_source or "").strip().lower()
        legacy_map = {
            "remote_ai_service": "ai_runtime_service",
            "remote_runtime": "ai_runtime_service",
            "ai_runtime": "ai_runtime_service",
            "local": "local_backend",
            "backend_local": "local_backend",
        }
        if source in legacy_map:
            return legacy_map[source]
        if source in {"ai_runtime_service", "local_backend"}:
            return source
        # Keep project clean: do not surface legacy/unknown runtime-source labels in Ops UI.
        # If missing, derive best effort from fallback marker; otherwise default to active runtime path.
        if fallback_used is True:
            return "local_backend"
        return "ai_runtime_service"

    def _effect_distribution_for_source(self, db: Session, source: str) -> tuple[list[OpsKeyValueCount], int, Optional[float]]:
        rows = db.execute(
            select(ControlActionFeedbackSample.actual_effect_label, func.count(ControlActionFeedbackSample.id))
            .where(ControlActionFeedbackSample.source == source)
            .group_by(ControlActionFeedbackSample.actual_effect_label)
        ).all()
        raw_map = {str(k or "unknown"): int(v) for k, v in rows}
        improved = raw_map.get("improved", 0)
        unchanged = raw_map.get("unchanged", 0)
        worse = raw_map.get("worse", 0)
        evaluable_total = improved + unchanged + worse
        ratio = (improved / evaluable_total) if evaluable_total > 0 else None
        ordered: list[OpsKeyValueCount] = [
            OpsKeyValueCount(key="improved", count=improved),
            OpsKeyValueCount(key="unchanged", count=unchanged),
            OpsKeyValueCount(key="worse", count=worse),
        ]
        for key, count in raw_map.items():
            if key not in {"improved", "unchanged", "worse"}:
                ordered.append(OpsKeyValueCount(key=key, count=count))
        sample_count = int(
            db.scalar(
                select(func.count(ControlActionFeedbackSample.id)).where(ControlActionFeedbackSample.source == source)
            )
            or 0
        )
        return ordered, sample_count, ratio

    def _build_learning_loop_metrics(self, db: Session) -> OpsLearningLoopOut:
        now = datetime.utcnow()
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        actions_total_rows = db.execute(
            select(ControlAction.source, func.count(ControlAction.id)).group_by(ControlAction.source)
        ).all()
        actions_24h_rows = db.execute(
            select(ControlAction.source, func.count(ControlAction.id))
            .where(ControlAction.applied_at >= day_ago)
            .group_by(ControlAction.source)
        ).all()

        status_rows = db.execute(
            select(ControlActionEvalJob.status, func.count(ControlActionEvalJob.id)).group_by(ControlActionEvalJob.status)
        ).all()
        status_map = {str(k): int(v) for k, v in status_rows}
        retry_pending = int(
            db.scalar(
                select(func.count(ControlActionEvalJob.id)).where(
                    ControlActionEvalJob.status == "pending",
                    ControlActionEvalJob.attempt_count > 0,
                )
            )
            or 0
        )
        pending_overdue = int(
            db.scalar(
                select(func.count(ControlActionEvalJob.id)).where(
                    ControlActionEvalJob.status == "pending",
                    ControlActionEvalJob.scheduled_at < now,
                )
            )
            or 0
        )

        worker_processed_24h = int(
            db.scalar(
                select(func.count(ControlActionEvalJob.id)).where(
                    ControlActionEvalJob.status.in_(["done", "insufficient_data", "failed"]),
                    ControlActionEvalJob.updated_at >= day_ago,
                )
            )
            or 0
        )
        worker_last_activity_at = db.scalar(
            select(func.max(ControlActionEvalJob.updated_at)).where(
                ControlActionEvalJob.status.in_(["done", "insufficient_data", "failed"])
            )
        )

        quality_rows = db.execute(
            select(ControlActionFeedbackSample.sample_quality, func.count(ControlActionFeedbackSample.id)).group_by(
                ControlActionFeedbackSample.sample_quality
            )
        ).all()
        effect_rows = db.execute(
            select(ControlActionFeedbackSample.actual_effect_label, func.count(ControlActionFeedbackSample.id)).group_by(
                ControlActionFeedbackSample.actual_effect_label
            )
        ).all()

        training_eligible_total = int(
            db.scalar(
                select(func.count(ControlActionFeedbackSample.id)).where(
                    ControlActionFeedbackSample.is_training_eligible.is_(True)
                )
            )
            or 0
        )
        training_eligible_7d = int(
            db.scalar(
                select(func.count(ControlActionFeedbackSample.id)).where(
                    ControlActionFeedbackSample.is_training_eligible.is_(True),
                    ControlActionFeedbackSample.created_at >= week_ago,
                )
            )
            or 0
        )

        eligible_daily_rows = db.execute(
            select(
                func.date_trunc("day", ControlActionFeedbackSample.created_at).label("bucket"),
                func.count(ControlActionFeedbackSample.id),
            )
            .where(
                ControlActionFeedbackSample.is_training_eligible.is_(True),
                ControlActionFeedbackSample.created_at >= week_ago,
            )
            .group_by("bucket")
            .order_by("bucket")
        ).all()
        eligible_daily = [
            OpsTrendPoint(ts=bucket, mqtt_ingress_tps=float(count), consume_tps=None, dropped_delta=None, queue_depth=None)
            for bucket, count in eligible_daily_rows
            if bucket is not None
        ]

        recent_rows = db.execute(
            select(
                ControlActionEvalJob.id,
                ControlActionEvalJob.control_action_id,
                ControlActionEvalJob.device_id,
                ControlAction.source,
                ControlActionEvalJob.status,
                ControlActionEvalJob.attempt_count,
                ControlActionEvalJob.scheduled_at,
                ControlActionEvalJob.updated_at,
                ControlActionEvalJob.last_error,
            )
            .join(ControlAction, ControlAction.id == ControlActionEvalJob.control_action_id)
            .order_by(ControlActionEvalJob.updated_at.desc())
            .limit(12)
        ).all()
        recent_jobs = [
            OpsRecentEvalJobOut(
                job_id=int(job_id),
                control_action_id=int(control_action_id),
                device_id=int(device_id),
                source=str(source),
                status=str(status),
                attempt_count=int(attempt_count),
                scheduled_at=scheduled_at,
                updated_at=updated_at,
                last_error=last_error,
            )
            for job_id, control_action_id, device_id, source, status, attempt_count, scheduled_at, updated_at, last_error in recent_rows
        ]

        return OpsLearningLoopOut(
            as_of=now,
            control_actions_by_source_total=self._rows_to_key_counts(actions_total_rows),
            control_actions_by_source_24h=self._rows_to_key_counts(actions_24h_rows),
            eval_jobs_by_status=OpsEvalJobStatusOut(
                pending=int(status_map.get("pending", 0)),
                running=int(status_map.get("running", 0)),
                done=int(status_map.get("done", 0)),
                retry_pending=retry_pending,
                terminal_insufficient=int(status_map.get("insufficient_data", 0)),
                failed=int(status_map.get("failed", 0)),
            ),
            pending_overdue=pending_overdue,
            worker_processed_24h=worker_processed_24h,
            worker_last_activity_at=worker_last_activity_at,
            sample_quality_distribution=self._rows_to_key_counts([(str(k or "unknown"), int(v)) for k, v in quality_rows]),
            training_eligible_total=training_eligible_total,
            training_eligible_7d=training_eligible_7d,
            training_eligible_daily_7d=eligible_daily,
            actual_effect_distribution=self._rows_to_key_counts([(str(k or "unknown"), int(v)) for k, v in effect_rows]),
            recent_jobs=recent_jobs,
        )

    def _model_artifact_info(self, path: Path) -> tuple[Optional[str], Optional[datetime]]:
        if not path.exists() or not path.is_dir():
            return None, None
        files = [p for p in path.rglob("*") if p.is_file() and not p.name.startswith(".")]
        if not files:
            return None, None
        latest = max(files, key=lambda p: p.stat().st_mtime)
        return str(latest.relative_to(_repo_root())), datetime.utcfromtimestamp(latest.stat().st_mtime)

    def _build_model_runtime_metrics(self, db: Session) -> OpsModelRuntimeOut:
        now = datetime.utcnow()
        root = _repo_root()
        artifacts_root = root / "hmi/backend/artifacts"

        active_version, last_promoted_at = self._model_artifact_info(artifacts_root / "active")
        candidate_version, _candidate_ts = self._model_artifact_info(artifacts_root / "candidates")

        trained_sources = [
            self._model_artifact_info(artifacts_root / "recommendation_success")[1],
            self._model_artifact_info(artifacts_root / "preview_gap")[1],
            self._model_artifact_info(artifacts_root / "problem_classifier")[1],
        ]
        trained_times = [t for t in trained_sources if t is not None]
        last_trained_at = max(trained_times) if trained_times else None

        archive_count = 0
        archive_dir = artifacts_root / "archive"
        if archive_dir.exists():
            archive_count = sum(1 for p in archive_dir.rglob("*") if p.is_file())

        recs = db.scalars(select(AIRecommendation).order_by(AIRecommendation.last_run_at.desc()).limit(300)).all()
        source_counter: Counter[str] = Counter()
        fallback_true = 0
        fallback_total = 0
        for rec in recs:
            meta = self._rec_service.read_storage_metadata(rec.suggestion)
            ard = meta.get("ard")
            if not isinstance(ard, dict):
                continue
            fallback_marker: Optional[bool] = bool(ard.get("fallback_used")) if "fallback_used" in ard else None
            src = self._normalize_runtime_source(ard.get("runtime_source"), fallback_used=fallback_marker)
            source_counter[src] += 1
            if "fallback_used" in ard:
                fallback_total += 1
                if bool(ard.get("fallback_used")):
                    fallback_true += 1

        day_ago = now - timedelta(hours=24)
        generated_24h = int(
            db.scalar(select(func.count(AIRecommendation.id)).where(AIRecommendation.last_run_at >= day_ago)) or 0
        )
        applied_24h = int(
            db.scalar(
                select(func.count(ControlAction.id)).where(
                    ControlAction.source == "ai_recommendation",
                    ControlAction.applied_at >= day_ago,
                )
            )
            or 0
        )

        fallback_ratio = (fallback_true / fallback_total) if fallback_total > 0 else None

        notes: list[str] = []
        if fallback_ratio is not None and fallback_ratio > 0.3:
            notes.append("Fallback ratio is high; inspect AI runtime connectivity or model readiness.")
        if active_version is None:
            notes.append("No active model artifact found in hmi/backend/artifacts/active.")
        if not settings.ai_runtime_enabled:
            notes.append("AI runtime is disabled in backend settings; local fallback path is expected.")

        ordered_sources = [
            OpsKeyValueCount(key="ai_runtime_service", count=int(source_counter.get("ai_runtime_service", 0))),
            OpsKeyValueCount(key="local_backend", count=int(source_counter.get("local_backend", 0))),
        ]

        return OpsModelRuntimeOut(
            as_of=now,
            active_model_version=active_version,
            candidate_model_version=candidate_version,
            last_trained_at=last_trained_at,
            last_promoted_at=last_promoted_at,
            archived_model_artifact_count=archive_count,
            runtime_source_breakdown=ordered_sources,
            fallback_ratio=fallback_ratio,
            recommendation_generated_24h=generated_24h,
            recommendation_applied_24h=applied_24h,
            ai_runtime_enabled=bool(settings.ai_runtime_enabled),
            notes=notes,
        )

    def _build_ai_overview_metrics(self, db: Session, models: OpsModelRuntimeOut) -> OpsAiOverviewOut:
        now = datetime.utcnow()
        day_ago = now - timedelta(hours=24)
        generated = int(models.recommendation_generated_24h or 0)
        applied = int(models.recommendation_applied_24h or 0)
        apply_rate = (applied / generated) if generated > 0 else None

        ai_actions_24h = int(
            db.scalar(
                select(func.count(ControlAction.id)).where(
                    ControlAction.source == "ai_recommendation",
                    ControlAction.applied_at >= day_ago,
                )
            )
            or 0
        )

        ai_dist, ai_samples, ai_ratio = self._effect_distribution_for_source(db, "ai_recommendation")
        manual_dist, manual_samples, manual_ratio = self._effect_distribution_for_source(db, "manual_user")
        fallback_ratio = models.fallback_ratio
        fallback_elevated = bool(fallback_ratio is not None and fallback_ratio > 0.3)
        return OpsAiOverviewOut(
            as_of=now,
            ai_runtime_enabled=bool(models.ai_runtime_enabled),
            ai_runtime_url=settings.ai_runtime_url,
            runtime_source_breakdown=models.runtime_source_breakdown,
            fallback_ratio=fallback_ratio,
            fallback_elevated=fallback_elevated,
            recommendation_generated_24h=generated,
            recommendation_applied_24h=applied,
            recommendation_apply_rate=apply_rate,
            ai_origin_control_actions_24h=ai_actions_24h,
            ai_effect_distribution=ai_dist,
            manual_effect_distribution=manual_dist,
            ai_improved_ratio=ai_ratio,
            manual_improved_ratio=manual_ratio,
            ai_sample_count=ai_samples,
            manual_sample_count=manual_samples,
        )

    def build_overview(self, db: Session) -> OpsOverviewOut:
        now = datetime.utcnow()
        data_hub = self._build_data_hub_metrics()
        runtime = self._build_runtime_metrics()
        models = self._build_model_runtime_metrics(db)
        ai_overview = self._build_ai_overview_metrics(db, models)
        learning = self._build_learning_loop_metrics(db)
        return OpsOverviewOut(
            as_of=now,
            data_hub=data_hub,
            runtime=runtime,
            ai_overview=ai_overview,
            learning_loop=learning,
            models=models,
        )

    def build_data_hub(self) -> OpsDataHubOut:
        return self._build_data_hub_metrics()

    def build_runtime(self) -> OpsRuntimeOut:
        return self._build_runtime_metrics()

    def build_learning_loop(self, db: Session) -> OpsLearningLoopOut:
        return self._build_learning_loop_metrics(db)

    def build_models(self, db: Session) -> OpsModelRuntimeOut:
        return self._build_model_runtime_metrics(db)


ops_console_service = OpsConsoleService()
