from __future__ import annotations

from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    roles: list[str]
