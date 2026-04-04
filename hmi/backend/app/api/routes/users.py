from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db_dep, require_roles
from app.core.security import get_password_hash
from app.models.entities import Role, User, UserRole
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        roles=[x.role.name for x in user.user_roles],
    )


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> list[UserOut]:
    users = db.scalars(select(User)).all()
    return [to_user_out(u) for u in users]


@router.post("", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> UserOut:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()

    for role_name in payload.roles:
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return to_user_out(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> UserOut:
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email is not None:
        user.email = payload.email
    if payload.password is not None:
        user.password_hash = get_password_hash(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active

    if payload.roles is not None:
        user.user_roles.clear()
        db.flush()
        for role_name in payload.roles:
            role = db.scalar(select(Role).where(Role.name == role_name))
            if role:
                db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return to_user_out(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db_dep),
    _: User = Depends(require_roles("admin")),
) -> dict:
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}
