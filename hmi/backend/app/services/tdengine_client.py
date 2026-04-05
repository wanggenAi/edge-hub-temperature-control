from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from app.core.config import settings


@dataclass
class TdQueryResult:
    columns: list[str]
    rows: list[list[Any]]


class TdengineClient:
    def __init__(self) -> None:
        auth_raw = f"{settings.tdengine_username}:{settings.tdengine_password}".encode("utf-8")
        self._auth_header = "Basic " + base64.b64encode(auth_raw).decode("utf-8")
        self._endpoint = settings.tdengine_url.rstrip("/") + "/rest/sql"
        self._database = settings.tdengine_database
        self._timeout = max(1, settings.tdengine_query_timeout_seconds)

    def enabled(self) -> bool:
        return settings.tdengine_enabled or settings.data_source_mode.lower() == "tdengine"

    def query(self, sql: str) -> TdQueryResult:
        payload = sql.encode("utf-8")
        req = Request(self._endpoint, data=payload, method="POST")
        req.add_header("Authorization", self._auth_header)
        req.add_header("Content-Type", "text/plain; charset=UTF-8")
        try:
            with urlopen(req, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise HTTPException(status_code=502, detail=f"TDengine HTTP error: {exc.code} {detail}") from exc
        except URLError as exc:
            raise HTTPException(status_code=502, detail=f"TDengine unavailable: {exc.reason}") from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="TDengine returned invalid JSON") from exc

        if int(body.get("code", -1)) != 0:
            raise HTTPException(status_code=502, detail=f"TDengine query failed: {body.get('desc', 'unknown error')}")

        meta = body.get("column_meta") or []
        columns = [str(col[0]) for col in meta if isinstance(col, list) and len(col) >= 1]
        rows = body.get("data") or []
        return TdQueryResult(columns=columns, rows=rows)

    def use_stmt(self) -> None:
        # Keep sql statements concise by centralizing database switch.
        self.query(f"USE {self._database}")

    @staticmethod
    def row_to_dict(columns: list[str], row: list[Any]) -> dict[str, Any]:
        return {columns[i]: row[i] if i < len(row) else None for i in range(len(columns))}

    @staticmethod
    def to_datetime(value: Any) -> datetime:
        if value is None:
            return datetime.now(tz=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return datetime.now(tz=timezone.utc)
