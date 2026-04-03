from __future__ import annotations

from pydantic import BaseModel, Field


class PermissionDefinition(BaseModel):
  key: str
  label: str
  description: str


class RoleDefinition(BaseModel):
  key: str
  name: str
  permissions: list[str]


class UserPublic(BaseModel):
  username: str
  display_name: str
  role: str
  permissions: list[str]


class ManagedUser(UserPublic):
  enabled: bool = True
  assigned_device_ids: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
  username: str = Field(min_length=3, max_length=32)
  password: str = Field(min_length=4, max_length=64)


class TokenPayload(BaseModel):
  username: str
  role: str
  exp: int


class TokenResponse(BaseModel):
  access_token: str
  token_type: str = "bearer"
  user: UserPublic


class UserUpsertRequest(BaseModel):
  username: str = Field(min_length=3, max_length=32)
  display_name: str = Field(min_length=2, max_length=64)
  role: str = Field(min_length=2, max_length=32)
  password: str | None = Field(default=None, min_length=4, max_length=64)
  enabled: bool = True
  device_ids: list[str] | None = None


class RoleUpsertRequest(BaseModel):
  key: str = Field(min_length=2, max_length=32)
  name: str = Field(min_length=2, max_length=64)
  permissions: list[str] = Field(default_factory=list)


class DeleteResult(BaseModel):
  deleted: bool = True
  resource: str
  key: str
