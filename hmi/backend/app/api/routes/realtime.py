from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.auth import UserPublic
from app.models.hmi import RealtimeSeriesResponse, TelemetrySnapshot
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.get("/snapshot", response_model=TelemetrySnapshot)
def read_snapshot(current_user: UserPublic = Depends(get_current_user)) -> TelemetrySnapshot:
  del current_user
  return demo_data_service.get_realtime_snapshot()


@router.get("/series", response_model=RealtimeSeriesResponse)
def read_series(current_user: UserPublic = Depends(get_current_user)) -> RealtimeSeriesResponse:
  del current_user
  return demo_data_service.get_realtime_series()
