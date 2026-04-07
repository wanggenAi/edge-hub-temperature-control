from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_dep, get_user_roles, require_device_access, require_roles
from app.models.entities import AIRecommendation, User
from app.schemas.ai_runtime import (
    AIRuntimeConfigOut,
    AIRuntimeConfigUpdate,
    AIRuntimeRecommendationDebugOut,
    AIRuntimeStatusOut,
)
from app.services.ai.ai_runtime_service import get_ai_runtime_service
from app.services.ai.recommendation_service import RecommendationService

router = APIRouter(prefix="/ai/runtime", tags=["ai-runtime"])

runtime_service = get_ai_runtime_service()
recommendation_service = RecommendationService()


@router.get("/config", response_model=AIRuntimeConfigOut)
def get_ai_runtime_config(current_user: User = Depends(get_current_user)) -> AIRuntimeConfigOut:
    _ = current_user
    return AIRuntimeConfigOut(**runtime_service.get_runtime_config())


@router.put("/config", response_model=AIRuntimeConfigOut)
def update_ai_runtime_config(
    payload: AIRuntimeConfigUpdate,
    current_user: User = Depends(require_roles("admin")),
) -> AIRuntimeConfigOut:
    _ = current_user
    next_cfg = runtime_service.update_runtime_config(payload.model_dump(exclude_none=True))
    return AIRuntimeConfigOut(**next_cfg)


@router.get("/status", response_model=AIRuntimeStatusOut)
def get_ai_runtime_status(current_user: User = Depends(get_current_user)) -> AIRuntimeStatusOut:
    _ = current_user
    return AIRuntimeStatusOut(**runtime_service.model_status())


@router.get("/recommendation-debug", response_model=AIRuntimeRecommendationDebugOut)
def get_ai_runtime_recommendation_debug(
    device_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db_dep),
    current_user: User = Depends(get_current_user),
) -> AIRuntimeRecommendationDebugOut:
    roles = set(get_user_roles(current_user))
    if device_id is not None:
        require_device_access(device_id, db, current_user)
        rec = db.scalar(
            select(AIRecommendation)
            .where(AIRecommendation.device_id == int(device_id))
            .order_by(AIRecommendation.last_run_at.desc())
        )
    else:
        if "admin" not in roles:
            raise HTTPException(status_code=400, detail="device_id is required for non-admin users")
        rec = db.scalar(select(AIRecommendation).order_by(AIRecommendation.last_run_at.desc()))

    if rec is not None:
        meta = recommendation_service.read_storage_metadata(rec.suggestion)
        decision = meta.get("ard") if isinstance(meta.get("ard"), dict) else None
        if isinstance(decision, dict):
            generated_at = rec.last_run_at
            return AIRuntimeRecommendationDebugOut(
                device_id=int(rec.device_id),
                recommendation_id=int(rec.id),
                source="recommendation_metadata",
                generated_at=generated_at,
                decision=decision,
            )

    if device_id is not None:
        cached = runtime_service.get_last_decision(device_id=int(device_id))
        if isinstance(cached, dict):
            return AIRuntimeRecommendationDebugOut(
                device_id=int(device_id),
                recommendation_id=None,
                source="runtime_cache",
                generated_at=datetime.utcnow(),
                decision=cached,
            )

    raise HTTPException(status_code=404, detail="No runtime recommendation decision found")
