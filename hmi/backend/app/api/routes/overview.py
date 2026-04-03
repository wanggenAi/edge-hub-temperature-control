from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.auth import UserPublic
from app.models.hmi import OverviewResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", response_model=OverviewResponse)
def read_overview(current_user: UserPublic = Depends(get_current_user)) -> OverviewResponse:
  del current_user
  return demo_data_service.get_overview()
