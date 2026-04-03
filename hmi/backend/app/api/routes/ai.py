from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.auth import UserPublic
from app.models.hmi import AIRecommendation
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/recommendations", response_model=list[AIRecommendation])
def read_recommendations(current_user: UserPublic = Depends(get_current_user)) -> list[AIRecommendation]:
  del current_user
  return demo_data_service.get_ai_recommendations()
