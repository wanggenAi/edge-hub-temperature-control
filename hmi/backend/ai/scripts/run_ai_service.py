#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ai.recommendation_service import RecommendationService  # noqa: E402
from app.services.ai.recommendation_orchestrator import RecommendationOrchestrator  # noqa: E402
from app.services.ai.schemas import RecommendationGenerateInput, RecommendationGenerateOutput  # noqa: E402


app = FastAPI(title="EdgeHub AI Runtime Service")
recommendation_service = RecommendationService()
recommendation_orchestrator = RecommendationOrchestrator(recommendation_service)


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "ai-runtime", "ts": datetime.utcnow().isoformat()}


@app.post("/v1/recommendations/generate", response_model=RecommendationGenerateOutput)
def generate_recommendation(payload: RecommendationGenerateInput) -> RecommendationGenerateOutput:
    result = recommendation_orchestrator.generate_ranked_recommendation(
        payload=payload,
        runtime_source="ai_runtime_service",
        fallback_used=False,
    )
    return result.output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run standalone AI runtime service.")
    parser.add_argument("--host", default=os.getenv("AI_RUNTIME_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AI_RUNTIME_PORT", "8010")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "run_ai_service:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
