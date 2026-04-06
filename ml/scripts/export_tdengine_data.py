#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import yaml


@dataclass
class TdConfig:
    url: str
    database: str
    username: str
    password: str


class TdengineRestClient:
    def __init__(self, cfg: TdConfig, timeout_s: int = 15) -> None:
        self.url = cfg.url.rstrip("/")
        self.database = cfg.database
        self.timeout_s = max(1, timeout_s)
        auth_raw = f"{cfg.username}:{cfg.password}".encode("utf-8")
        self.auth_header = "Basic " + base64.b64encode(auth_raw).decode("utf-8")

    def query(self, sql: str) -> Dict[str, Any]:
        payload = sql.encode("utf-8")
        req = Request(self.url, data=payload, method="POST")
        req.add_header("Authorization", self.auth_header)
        req.add_header("Content-Type", "text/plain; charset=UTF-8")

        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"TDengine HTTP error: {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"TDengine unavailable: {exc.reason}") from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("TDengine returned invalid JSON") from exc

        if int(body.get("code", -1)) != 0:
            raise RuntimeError(f"TDengine query failed: {body.get('desc', 'unknown error')}")

        return body


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config must be a mapping")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export TDengine tables to parquet for ML pipeline")
    parser.add_argument("--config", default="ml/configs/training_data.yaml", help="Path to pipeline YAML config")
    parser.add_argument("--device-id", action="append", default=[], help="Device ID filter (repeatable)")
    parser.add_argument("--start-ms", type=int, default=None, help="Inclusive start timestamp in milliseconds")
    parser.add_argument("--end-ms", type=int, default=None, help="Inclusive end timestamp in milliseconds")
    parser.add_argument("--tables", nargs="*", default=None, help="Override table list")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    return parser.parse_args()


def build_where_clause(device_ids: List[str], start_ms: Optional[int], end_ms: Optional[int]) -> str:
    clauses: List[str] = []
    if device_ids:
        quoted = ", ".join("'" + d.replace("'", "''") + "'" for d in device_ids)
        clauses.append(f"device_id IN ({quoted})")
    if start_ms is not None:
        clauses.append(f"ts >= {int(start_ms)}")
    if end_ms is not None:
        clauses.append(f"ts <= {int(end_ms)}")
    if not clauses:
        return ""
    return " WHERE " + " AND ".join(clauses)


def table_to_dataframe(body: Dict[str, Any]) -> pd.DataFrame:
    meta = body.get("column_meta") or []
    cols = [str(col[0]) for col in meta if isinstance(col, list) and len(col) >= 1]
    rows = body.get("data") or []
    df = pd.DataFrame(rows, columns=cols)
    return df


def maybe_add_ts_ms(df: pd.DataFrame) -> pd.DataFrame:
    if "ts" not in df.columns:
        return df
    # TDengine can return ts as int(ms), string datetime, or python-serializable datetime text.
    if pd.api.types.is_numeric_dtype(df["ts"]):
        df["ts_ms"] = pd.to_numeric(df["ts"], errors="coerce").astype("Int64")
    else:
        parsed = pd.to_datetime(df["ts"], errors="coerce", utc=True)
        df["ts_ms"] = (parsed.view("int64") // 1_000_000).astype("Int64")
    return df


def export_one_table(
    client: TdengineRestClient,
    *,
    table: str,
    where_clause: str,
    output_dir: Path,
) -> Path:
    sql = f"SELECT * FROM {client.database}.{table}{where_clause} ORDER BY ts ASC"
    body = client.query(sql)
    df = table_to_dataframe(body)
    if not df.empty:
        df = maybe_add_ts_ms(df)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{table}.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


def main() -> None:
    args = parse_args()
    cfg = load_yaml(Path(args.config))

    td_cfg_raw = cfg.get("tdengine", {})
    exp_cfg = cfg.get("export", {})

    td_cfg = TdConfig(
        url=str(td_cfg_raw.get("url", "http://127.0.0.1:6041/rest/sql")),
        database=str(td_cfg_raw.get("database", "edgehub")),
        username=str(td_cfg_raw.get("username", "root")),
        password=str(td_cfg_raw.get("password", "taosdata")),
    )

    tables = args.tables or exp_cfg.get("tables") or [
        "telemetry",
        "params_ack",
        "params_set",
        "telemetry_summary",
        "alarm_events",
    ]
    tables = [str(t) for t in tables]

    output_dir = Path(args.output_dir or exp_cfg.get("output_dir") or "ml/data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    env_device = os.getenv("ML_DEVICE_ID")
    device_ids: List[str] = list(args.device_id)
    if env_device and not device_ids:
        device_ids = [x.strip() for x in env_device.split(",") if x.strip()]

    where_clause = build_where_clause(device_ids, args.start_ms, args.end_ms)
    client = TdengineRestClient(td_cfg)

    print(f"[export] database={td_cfg.database} tables={tables}")
    if where_clause:
        print(f"[export] filter={where_clause.strip()}")

    for table in tables:
        try:
            out_path = export_one_table(client, table=table, where_clause=where_clause, output_dir=output_dir)
            print(f"[export] {table:<18} -> {out_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[export] {table:<18} failed: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
