import os
import secrets

from pathlib import Path
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is missing from .env")


def create_access_token(subject: str, session_id: int) -> str:
    """Create a short-lived JWT tied to a database session."""

    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "sid": session_id,
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        "type": "access"
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def create_refresh_token() -> str:
    """Create a secure opaque refresh token."""

    return secrets.token_urlsafe(48)
