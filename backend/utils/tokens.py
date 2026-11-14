import hashlib
import secrets

from datetime import datetime, timedelta, timezone


def generate_secure_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_token_expiry(minutes: int) -> datetime:
    if minutes <= 0:
        raise ValueError("Token expiry must be greater than zero.")

    return datetime.now(timezone.utc) + timedelta(minutes=minutes)