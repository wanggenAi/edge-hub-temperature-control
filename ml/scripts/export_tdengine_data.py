#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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


def build_where_clause(
    device_ids: List[str],
    start_ms: Optional[int],
    end_ms: Optional[int],
    *,
    device_column: str,
    time_column: str,
) -> str:
    clauses: List[str] = []
    if device_ids:
        quoted = ", ".join("'" + d.replace("'", "''") + "'" for d in device_ids)
        clauses.append(f"{device_column} IN ({quoted})")
    if start_ms is not None:
        clauses.append(f"{time_column} >= {int(start_ms)}")
    if end_ms is not None:
        clauses.append(f"{time_column} <= {int(end_ms)}")
    if not clauses:
        return ""
    return " WHERE " + " AND ".join(clauses)


def table_to_dataframe(body: Dict[str, Any]) -> pd.DataFrame:
    meta = body.get("column_meta") or []
    cols = [str(col[0]) for col in meta if isinstance(col, list) and len(col) >= 1]
    rows = body.get("data") or []
    df = pd.DataFrame(rows, columns=cols)
    return df


def maybe_add_ts_ms(df: pd.DataFrame, *, time_column: str) -> pd.DataFrame:
    if time_column not in df.columns:
        return df
    # TDengine can return ts as int(ms), string datetime, or python-serializable datetime text.
    if pd.api.types.is_numeric_dtype(df[time_column]):
        df["ts_ms"] = pd.to_numeric(df[time_column], errors="coerce").astype("Int64")
    else:
        parsed = pd.to_datetime(df[time_column], errors="coerce", utc=True)
        df["ts_ms"] = (parsed.view("int64") // 1_000_000).astype("Int64")
    return df


def resolve_table_mappings(
    exp_cfg: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    tables_cfg = exp_cfg.get("tables")
    if isinstance(tables_cfg, dict):
        mappings: Dict[str, Dict[str, str]] = {}
        for alias, row in tables_cfg.items():
            if isinstance(row, dict):
                name = str(row.get("name", alias))
                mappings[str(alias)] = {
                    "name": name,
                    "time_column": str(row.get("time_column", "ts")),
                    "device_column": str(row.get("device_column", "device_id")),
                    "order_by": str(row.get("order_by", "ts")),
                }
            else:
                name = str(alias)
                mappings[str(alias)] = {
                    "name": name,
                    "time_column": "ts",
                    "device_column": "device_id",
                    "order_by": "ts",
                }
        table_names = [mappings[k]["name"] for k in mappings]
        return mappings, table_names

    tables = tables_cfg if isinstance(tables_cfg, list) else [
        "telemetry",
        "params_ack",
        "params_set",
        "telemetry_summary",
        "alarm_events",
    ]
    table_names = [str(t) for t in tables]
    mappings = {
        t: {
            "name": t,
            "time_column": "ts",
            "device_column": "device_id",
            "order_by": "ts",
        }
        for t in table_names
    }
    return mappings, table_names


def export_one_table(
    client: TdengineRestClient,
    *,
    table_name: str,
    time_column: str,
    order_by: str,
    where_clause: str,
    output_dir: Path,
) -> Path:
    sql = f"SELECT * FROM {client.database}.{table_name}{where_clause} ORDER BY {order_by} ASC"
    body = client.query(sql)
    df = table_to_dataframe(body)
    if not df.empty:
        df = maybe_add_ts_ms(df, time_column=time_column)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{table_name}.parquet"
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

    table_mappings, configured_table_names = resolve_table_mappings(exp_cfg)
    tables = [str(t) for t in (args.tables or configured_table_names)]

    output_dir = Path(args.output_dir or exp_cfg.get("output_dir") or "ml/data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    env_device = os.getenv("ML_DEVICE_ID")
    device_ids: List[str] = list(args.device_id)
    if env_device and not device_ids:
        device_ids = [x.strip() for x in env_device.split(",") if x.strip()]

    client = TdengineRestClient(td_cfg)

    print(f"[export] database={td_cfg.database} tables={tables}")

    for table in tables:
        cfg_row = table_mappings.get(table)
        if cfg_row is None:
            # Support --tables for names not explicitly configured.
            cfg_row = {
                "name": table,
                "time_column": "ts",
                "device_column": "device_id",
                "order_by": "ts",
            }
        table_name = str(cfg_row.get("name", table))
        time_column = str(cfg_row.get("time_column", "ts"))
        device_column = str(cfg_row.get("device_column", "device_id"))
        order_by = str(cfg_row.get("order_by", "ts"))
        where_clause = build_where_clause(
            device_ids,
            args.start_ms,
            args.end_ms,
            device_column=device_column,
            time_column=time_column,
        )
        try:
            out_path = export_one_table(
                client,
                table_name=table_name,
                time_column=time_column,
                order_by=order_by,
                where_clause=where_clause,
                output_dir=output_dir,
            )
            if where_clause:
                print(f"[export] {table_name:<18} filter={where_clause.strip()}")
            print(f"[export] {table_name:<18} -> {out_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[export] {table_name:<18} failed: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
