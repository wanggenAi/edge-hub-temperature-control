from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.models.auth import UserPublic
from app.services.demo_data import demo_data_service

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserPublic:
  if credentials is None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
  payload = decode_access_token(credentials.credentials)
  return demo_data_service.get_user(payload.username)


def require_permission(permission_key: str):

  def dependency(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if permission_key not in current_user.permissions:
      raise HTTPException(
          status_code=status.HTTP_403_FORBIDDEN,
          detail=f"Permission required: {permission_key}",
      )
    return current_user

  return dependency
