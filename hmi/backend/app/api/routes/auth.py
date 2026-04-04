from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_dep, get_user_roles
from app.core.security import create_access_token, verify_password
from app.models.entities import User
from app.schemas.auth import LoginRequest, MeResponse, Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db_dep)) -> Token:
    user = db.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.username))
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(subject=user.username)
    return Token(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        roles=get_user_roles(current_user),
    )
