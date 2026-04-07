from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TdQueryResult:
    columns: list[str]
    rows: list[list[Any]]


class TdengineClient:
    def __init__(self) -> None:
        auth_raw = f"{settings.tdengine_username}:{settings.tdengine_password}".encode("utf-8")
        self._auth_header = "Basic " + base64.b64encode(auth_raw).decode("utf-8")
        td_url = settings.tdengine_url.rstrip("/")
        self._endpoint = td_url + "/rest/sql"
        self._database = settings.tdengine_database
        self._timeout = max(1, settings.tdengine_query_timeout_seconds)
        self._local_no_proxy = False
        host = (urlparse(td_url).hostname or "").lower()
        parsed = urlparse(td_url)
        self._host = parsed.hostname or ""
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if host in {"127.0.0.1", "localhost", "::1"}:
            # Keep system/global proxy for everything else, but never proxy local TDengine.
            self._local_no_proxy = True
            self._opener = build_opener(ProxyHandler({}))
        else:
            self._opener = None

    def enabled(self) -> bool:
        return settings.tdengine_enabled or settings.data_source_mode.lower() == "tdengine"

    def query(self, sql: str) -> TdQueryResult:
        t0 = time.monotonic()
        sql_preview = " ".join(sql.strip().split())[:160]
        logger.debug(
            "[TD-QUERY] endpoint=%s host=%s port=%s no_proxy=%s sql=%s",
            self._endpoint,
            self._host,
            self._port,
            self._local_no_proxy,
            sql_preview,
        )
        payload = sql.encode("utf-8")
        req = Request(self._endpoint, data=payload, method="POST")
        req.add_header("Authorization", self._auth_header)
        req.add_header("Content-Type", "text/plain; charset=UTF-8")
        try:
            if self._opener is not None:
                response_ctx = self._opener.open(req, timeout=self._timeout)
            else:
                response_ctx = urlopen(req, timeout=self._timeout)
            with response_ctx as response:
                raw = response.read().decode("utf-8")
            logger.debug(
                "[TD-QUERY] done host=%s port=%s elapsed_ms=%s",
                self._host,
                self._port,
                int((time.monotonic() - t0) * 1000),
            )
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            logger.debug(
                "[TD-QUERY] http_error host=%s port=%s code=%s elapsed_ms=%s",
                self._host,
                self._port,
                exc.code,
                int((time.monotonic() - t0) * 1000),
            )
            raise HTTPException(status_code=502, detail=f"TDengine HTTP error: {exc.code} {detail}") from exc
        except URLError as exc:
            logger.debug(
                "[TD-QUERY] url_error host=%s port=%s reason=%s elapsed_ms=%s",
                self._host,
                self._port,
                exc.reason,
                int((time.monotonic() - t0) * 1000),
            )
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
        logger.debug(
            "[TD-QUERY] rows=%s host=%s port=%s",
            len(rows),
            self._host,
            self._port,
        )
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
