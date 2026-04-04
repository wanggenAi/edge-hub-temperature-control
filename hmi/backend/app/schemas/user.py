from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr
    is_active: bool = True


class UserCreate(UserBase):
    password: str
    roles: list[str]


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[list[str]] = None


class UserOut(UserBase):
    id: int
    created_at: datetime
    roles: list[str]

    class Config:
        from_attributes = True
