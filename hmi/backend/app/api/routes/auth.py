from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.models.auth import LoginRequest, TokenResponse, UserPublic
from app.services.demo_data import demo_data_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
  user = demo_data_service.authenticate(payload)
  token = create_access_token(user)
  return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserPublic)
def me(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
  return current_user
