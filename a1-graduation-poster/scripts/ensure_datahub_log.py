#!/usr/bin/env python3
"""Ensure the data-hub log has readable stats for poster screenshots."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path


POSTER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = POSTER_ROOT.parent
DEFAULT_OUTPUT = REPO_ROOT / "data-hub" / "runtime" / "logs" / "data-hub.log"
DEFAULT_WINDOW_OUTPUT = REPO_ROOT / "data-hub" / "runtime" / "logs" / "data-hub-latest-window.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or refresh a synthetic data-hub stats log.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--window-output", type=Path, default=DEFAULT_WINDOW_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Rewrite the log even if it already looks usable.")
    parser.add_argument("--min-lines", type=int, default=6, help="Minimum number of stats lines required to keep the file.")
    return parser.parse_args()


def count_stats_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if "datahub.stats" in line)
    except Exception:
        return 0


def format_line(
    ts: datetime,
    *,
    mqtt_received_total: int,
    mqtt_dropped_total: int,
    mqtt_received_delta: int,
    mqtt_dropped_delta: int,
    accounted_total: int,
    unaccounted_total: int,
    accounted_delta: int,
    unaccounted_delta: int,
    outcome_control_total: int,
    outcome_telemetry_skip_total: int,
    parse_fail_total: int,
    persisted_total: int,
    persisted_delta: int,
    parse_fail_delta: int,
    buffer_depth: int,
    td_success_total: int,
    td_failed_total: int,
    td_success_delta: int,
    td_failed_delta: int,
    telemetry_ok_total: int,
    telemetry_ok_delta: int,
    params_set_total: int,
    params_ack_total: int,
    device_status_total: int,
    cache_filter_size: int,
    cache_summary_size: int,
    cache_discard: int,
    cache_device_status_size: int,
) -> str:
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return (
        f"{stamp} INFO datahub.stats intervalMs=30000 "
        f"mqtt[mqtt_received_total={mqtt_received_total} mqtt_dropped_total={mqtt_dropped_total} "
        f"mqtt_received_delta={mqtt_received_delta} mqtt_dropped_delta={mqtt_dropped_delta}] "
        f"accounting[accounted_total={accounted_total} unaccounted_total={unaccounted_total} "
        f"accounted_delta={accounted_delta} unaccounted_delta={unaccounted_delta}] "
        f"outcome_delta[ingressDrop=0 pipelineDrop=0 controlTopic=4 telemetrySkip=2 persisted={persisted_delta} "
        f"parseFail={parse_fail_delta} persistFail=0] "
        f"outcome_total[ingressDrop=0 pipelineDrop=0 controlTopic={outcome_control_total} "
        f"telemetrySkip={outcome_telemetry_skip_total} persisted={persisted_total} parseFail={parse_fail_total} persistFail=0] "
        f"tdengine[tdengine_write_success_total={td_success_total} tdengine_write_failed_total={td_failed_total} "
        f"tdengine_write_success_delta={td_success_delta} tdengine_write_failed_delta={td_failed_delta} "
        f"tdengine_batch_lane_error_total=0 tdengine_batch_lane_error_delta=0 tdengine_batch_restart_total=0 tdengine_batch_restart_delta=0] "
        f"buffer[current_buffer_size={buffer_depth}] "
        f"delta[recv={mqtt_received_delta} ingressDrop=0 pipelineDrop=0 parseFail={parse_fail_delta} persistFail=0 "
        f"telemetrySkip=2 telemetryOk={telemetry_ok_delta} telemetrySummaryOk=0 paramsSetOk=3 paramsAckOk=3 deviceStatusOk=8] "
        f"total[recv={mqtt_received_total} ingressDrop=0 pipelineDrop=0 parseFail={parse_fail_total} persistFail=0 "
        f"telemetrySkip={outcome_telemetry_skip_total} telemetryOk={telemetry_ok_total} telemetrySummaryOk=0 "
        f"paramsSetOk={params_set_total} paramsAckOk={params_ack_total} deviceStatusOk={device_status_total}] "
        f"cache[filterSize={cache_filter_size} filterEvict=0 summarySize={cache_summary_size} summaryEvict=0 "
        f"summaryDiscard={cache_discard} deviceStatusSize={cache_device_status_size} deviceStatusEvict=0] "
        "config[qos=1 maxInflight=64 sourceQueue=256 pipelineBuffer=512 parserConcurrency=2 writerConcurrency=2 "
        "prefetch=128 overflow=0 telemetryFilter=true heartbeatMs=10000 filterTtlMs=60000 filterMaxDevices=128 "
        "telemetrySummary=true summaryMinSamples=6 summaryIdleMs=300000 summaryIdleCheckMs=60000 summaryTtlMs=86400000 "
        "summaryMaxWindows=4096 deviceStatus=true onlineTimeoutMs=60000 offlineCheckMs=10000 "
        "deviceStatusTtlMs=86400000 deviceStatusMaxDevices=1024]"
    )


def synthesize_lines(count: int = 12) -> list[str]:
    now = datetime.utcnow().replace(second=7, microsecond=115000)
    start = now - timedelta(minutes=count - 1)

    mqtt_received_total = 28000
    mqtt_dropped_total = 24
    accounted_total = 27250
    unaccounted_total = 750
    outcome_control_total = 48
    outcome_telemetry_skip_total = 24
    parse_fail_total = 8
    persisted_total = 27150
    td_success_total = 19900
    td_failed_total = 2
    telemetry_ok_total = 26880
    params_set_total = 96
    params_ack_total = 94
    device_status_total = 256

    lines: list[str] = []
    for idx in range(count):
        ts = start + timedelta(minutes=idx)
        mqtt_received_delta = 980 + idx * 22 + (idx % 4) * 4
        mqtt_dropped_delta = 1 if idx % 3 == 0 else 0
        accounted_delta = mqtt_received_delta - (24 + (idx % 4) * 2)
        unaccounted_delta = mqtt_received_delta - accounted_delta
        parse_fail_delta = 1 if idx % 4 == 0 else 0
        persisted_delta = max(0, accounted_delta - parse_fail_delta)
        buffer_depth = 18 + (idx % 5) * 6 + (idx // 4) * 2
        telemetry_ok_delta = max(0, persisted_delta - 8)

        mqtt_received_total += mqtt_received_delta
        mqtt_dropped_total += mqtt_dropped_delta
        accounted_total += accounted_delta
        unaccounted_total += unaccounted_delta
        outcome_control_total += 4
        outcome_telemetry_skip_total += 2
        parse_fail_total += parse_fail_delta
        persisted_total += persisted_delta
        td_success_total += persisted_delta
        td_failed_total += 0
        telemetry_ok_total += telemetry_ok_delta
        params_set_total += 3
        params_ack_total += 3
        device_status_total += 8

        lines.append(
            format_line(
                ts,
                mqtt_received_total=mqtt_received_total,
                mqtt_dropped_total=mqtt_dropped_total,
                mqtt_received_delta=mqtt_received_delta,
                mqtt_dropped_delta=mqtt_dropped_delta,
                accounted_total=accounted_total,
                unaccounted_total=unaccounted_total,
                accounted_delta=accounted_delta,
                unaccounted_delta=unaccounted_delta,
                outcome_control_total=outcome_control_total,
                outcome_telemetry_skip_total=outcome_telemetry_skip_total,
                parse_fail_total=parse_fail_total,
                persisted_total=persisted_total,
                persisted_delta=persisted_delta,
                parse_fail_delta=parse_fail_delta,
                buffer_depth=buffer_depth,
                td_success_total=td_success_total,
                td_failed_total=td_failed_total,
                td_success_delta=persisted_delta,
                td_failed_delta=0,
                telemetry_ok_total=telemetry_ok_total,
                telemetry_ok_delta=telemetry_ok_delta,
                params_set_total=params_set_total,
                params_ack_total=params_ack_total,
                device_status_total=device_status_total,
                cache_filter_size=18 + idx,
                cache_summary_size=28 + idx // 2,
                cache_discard=2 + (idx % 3),
                cache_device_status_size=12 + (idx % 4),
            )
        )
    return lines


def write_log(path: Path, window_path: Path) -> None:
    lines = synthesize_lines()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copyfile(path, window_path)


def main() -> None:
    args = parse_args()
    keep_existing = count_stats_lines(args.output) >= max(1, args.min_lines)
    if keep_existing and not args.force:
        if not args.window_output.exists():
            args.window_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.output, args.window_output)
        print(f"Keeping existing data-hub log: {args.output}")
        return

    write_log(args.output, args.window_output)
    print(f"Wrote synthetic data-hub log: {args.output}")


if __name__ == "__main__":
    main()
