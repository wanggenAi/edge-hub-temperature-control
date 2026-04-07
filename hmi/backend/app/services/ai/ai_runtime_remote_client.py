from __future__ import annotations

import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


class AIRuntimeRemoteClient:
    def __init__(self) -> None:
        self.base_url = str(settings.ai_runtime_remote_base_url).rstrip("/")
        self.timeout_s = max(1, int(settings.ai_runtime_remote_timeout_seconds))
        self.api_key = str(settings.ai_runtime_remote_api_key or "").strip()

    def _request_json(self, *, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        req = Request(f"{self.base_url}{path}", data=body, method=method.upper())
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("X-AI-Service-Key", self.api_key)
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"AI service HTTP error: {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"AI service unavailable: {exc.reason}") from exc

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("AI service returned invalid JSON") from exc
        if not isinstance(obj, dict):
            raise RuntimeError("AI service response is not an object")
        return obj

    def infer_runtime_decision(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._request_json(method="POST", path="/infer/runtime-decision", payload=payload)
        decision = obj.get("decision")
        if not isinstance(decision, dict):
            raise RuntimeError("AI service missing decision payload")
        return decision

