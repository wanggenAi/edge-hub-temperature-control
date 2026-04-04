from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.models.auth import UserPublic
from app.models.hmi import AIPageResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/recommendations", response_model=AIPageResponse)
def read_recommendations(
    device_id: str | None = Query(default=None),
    current_user: UserPublic = Depends(require_permission("ai.view")),
) -> AIPageResponse:
  return demo_data_service.get_ai_page(current_user.username, device_id)
