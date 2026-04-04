from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.models.auth import UserPublic
from app.models.hmi import HistoryResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=HistoryResponse)
def read_history(
    device_id: str | None = Query(default=None),
    current_user: UserPublic = Depends(require_permission("history.view")),
) -> HistoryResponse:
  return demo_data_service.get_history(current_user.username, device_id)
