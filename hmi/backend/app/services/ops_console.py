from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import statistics
import threading
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.models.entities import AIRecommendation, ControlAction, ControlActionEvalJob, ControlActionFeedbackSample, ModelLifecycleRun
from app.schemas.ops import (
    OpsAiConfusionMatrixOut,
    OpsAiDataQualityOut,
    OpsAiDriftDataHealthOut,
    OpsAiFeatureDriftOut,
    OpsAiOverviewOut,
    OpsAiHealthSummaryOut,
    OpsAiJudgmentOut,
    OpsAiLabelDriftOut,
    OpsAiModelEvaluationOut,
    OpsAiObservabilityOut,
    OpsAiOfflineEvaluationOut,
    OpsAiOnlineOutcomesOut,
    OpsAiOnlineWindowOut,
    OpsAiOutcomeBreakdownOut,
    OpsAiPerClassMetricOut,
    OpsAiRuntimeReliabilityOut,
    OpsAiWhyStatusOut,
    OpsDataHubOut,
    OpsEvalJobStatusOut,
    OpsKeyValueCount,
    OpsLearningLoopOut,
    OpsModelRuntimeOut,
    OpsModelLifecycleRunOut,
    OpsModelLifecycleStatusOut,
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


def _safe_float(raw: Any) -> Optional[float]:
    try:
        if raw is None:
            return None
        return float(raw)
    except (TypeError, ValueError):
        return None


def _safe_int(raw: Any) -> Optional[int]:
    try:
        if raw is None:
            return None
        return int(raw)
    except (TypeError, ValueError):
        return None


def _pct(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * max(0.0, min(1.0, q))
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def _ratio(num: int, den: int) -> Optional[float]:
    if den <= 0:
        return None
    return float(num) / float(den)


def _tone_for_value(value: str) -> str:
    v = str(value or "").strip().lower()
    if v in {"strong", "positive", "high"}:
        return "normal"
    if v in {"mixed", "medium", "moderate", "neutral", "unknown", "insufficient data"}:
        return "warning"
    return "critical"


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

    def _build_model_lifecycle_status(self, db: Session, *, limit: int = 20) -> OpsModelLifecycleStatusOut:
        rows = db.scalars(
            select(ModelLifecycleRun).order_by(ModelLifecycleRun.started_at.desc(), ModelLifecycleRun.id.desc()).limit(
                max(1, min(int(limit), 200))
            )
        ).all()
        last_run = rows[0] if rows else None
        last_promoted = next((x for x in rows if bool(x.promoted)), None)
        last_rejected = next((x for x in rows if x.status == "rejected"), None)
        last_skipped = next((x for x in rows if x.status == "skipped"), None)
        return OpsModelLifecycleStatusOut(
            as_of=datetime.utcnow(),
            enabled=bool(settings.model_lifecycle_enabled),
            check_interval_seconds=int(settings.model_lifecycle_check_interval_seconds),
            last_run_at=last_run.started_at if last_run else None,
            last_run_status=last_run.status if last_run else None,
            last_trigger_source=last_run.trigger_source if last_run else None,
            last_promoted_at=last_promoted.completed_at if last_promoted else None,
            last_promoted_model_family=last_promoted.model_family if last_promoted else None,
            last_rejected_at=last_rejected.completed_at if last_rejected else None,
            last_rejected_reason=last_rejected.reason if last_rejected else None,
            last_skipped_at=last_skipped.completed_at if last_skipped else None,
            last_skipped_reason=last_skipped.reason if last_skipped else None,
            recent_runs=[
                OpsModelLifecycleRunOut(
                    id=row.id,
                    lifecycle_run_id=row.lifecycle_run_id,
                    model_family=row.model_family,
                    trigger_source=row.trigger_source,
                    status=row.status,
                    promoted=bool(row.promoted),
                    dry_run=bool(row.dry_run),
                    reason=row.reason,
                    gate_reasons=[str(x) for x in (row.gate_reasons or [])],
                    training_sample_count=int(row.training_sample_count or 0),
                    new_eligible_samples_since_last=int(row.new_eligible_samples_since_last or 0),
                    recent_eligible_samples_7d=int(row.recent_eligible_samples_7d or 0),
                    validation_size=row.validation_size,
                    candidate_artifact_dir=row.candidate_artifact_dir,
                    active_artifact_dir_before=row.active_artifact_dir_before,
                    archive_artifact_dir=row.archive_artifact_dir,
                    comparison_summary=row.comparison_summary if isinstance(row.comparison_summary, dict) else None,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ],
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

    def _artifact_metrics_path(self, artifact_dir_name: str, metrics_file: str) -> Optional[Path]:
        root = _repo_root()
        path = root / "hmi/backend/artifacts" / artifact_dir_name / metrics_file
        if path.exists() and path.is_file():
            return path
        return None

    def _load_json_file(self, path: Optional[Path]) -> dict[str, Any]:
        if path is None:
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                body = json.load(f)
            return body if isinstance(body, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _pick_offline_model(self, body: dict[str, Any]) -> tuple[Optional[str], dict[str, Any]]:
        models = body.get("models")
        if not isinstance(models, dict) or not models:
            return None, {}
        if isinstance(models.get("baseline"), dict):
            return "baseline", dict(models.get("baseline") or {})
        for key, payload in models.items():
            if isinstance(payload, dict):
                return str(key), dict(payload)
        return None, {}

    def _build_confusion_note(self, labels: list[str], matrix: list[list[int]], model_scope: str) -> Optional[str]:
        if not labels or not matrix:
            return None
        strongest: Optional[tuple[str, int]] = None
        for i, row in enumerate(matrix):
            if i >= len(labels):
                continue
            for j, val in enumerate(row):
                if i == j or j >= len(labels):
                    continue
                if not isinstance(val, int):
                    continue
                if strongest is None or val > strongest[1]:
                    strongest = (f"{labels[i]} -> {labels[j]}", val)
        if strongest is None or strongest[1] <= 0:
            return f"{model_scope} confusion is relatively clean."
        return f"Most confusion: {strongest[0]} ({strongest[1]} samples)."

    def _build_model_evaluation(
        self,
        *,
        artifact_dir_name: str,
        metrics_file: str,
        expected_labels: list[str],
        model_scope: str,
    ) -> OpsAiModelEvaluationOut:
        path = self._artifact_metrics_path(artifact_dir_name, metrics_file)
        body = self._load_json_file(path)
        model_key, selected = self._pick_offline_model(body)
        report = selected.get("classification_report")
        report_map = report if isinstance(report, dict) else {}
        per_class: list[OpsAiPerClassMetricOut] = []
        for label in expected_labels:
            row = report_map.get(label)
            row_map = row if isinstance(row, dict) else {}
            per_class.append(
                OpsAiPerClassMetricOut(
                    label=label,
                    precision=_safe_float(row_map.get("precision")),
                    recall=_safe_float(row_map.get("recall")),
                    f1=_safe_float(row_map.get("f1-score")),
                    support=_safe_int(row_map.get("support")),
                )
            )
        labels_raw = selected.get("confusion_matrix_labels")
        labels = [str(item) for item in labels_raw] if isinstance(labels_raw, list) else []
        matrix_raw = selected.get("confusion_matrix")
        matrix: list[list[int]] = []
        if isinstance(matrix_raw, list):
            for row in matrix_raw:
                if isinstance(row, list):
                    matrix.append([int(v) for v in row if isinstance(v, (int, float))])
        training_label_distribution: list[OpsKeyValueCount] = []
        dataset = body.get("dataset")
        if isinstance(dataset, dict) and isinstance(dataset.get("label_distribution"), dict):
            dist_map = dataset.get("label_distribution") or {}
            for label in expected_labels:
                training_label_distribution.append(
                    OpsKeyValueCount(key=label, count=int(dist_map.get(label) or 0))
                )
        artifact_rel = str(path.relative_to(_repo_root())) if path is not None else None
        artifact_ts = datetime.utcfromtimestamp(path.stat().st_mtime) if path is not None else None
        return OpsAiModelEvaluationOut(
            model_key=model_key,
            model_name=str(selected.get("model_name")) if selected.get("model_name") is not None else None,
            artifact_path=artifact_rel,
            artifact_timestamp=artifact_ts,
            validation_size=_safe_int(selected.get("validation_size")),
            accuracy=_safe_float(selected.get("accuracy")),
            macro_precision=_safe_float(selected.get("macro_precision")),
            macro_recall=_safe_float(selected.get("macro_recall")),
            macro_f1=_safe_float(selected.get("macro_f1")),
            per_class=per_class,
            confusion=OpsAiConfusionMatrixOut(
                labels=labels,
                matrix=matrix,
                note=self._build_confusion_note(labels, matrix, model_scope=model_scope),
            ),
            training_label_distribution=training_label_distribution,
        )

    def _build_outcome_breakdown(self, db: Session, *, source: str, since: datetime) -> OpsAiOutcomeBreakdownOut:
        rows = db.execute(
            select(ControlActionFeedbackSample.actual_effect_label, func.count(ControlActionFeedbackSample.id))
            .where(
                ControlActionFeedbackSample.source == source,
                ControlActionFeedbackSample.applied_at >= since,
            )
            .group_by(ControlActionFeedbackSample.actual_effect_label)
        ).all()
        mapped = {str(k or "unknown"): int(v) for k, v in rows}
        improved = int(mapped.get("improved", 0))
        unchanged = int(mapped.get("unchanged", 0))
        worse = int(mapped.get("worse", 0))
        total = improved + unchanged + worse
        return OpsAiOutcomeBreakdownOut(
            improved=improved,
            unchanged=unchanged,
            worse=worse,
            total=total,
            improved_ratio=_ratio(improved, total),
            worse_ratio=_ratio(worse, total),
        )

    def _build_online_window(self, db: Session, *, label: str, since: datetime) -> OpsAiOnlineWindowOut:
        ai = self._build_outcome_breakdown(db, source="ai_recommendation", since=since)
        manual = self._build_outcome_breakdown(db, source="manual_user", since=since)
        delta = None
        if ai.improved_ratio is not None and manual.improved_ratio is not None:
            delta = ai.improved_ratio - manual.improved_ratio
        return OpsAiOnlineWindowOut(window=label, ai=ai, manual=manual, ai_vs_manual_improved_delta=delta)

    def _read_feature_samples(
        self,
        db: Session,
        *,
        feature: str,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> list[float]:
        if not hasattr(ControlActionFeedbackSample, feature):
            return []
        column = getattr(ControlActionFeedbackSample, feature)
        stmt = select(column).where(
            ControlActionFeedbackSample.is_training_eligible.is_(True),
            column.isnot(None),
        )
        if since is not None:
            stmt = stmt.where(ControlActionFeedbackSample.applied_at >= since)
        if until is not None:
            stmt = stmt.where(ControlActionFeedbackSample.applied_at < until)
        vals = [float(v) for v in db.scalars(stmt.limit(5000)).all() if isinstance(v, (int, float))]
        return vals

    def _feature_drift_level(self, delta_ratio: Optional[float]) -> str:
        if delta_ratio is None:
            return "Unknown"
        n = abs(delta_ratio)
        if n >= 0.4:
            return "High"
        if n >= 0.2:
            return "Medium"
        return "Low"

    def _aggregate_level(self, levels: list[str]) -> str:
        if any(l == "High" for l in levels):
            return "High"
        if any(l == "Medium" for l in levels):
            return "Medium"
        if any(l == "Low" for l in levels):
            return "Low"
        if any(l == "Insufficient data" for l in levels):
            return "Insufficient data"
        return "Unknown"

    def _build_drift_data_health(
        self,
        db: Session,
        *,
        success_eval: OpsAiModelEvaluationOut,
        gap_eval: OpsAiModelEvaluationOut,
    ) -> OpsAiDriftDataHealthOut:
        now = datetime.utcnow()
        recent_since = now - timedelta(days=7)
        baseline_until = recent_since
        features = [
            "mean_abs_error",
            "error_std",
            "zero_crossings",
            "in_band_ratio",
            "saturation_ratio",
            "delta_kp",
            "delta_ki",
            "delta_kd",
            "settling_sec",
            "overshoot_pct",
        ]
        rows: list[OpsAiFeatureDriftOut] = []
        levels: list[str] = []
        for feature in features:
            recent_vals = self._read_feature_samples(db, feature=feature, since=recent_since, until=None)
            baseline_vals = self._read_feature_samples(db, feature=feature, since=None, until=baseline_until)
            if len(baseline_vals) < 20:
                baseline_vals = self._read_feature_samples(db, feature=feature, since=None, until=None)
            if not recent_vals or not baseline_vals:
                levels.append("Insufficient data")
                rows.append(OpsAiFeatureDriftOut(feature=feature, status="Insufficient data"))
                continue
            baseline_mean = float(statistics.fmean(baseline_vals))
            recent_mean = float(statistics.fmean(recent_vals))
            denom = max(abs(baseline_mean), 1e-6)
            delta_ratio = (recent_mean - baseline_mean) / denom
            status = self._feature_drift_level(delta_ratio)
            levels.append(status)
            rows.append(
                OpsAiFeatureDriftOut(
                    feature=feature,
                    baseline_mean=baseline_mean,
                    baseline_p50=_pct(baseline_vals, 0.5),
                    baseline_p95=_pct(baseline_vals, 0.95),
                    recent_mean=recent_mean,
                    recent_p50=_pct(recent_vals, 0.5),
                    recent_p95=_pct(recent_vals, 0.95),
                    delta_ratio=delta_ratio,
                    status=status,
                )
            )

        label_rows: list[OpsAiLabelDriftOut] = []
        label_levels: list[str] = []

        def _label_ratio_map(rows_in: list[tuple[Optional[str], int]]) -> dict[str, float]:
            total = sum(v for _, v in rows_in)
            if total <= 0:
                return {}
            return {str(k): float(v) / float(total) for k, v in rows_in if k}

        success_train = {r.key: r.count for r in success_eval.training_label_distribution}
        gap_train = {r.key: r.count for r in gap_eval.training_label_distribution}
        success_train_total = sum(success_train.values())
        gap_train_total = sum(gap_train.values())

        success_live_rows = db.execute(
            select(ControlActionFeedbackSample.actual_effect_label, func.count(ControlActionFeedbackSample.id))
            .where(ControlActionFeedbackSample.applied_at >= recent_since)
            .group_by(ControlActionFeedbackSample.actual_effect_label)
        ).all()
        gap_live_rows = db.execute(
            select(ControlActionFeedbackSample.preview_gap_label, func.count(ControlActionFeedbackSample.id))
            .where(ControlActionFeedbackSample.applied_at >= recent_since)
            .group_by(ControlActionFeedbackSample.preview_gap_label)
        ).all()
        success_live = _label_ratio_map([(k, int(v)) for k, v in success_live_rows])
        gap_live = _label_ratio_map([(k, int(v)) for k, v in gap_live_rows])
        min_recent_label_samples = max(1, int(settings.ops_ai_judgment_min_drift_recent_samples))
        success_recent_labeled = int(sum(int(v) for k, v in success_live_rows if str(k or "") in {"improved", "unchanged", "worse"}))
        gap_recent_labeled = int(sum(int(v) for k, v in gap_live_rows if str(k or "") in {"low", "medium", "high"}))
        success_label_data_sufficient = success_recent_labeled >= min_recent_label_samples
        gap_label_data_sufficient = gap_recent_labeled >= min_recent_label_samples

        for label in ("improved", "unchanged", "worse"):
            train_ratio = (float(success_train.get(label, 0)) / float(success_train_total)) if success_train_total > 0 else None
            if not success_label_data_sufficient:
                live_ratio = None
                delta_abs = None
                row_status = "Insufficient data"
            else:
                live_ratio = float(success_live.get(label, 0.0))
                if train_ratio is None:
                    delta_abs = None
                    row_status = "Unknown"
                else:
                    delta_abs = abs(live_ratio - train_ratio)
                    row_status = "High" if delta_abs >= 0.25 else "Medium" if delta_abs >= 0.12 else "Low"
            if row_status in {"High", "Medium", "Low"}:
                label_levels.append(row_status)
            else:
                label_levels.append(row_status)
            label_rows.append(
                OpsAiLabelDriftOut(
                    label_group="success_label",
                    label=label,
                    training_ratio=train_ratio,
                    recent_ratio=live_ratio,
                    delta_abs=delta_abs,
                    status=row_status,
                )
            )
        for label in ("low", "medium", "high"):
            train_ratio = (float(gap_train.get(label, 0)) / float(gap_train_total)) if gap_train_total > 0 else None
            if not gap_label_data_sufficient:
                live_ratio = None
                delta_abs = None
                row_status = "Insufficient data"
            else:
                live_ratio = float(gap_live.get(label, 0.0))
                if train_ratio is None:
                    delta_abs = None
                    row_status = "Unknown"
                else:
                    delta_abs = abs(live_ratio - train_ratio)
                    row_status = "High" if delta_abs >= 0.25 else "Medium" if delta_abs >= 0.12 else "Low"
            if row_status in {"High", "Medium", "Low"}:
                label_levels.append(row_status)
            else:
                label_levels.append(row_status)
            label_rows.append(
                OpsAiLabelDriftOut(
                    label_group="preview_gap_label",
                    label=label,
                    training_ratio=train_ratio,
                    recent_ratio=live_ratio,
                    delta_abs=delta_abs,
                    status=row_status,
                )
            )

        recent_count = int(
            db.scalar(
                select(func.count(ControlActionFeedbackSample.id)).where(ControlActionFeedbackSample.applied_at >= recent_since)
            )
            or 0
        )
        recent_usable = int(
            db.scalar(
                select(func.count(ControlActionFeedbackSample.id)).where(
                    ControlActionFeedbackSample.applied_at >= recent_since,
                    ControlActionFeedbackSample.is_training_eligible.is_(True),
                )
            )
            or 0
        )
        quality_rows = db.execute(
            select(ControlActionFeedbackSample.sample_quality, func.count(ControlActionFeedbackSample.id))
            .where(ControlActionFeedbackSample.applied_at >= recent_since)
            .group_by(ControlActionFeedbackSample.sample_quality)
        ).all()
        success_live_labels = {str(k) for k, _ in success_live_rows if k}
        gap_live_labels = {str(k) for k, _ in gap_live_rows if k}
        label_coverage = f"success {len(success_live_labels)}/3, gap {len(gap_live_labels)}/3"
        return OpsAiDriftDataHealthOut(
            feature_drift_status=self._aggregate_level(levels),
            label_drift_status=self._aggregate_level(label_levels),
            feature_drift=rows,
            label_drift=label_rows,
            data_quality=OpsAiDataQualityOut(
                recent_feedback_sample_count=recent_count,
                usable_for_training_ratio=_ratio(recent_usable, recent_count),
                label_coverage=label_coverage,
                sample_quality_distribution=self._rows_to_key_counts(
                    [(str(k or "unknown"), int(v)) for k, v in quality_rows]
                ),
            ),
        )

    def _build_runtime_reliability(self, db: Session) -> OpsAiRuntimeReliabilityOut:
        recs = db.scalars(select(AIRecommendation).order_by(AIRecommendation.last_run_at.desc()).limit(500)).all()
        ranking_used_true = 0
        ranking_used_total = 0
        ranking_fb_true = 0
        ranking_fb_total = 0
        fallback_true = 0
        fallback_total = 0
        selected_counter: Counter[str] = Counter()
        selected_total = 0
        for rec in recs:
            meta = self._rec_service.read_storage_metadata(rec.suggestion)
            ard = meta.get("ard")
            if not isinstance(ard, dict):
                continue
            if "ranking_used" in ard:
                ranking_used_total += 1
                if bool(ard.get("ranking_used")):
                    ranking_used_true += 1
            if "ranking_fallback_used" in ard:
                ranking_fb_total += 1
                if bool(ard.get("ranking_fallback_used")):
                    ranking_fb_true += 1
            if "fallback_used" in ard:
                fallback_total += 1
                if bool(ard.get("fallback_used")):
                    fallback_true += 1
            candidate_id = str(ard.get("selected_candidate_id") or "").strip()
            if candidate_id:
                selected_counter[candidate_id] += 1
                selected_total += 1
        ordered = [OpsKeyValueCount(key=k, count=v) for k, v in selected_counter.most_common()]

        def _candidate_ratio(candidate_key: str) -> Optional[float]:
            return _ratio(int(selected_counter.get(candidate_key, 0)), selected_total)

        conservative_count = sum(v for k, v in selected_counter.items() if "conservative" in k)
        aggressive_count = sum(v for k, v in selected_counter.items() if "aggressive" in k)
        balance_count = sum(v for k, v in selected_counter.items() if "balance" in k)
        return OpsAiRuntimeReliabilityOut(
            ranking_used_ratio=_ratio(ranking_used_true, ranking_used_total),
            ranking_fallback_used_ratio=_ratio(ranking_fb_true, ranking_fb_total),
            runtime_fallback_ratio=_ratio(fallback_true, fallback_total),
            candidate_selection_distribution=ordered,
            rule_center_selected_ratio=_candidate_ratio("rule_center"),
            baseline_hold_selected_ratio=_candidate_ratio("baseline_hold"),
            conservative_selected_ratio=_ratio(conservative_count, selected_total),
            aggressive_selected_ratio=_ratio(aggressive_count, selected_total),
            balance_selected_ratio=_ratio(balance_count, selected_total),
        )

    def _derive_health_summary(
        self,
        *,
        success_eval: OpsAiModelEvaluationOut,
        gap_eval: OpsAiModelEvaluationOut,
        outcomes_7d: OpsAiOnlineWindowOut,
        drift: OpsAiDriftDataHealthOut,
        runtime: OpsAiRuntimeReliabilityOut,
    ) -> tuple[OpsAiHealthSummaryOut, OpsAiWhyStatusOut]:
        success_macro_f1 = success_eval.macro_f1
        gap_macro_f1 = gap_eval.macro_f1
        recall_worse = next((p.recall for p in success_eval.per_class if p.label == "worse"), None)
        recall_high = next((p.recall for p in gap_eval.per_class if p.label == "high"), None)
        fallback_ratio = runtime.runtime_fallback_ratio
        ai_ratio = outcomes_7d.ai.improved_ratio
        manual_ratio = outcomes_7d.manual.improved_ratio
        delta = outcomes_7d.ai_vs_manual_improved_delta
        reasons: list[str] = []
        artifact_max_age_days = max(1, int(settings.ops_ai_health_artifact_max_age_days))
        artifact_cutoff = datetime.utcnow() - timedelta(days=artifact_max_age_days)
        success_artifact_stale = (
            success_eval.artifact_timestamp is None or success_eval.artifact_timestamp < artifact_cutoff
        )
        gap_artifact_stale = gap_eval.artifact_timestamp is None or gap_eval.artifact_timestamp < artifact_cutoff

        if success_macro_f1 is None or gap_macro_f1 is None:
            status = "Untrusted"
            reasons.append("Offline evaluation artifacts are missing or unreadable.")
        elif success_artifact_stale or gap_artifact_stale:
            status = "Untrusted"
            reasons.append(f"Offline evaluation artifacts are stale (older than {artifact_max_age_days} days).")
        elif (
            recall_worse is not None and recall_worse < float(settings.ops_ai_health_untrusted_danger_recall_critical)
        ) or (
            recall_high is not None and recall_high < float(settings.ops_ai_health_untrusted_danger_recall_critical)
        ):
            status = "Untrusted"
            reasons.append("Dangerous-class recall is critically low.")
        elif (
            fallback_ratio is not None
            and fallback_ratio >= float(settings.ops_ai_health_untrusted_fallback_critical)
        ):
            status = "Untrusted"
            reasons.append("Runtime fallback is too high, so model-driven decisions are not reliable.")
        else:
            status = "Good"
            if (
                (success_macro_f1 is not None and success_macro_f1 < float(settings.ops_ai_health_poor_success_macro_f1_max))
                or (gap_macro_f1 is not None and gap_macro_f1 < float(settings.ops_ai_health_poor_gap_macro_f1_max))
                or (recall_worse is not None and recall_worse < float(settings.ops_ai_health_poor_danger_recall_max))
                or (recall_high is not None and recall_high < float(settings.ops_ai_health_poor_danger_recall_max))
                or (fallback_ratio is not None and fallback_ratio > float(settings.ops_ai_health_poor_fallback_min))
                or (delta is not None and delta < float(settings.ops_ai_health_poor_ai_manual_delta_min))
                or drift.feature_drift_status == "High"
                or drift.label_drift_status == "High"
            ):
                status = "Poor"
            elif (
                (success_macro_f1 is not None and success_macro_f1 < float(settings.ops_ai_health_watch_success_macro_f1_max))
                or (gap_macro_f1 is not None and gap_macro_f1 < float(settings.ops_ai_health_watch_gap_macro_f1_max))
                or (recall_worse is not None and recall_worse < float(settings.ops_ai_health_watch_danger_recall_max))
                or (recall_high is not None and recall_high < float(settings.ops_ai_health_watch_danger_recall_max))
                or (fallback_ratio is not None and fallback_ratio > float(settings.ops_ai_health_watch_fallback_min))
                or (delta is not None and delta < float(settings.ops_ai_health_watch_ai_manual_delta_min))
                or drift.feature_drift_status == "Medium"
                or drift.label_drift_status == "Medium"
            ):
                status = "Watch"

        if success_macro_f1 is not None:
            reasons.append(f"Success macro F1 {success_macro_f1:.3f}.")
        if gap_macro_f1 is not None:
            reasons.append(f"Preview-gap macro F1 {gap_macro_f1:.3f}.")
        if recall_worse is not None:
            reasons.append(f"Recall(worse) {recall_worse:.3f}.")
        if recall_high is not None:
            reasons.append(f"Recall(high) {recall_high:.3f}.")
        if fallback_ratio is not None:
            reasons.append(f"Fallback ratio {fallback_ratio * 100:.1f}%.")
        if delta is not None:
            reasons.append(f"AI vs manual improved delta {delta * 100:.1f}pp (7d).")
        reasons.append(f"Feature drift: {drift.feature_drift_status}.")
        reasons.append(f"Label drift: {drift.label_drift_status}.")

        if status == "Good":
            interpretation = "Models are healthy: macro F1 is stable, dangerous-class recall is acceptable, and fallback remains low."
        elif status == "Watch":
            interpretation = "Offline quality is acceptable, but one or more risk indicators need attention (dangerous-class recall, drift, or fallback)."
        elif status == "Poor":
            interpretation = "Model quality or production reliability is weak; investigate dangerous-class recall, drift, and online outcomes before trusting recommendations."
        else:
            interpretation = "Current AI outputs are not trustworthy due to severe recall/fallback issues or missing offline evidence."

        summary = " ".join(reasons[:3]) if reasons else "Status based on offline quality, online outcomes, drift, and runtime reliability."
        return (
            OpsAiHealthSummaryOut(
                overall_model_health=status,
                success_model_macro_f1=success_macro_f1,
                preview_gap_model_macro_f1=gap_macro_f1,
                recall_worse=recall_worse,
                recall_high_gap=recall_high,
                fallback_ratio=fallback_ratio,
                ai_improved_ratio=ai_ratio,
                manual_improved_ratio=manual_ratio,
                ai_vs_manual_improved_delta=delta,
                feature_drift_status=drift.feature_drift_status,
                label_drift_status=drift.label_drift_status,
                interpretation=interpretation,
            ),
            OpsAiWhyStatusOut(status=status, summary=summary, reasons=reasons),
        )

    def _build_authoritative_judgments(
        self,
        *,
        success_eval: OpsAiModelEvaluationOut,
        gap_eval: OpsAiModelEvaluationOut,
        outcomes_7d: OpsAiOnlineWindowOut,
        drift: OpsAiDriftDataHealthOut,
        runtime: OpsAiRuntimeReliabilityOut,
    ) -> dict[str, OpsAiJudgmentOut]:
        success_f1 = success_eval.macro_f1
        gap_f1 = gap_eval.macro_f1
        recall_worse = next((p.recall for p in success_eval.per_class if p.label == "worse"), None)
        recall_high = next((p.recall for p in gap_eval.per_class if p.label == "high"), None)
        success_n = int(success_eval.validation_size or 0)
        gap_n = int(gap_eval.validation_size or 0)
        min_validation_n = min(success_n, gap_n)

        # Offline quality
        if success_f1 is None or gap_f1 is None or recall_worse is None or recall_high is None:
            offline_value = "Untrusted"
        elif (
            success_f1 >= float(settings.ops_ai_judgment_offline_strong_success_macro_f1_min)
            and gap_f1 >= float(settings.ops_ai_judgment_offline_strong_gap_macro_f1_min)
            and recall_worse >= float(settings.ops_ai_judgment_offline_strong_danger_recall_min)
            and recall_high >= float(settings.ops_ai_judgment_offline_strong_danger_recall_min)
        ):
            offline_value = "Strong"
        elif (
            success_f1 < float(settings.ops_ai_judgment_offline_weak_success_macro_f1_max)
            or gap_f1 < float(settings.ops_ai_judgment_offline_weak_gap_macro_f1_max)
            or recall_worse < float(settings.ops_ai_judgment_offline_weak_danger_recall_max)
            or recall_high < float(settings.ops_ai_judgment_offline_weak_danger_recall_max)
        ):
            offline_value = "Weak"
        else:
            offline_value = "Mixed"
        offline_reason = (
            "Offline success-model quality is strong, and dangerous-class recall is acceptable."
            if offline_value == "Strong"
            else "Offline model quality is weak due to low macro F1 or low dangerous-class recall."
            if offline_value == "Weak"
            else "Offline model quality is untrusted because key offline metrics are missing."
            if offline_value == "Untrusted"
            else "Offline success-model quality is acceptable, but preview-gap quality or dangerous-class recall is only moderate."
        )

        # Evidence confidence
        recent_feedback = int(drift.data_quality.recent_feedback_sample_count or 0)
        min_validation_required = max(1, int(settings.ops_ai_judgment_min_validation_samples))
        min_drift_recent_required = max(1, int(settings.ops_ai_judgment_min_drift_recent_samples))
        ai_online_n = int(outcomes_7d.ai.total or 0)
        manual_online_n = int(outcomes_7d.manual.total or 0)
        min_online_required = max(1, int(settings.ops_ai_judgment_min_online_samples))
        if (
            min_validation_n < max(1, min_validation_required // 2)
            or recent_feedback < max(1, min_drift_recent_required // 2)
            or min(ai_online_n, manual_online_n) < max(1, min_online_required // 2)
        ):
            evidence_value = "Low"
        elif (
            min_validation_n < min_validation_required
            or recent_feedback < min_drift_recent_required
            or min(ai_online_n, manual_online_n) < min_online_required
        ):
            evidence_value = "Medium"
        else:
            evidence_value = "High"
        evidence_reason = (
            "Confidence is low because validation and/or recent evaluated sample sizes are too small."
            if evidence_value == "Low"
            else "Confidence is medium: evidence exists, but sample sizes are still limited."
            if evidence_value == "Medium"
            else "Confidence is high: validation and recent evidence volumes are adequate."
        )

        # Online usefulness
        ai_worse = outcomes_7d.ai.worse_ratio
        manual_worse = outcomes_7d.manual.worse_ratio
        delta = outcomes_7d.ai_vs_manual_improved_delta
        if min(ai_online_n, manual_online_n) < min_online_required or delta is None:
            online_value = "Unknown"
        elif (
            delta > float(settings.ops_ai_judgment_online_positive_delta_min)
            and (
                ai_worse is None
                or manual_worse is None
                or ai_worse <= manual_worse + float(settings.ops_ai_judgment_online_worse_guard_delta)
            )
        ):
            online_value = "Positive"
        elif (
            delta < float(settings.ops_ai_judgment_online_negative_delta_max)
            or (
                ai_worse is not None
                and manual_worse is not None
                and ai_worse > manual_worse + float(settings.ops_ai_judgment_online_worse_guard_delta)
            )
        ):
            online_value = "Negative"
        else:
            online_value = "Neutral"
        online_reason = (
            "Online usefulness is currently unknown because recent evaluated AI/manual samples are insufficient."
            if online_value == "Unknown"
            else "Online usefulness is positive: AI outcomes are outperforming manual with acceptable downside."
            if online_value == "Positive"
            else "Online usefulness is negative: AI outcomes are below manual or worse-case ratio is elevated."
            if online_value == "Negative"
            else "Online usefulness is currently neutral because AI and manual outcomes are close."
        )

        # Runtime influence
        ranking_used = runtime.ranking_used_ratio
        fallback = runtime.runtime_fallback_ratio
        rule_center = runtime.rule_center_selected_ratio
        non_rule_center = None if rule_center is None else max(0.0, 1.0 - float(rule_center))
        if fallback is not None and fallback >= float(settings.ops_ai_judgment_runtime_bypassed_fallback_min):
            runtime_value = "Bypassed"
        elif (
            ranking_used is not None
            and non_rule_center is not None
            and ranking_used >= float(settings.ops_ai_judgment_runtime_high_ranking_used_min)
            and non_rule_center >= float(settings.ops_ai_judgment_runtime_high_non_rule_center_min)
            and (fallback is None or fallback <= float(settings.ops_ai_judgment_runtime_high_fallback_max))
        ):
            runtime_value = "High"
        elif (
            ranking_used is not None
            and non_rule_center is not None
            and (
                ranking_used <= float(settings.ops_ai_judgment_runtime_low_ranking_used_max)
                or non_rule_center <= float(settings.ops_ai_judgment_runtime_low_non_rule_center_max)
            )
        ):
            runtime_value = "Low"
        else:
            runtime_value = "Moderate"
        runtime_reason = (
            "Runtime influence is bypassed because fallback is elevated and model path is not consistently active."
            if runtime_value == "Bypassed"
            else "Runtime influence is high: ranking is active and non-rule-center candidates are frequently selected."
            if runtime_value == "High"
            else "Runtime influence is low because most selections still remain at `rule_center` or ranking is rarely used."
            if runtime_value == "Low"
            else "Runtime influence is moderate: ranking contributes, but rule-center still has substantial share."
        )

        # Drift summaries
        drift_recent_required = max(1, int(settings.ops_ai_judgment_min_drift_recent_samples))
        if recent_feedback < drift_recent_required:
            drift_value = "Insufficient data"
            drift_reason = (
                "Drift is marked as insufficient data because recent feedback sample volume is too low for reliable drift conclusions."
            )
        else:
            drift_value = str(drift.feature_drift_status or "Unknown")
            drift_reason = f"Feature drift is currently {drift_value}. Missing recent data is not treated as high drift."
        label_drift_value = (
            "Insufficient data" if recent_feedback < drift_recent_required else str(drift.label_drift_status or "Unknown")
        )

        return {
            "offline_quality": OpsAiJudgmentOut(
                value=offline_value,
                tone=_tone_for_value(offline_value),
                reason=offline_reason,
            ),
            "evidence_confidence": OpsAiJudgmentOut(
                value=evidence_value,
                tone=_tone_for_value(evidence_value),
                reason=evidence_reason,
            ),
            "online_usefulness": OpsAiJudgmentOut(
                value=online_value,
                tone=_tone_for_value(online_value),
                reason=online_reason,
            ),
            "runtime_influence": OpsAiJudgmentOut(
                value=runtime_value,
                tone=_tone_for_value(runtime_value),
                reason=runtime_reason,
            ),
            "drift_summary": OpsAiJudgmentOut(
                value=drift_value,
                tone=_tone_for_value(drift_value),
                reason=drift_reason,
            ),
            "label_drift_summary": OpsAiJudgmentOut(
                value=label_drift_value,
                tone=_tone_for_value(label_drift_value),
                reason=(
                    "Label drift is marked as insufficient data because recent labeled distributions are not reliable."
                    if label_drift_value == "Insufficient data"
                    else f"Label drift is currently {label_drift_value}."
                ),
            ),
        }

    def build_ai_observability(self, db: Session) -> OpsAiObservabilityOut:
        now = datetime.utcnow()
        success_eval = self._build_model_evaluation(
            artifact_dir_name="recommendation_success",
            metrics_file="recommendation_success_metrics.json",
            expected_labels=["improved", "unchanged", "worse"],
            model_scope="Success model",
        )
        gap_eval = self._build_model_evaluation(
            artifact_dir_name="preview_gap",
            metrics_file="preview_gap_metrics.json",
            expected_labels=["low", "medium", "high"],
            model_scope="Preview-gap model",
        )
        online_24h = self._build_online_window(db, label="24h", since=now - timedelta(hours=24))
        online_7d = self._build_online_window(db, label="7d", since=now - timedelta(days=7))
        drift = self._build_drift_data_health(db, success_eval=success_eval, gap_eval=gap_eval)
        runtime = self._build_runtime_reliability(db)
        health_summary, why = self._derive_health_summary(
            success_eval=success_eval,
            gap_eval=gap_eval,
            outcomes_7d=online_7d,
            drift=drift,
            runtime=runtime,
        )
        judgments = self._build_authoritative_judgments(
            success_eval=success_eval,
            gap_eval=gap_eval,
            outcomes_7d=online_7d,
            drift=drift,
            runtime=runtime,
        )
        why = OpsAiWhyStatusOut(
            status=health_summary.overall_model_health,
            summary="; ".join(
                [
                    judgments["offline_quality"].reason,
                    judgments["evidence_confidence"].reason,
                    judgments["online_usefulness"].reason,
                    judgments["runtime_influence"].reason,
                ]
            ),
            reasons=[
                judgments["offline_quality"].reason,
                judgments["evidence_confidence"].reason,
                judgments["online_usefulness"].reason,
                judgments["runtime_influence"].reason,
            ],
        )
        return OpsAiObservabilityOut(
            as_of=now,
            health_summary=health_summary,
            why_this_status=why,
            offline_quality=judgments["offline_quality"],
            evidence_confidence=judgments["evidence_confidence"],
            online_usefulness=judgments["online_usefulness"],
            runtime_influence=judgments["runtime_influence"],
            drift_summary=judgments["drift_summary"],
            label_drift_summary=judgments["label_drift_summary"],
            offline_evaluation=OpsAiOfflineEvaluationOut(
                success_model=success_eval,
                preview_gap_model=gap_eval,
            ),
            online_outcome_quality=OpsAiOnlineOutcomesOut(window_24h=online_24h, window_7d=online_7d),
            drift_data_health=drift,
            runtime_reliability=runtime,
            model_lifecycle=self._build_model_lifecycle_status(db, limit=10),
            primary_metrics=[
                "success_model_macro_f1",
                "preview_gap_model_macro_f1",
                "recall_worse",
                "recall_high_gap",
                "ai_improved_ratio",
                "ai_vs_manual_improved_delta",
                "fallback_ratio",
                "feature_drift_status",
                "label_drift_status",
            ],
            secondary_metrics=[
                "accuracy",
                "macro_precision",
                "macro_recall",
                "per_class_precision_recall_f1",
                "confusion_matrix",
                "candidate_selection_distribution",
            ],
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
