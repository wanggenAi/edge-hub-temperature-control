from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_operator
from app.models.auth import UserPublic
from app.models.hmi import AckRecord, ParameterCommandRequest, ParameterPageResponse
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/params", tags=["params"])


@router.get("", response_model=ParameterPageResponse)
def read_parameters(current_user: UserPublic = Depends(get_current_user)) -> ParameterPageResponse:
  del current_user
  return demo_data_service.get_parameters_page()


@router.post("/commands", response_model=AckRecord)
def submit_parameters(
    payload: ParameterCommandRequest,
    current_user: UserPublic = Depends(require_operator),
) -> AckRecord:
  del current_user
  return demo_data_service.submit_parameters(payload)
