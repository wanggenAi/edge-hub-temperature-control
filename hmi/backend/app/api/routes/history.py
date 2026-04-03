from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.auth import UserPublic
from app.models.hmi import HistoryResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=HistoryResponse)
def read_history(current_user: UserPublic = Depends(get_current_user)) -> HistoryResponse:
  del current_user
  return demo_data_service.get_history()
