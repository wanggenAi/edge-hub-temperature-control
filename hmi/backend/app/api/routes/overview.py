from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.models.auth import UserPublic
from app.models.hmi import OverviewResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", response_model=OverviewResponse)
def read_overview(
    device_id: str | None = Query(default=None),
    current_user: UserPublic = Depends(require_permission("overview.view")),
) -> OverviewResponse:
  return demo_data_service.get_overview(current_user.username, device_id)
