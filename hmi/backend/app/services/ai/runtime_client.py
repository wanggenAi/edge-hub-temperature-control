from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from app.core.config import settings
from app.services.ai.schemas import RecommendationGenerateInput, RecommendationGenerateOutput


class AIRuntimeError(RuntimeError):
    pass


class AIRuntimeClient:
    def __init__(self) -> None:
        self.base_url = str(settings.ai_runtime_url).rstrip("/")
        self.timeout_seconds = max(0.2, float(settings.ai_runtime_timeout_seconds))

    def generate(self, payload: RecommendationGenerateInput) -> RecommendationGenerateOutput:
        endpoint = f"{self.base_url}/v1/recommendations/generate"
        body = json.dumps(payload.model_dump(mode="json"), separators=(",", ":")).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                if resp.status >= 400:
                    raise AIRuntimeError(f"runtime_http_{resp.status}")
        except error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8").strip()
            except Exception:
                detail = ""
            raise AIRuntimeError(f"runtime_http_{exc.code}: {detail or 'request failed'}") from exc
        except error.URLError as exc:
            raise AIRuntimeError(f"runtime_unreachable: {exc.reason}") from exc
        except Exception as exc:
            raise AIRuntimeError(f"runtime_call_failed: {exc}") from exc

        try:
            parsed: Any = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise AIRuntimeError("runtime_invalid_json") from exc
        try:
            return RecommendationGenerateOutput.model_validate(parsed)
        except Exception as exc:
            raise AIRuntimeError(f"runtime_invalid_payload: {exc}") from exc


ai_runtime_client = AIRuntimeClient()
