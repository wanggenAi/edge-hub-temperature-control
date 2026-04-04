from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt

from app.core.config import settings

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        _, salt_b64, expected_b64 = hashed_password.split("$", 2)
    except ValueError:
        return False

    salt = base64.b64decode(salt_b64.encode("utf-8"))
    expected = base64.b64decode(expected_b64.encode("utf-8"))
    candidate = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(candidate, expected)


def get_password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode('utf-8')}${base64.b64encode(digest).decode('utf-8')}"


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
