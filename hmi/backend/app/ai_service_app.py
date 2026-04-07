from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.ai.ai_runtime_service import get_ai_runtime_service
from app.services.ai.schemas import RecommendationGenerateInput, RecommendationGenerateOutput

app = FastAPI(title="EdgeHub AI Runtime Service")
runtime_service = get_ai_runtime_service()


class RuntimeDecisionRequest(BaseModel):
    recommendation_input: dict[str, Any]
    base_recommendation_output: dict[str, Any]
    recommendation_id: int = 0


class RuntimeDecisionResponse(BaseModel):
    generated_at: datetime
    decision: dict[str, Any]
    recommendation_output: dict[str, Any]


def _check_api_key(x_ai_service_key: Optional[str]) -> None:
    expected = str(settings.ai_runtime_remote_api_key or "").strip()
    if not expected:
        return
    got = str(x_ai_service_key or "").strip()
    if got != expected:
        raise HTTPException(status_code=401, detail="Invalid AI service key")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "ai-runtime"}


@app.get("/models/status")
def model_status(x_ai_service_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _check_api_key(x_ai_service_key)
    return runtime_service.model_status()


@app.post("/models/reload")
def model_reload(x_ai_service_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _check_api_key(x_ai_service_key)
    runtime_service.reload_models()
    return {"ok": True, "status": runtime_service.model_status()}


@app.post("/infer/runtime-decision", response_model=RuntimeDecisionResponse)
def infer_runtime_decision(
    req: RuntimeDecisionRequest,
    x_ai_service_key: Optional[str] = Header(default=None),
) -> RuntimeDecisionResponse:
    _check_api_key(x_ai_service_key)
    payload = RecommendationGenerateInput.model_validate(req.recommendation_input)
    base_output = RecommendationGenerateOutput.model_validate(req.base_recommendation_output)
    decision = runtime_service.build_recommendation_decision(
        payload=payload,
        base_output=base_output,
        recommendation_id=int(req.recommendation_id),
    )
    updated = runtime_service.apply_decision_to_recommendation(output=base_output, decision=decision)
    return RuntimeDecisionResponse(
        generated_at=datetime.utcnow(),
        decision=decision,
        recommendation_output=updated.model_dump(mode="json"),
    )

