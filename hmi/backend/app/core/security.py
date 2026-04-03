from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException, status

from app.core.config import settings
from app.models.auth import TokenPayload, UserPublic


def hash_password(raw_password: str) -> str:
  return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def _b64url_encode(data: bytes) -> str:
  return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
  padding = "=" * (-len(data) % 4)
  return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def create_access_token(user: UserPublic) -> str:
  header = {"alg": "HS256", "typ": "JWT"}
  payload = TokenPayload(
      username=user.username,
      role=user.role,
      exp=int(time.time()) + settings.token_expire_minutes * 60,
  )
  encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
  encoded_payload = _b64url_encode(payload.model_dump_json().encode("utf-8"))
  signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
  signature = hmac.new(
      settings.token_secret.encode("utf-8"),
      signing_input,
      hashlib.sha256,
  ).digest()
  encoded_signature = _b64url_encode(signature)
  return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_access_token(token: str) -> TokenPayload:
  try:
    encoded_header, encoded_payload, encoded_signature = token.split(".")
  except ValueError as exc:
    raise _credentials_exception() from exc

  signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
  expected_signature = hmac.new(
      settings.token_secret.encode("utf-8"),
      signing_input,
      hashlib.sha256,
  ).digest()
  if not hmac.compare_digest(expected_signature, _b64url_decode(encoded_signature)):
    raise _credentials_exception()

  try:
    payload = json.loads(_b64url_decode(encoded_payload))
    token_payload = TokenPayload.model_validate(payload)
  except (ValueError, json.JSONDecodeError) as exc:
    raise _credentials_exception() from exc

  if token_payload.exp < int(time.time()):
    raise _credentials_exception(detail="Token expired.")
  return token_payload


def _credentials_exception(detail: str = "Could not validate credentials.") -> HTTPException:
  return HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail=detail,
      headers={"WWW-Authenticate": "Bearer"},
  )
