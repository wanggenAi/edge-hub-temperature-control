from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Role = Literal["viewer", "operator"]


class UserPublic(BaseModel):
  username: str
  display_name: str
  role: Role


class LoginRequest(BaseModel):
  username: str = Field(min_length=3, max_length=32)
  password: str = Field(min_length=4, max_length=64)


class TokenPayload(BaseModel):
  username: str
  role: Role
  exp: int


class TokenResponse(BaseModel):
  access_token: str
  token_type: str = "bearer"
  user: UserPublic
