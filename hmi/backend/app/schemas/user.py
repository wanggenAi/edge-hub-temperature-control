from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class UserBase(BaseModel):
    username: str
    email: EmailStr
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be blank")
        return text


class UserCreate(UserBase):
    password: str
    roles: list[str]

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be blank")
        return value


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
