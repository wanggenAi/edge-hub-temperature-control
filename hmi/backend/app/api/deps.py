from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Device, Role, User, UserDevice

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db_dep() -> Generator[Session, None, None]:
    yield from get_db()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db_dep),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return user


def get_user_roles(user: User) -> list[str]:
    return [ur.role.name for ur in user.user_roles]


def require_roles(*required: str):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        user_roles = set(get_user_roles(current_user))
        if not user_roles.intersection(required):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return checker


def can_access_device(db: Session, user: User, device_id: int) -> bool:
    roles = set(get_user_roles(user))
    if "admin" in roles:
        return db.scalar(select(Device).where(Device.id == device_id)) is not None

    assignment = db.scalar(
        select(UserDevice).where(UserDevice.user_id == user.id, UserDevice.device_id == device_id)
    )
    return assignment is not None


def get_accessible_device_ids(db: Session, user: User) -> list[int]:
    roles = set(get_user_roles(user))
    if "admin" in roles:
        return db.scalars(select(Device.id)).all()
    return db.scalars(select(UserDevice.device_id).where(UserDevice.user_id == user.id)).all()


def require_device_access(
    device_id: int,
    db: Session,
    current_user: User,
) -> None:
    if not can_access_device(db, current_user, device_id):
        raise HTTPException(status_code=403, detail="No access to this device")
