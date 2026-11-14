
from datetime import datetime, timezone

import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, AuthSession

from backend.utils.security import SECRET_KEY, ALGORITHM
from backend.utils.roles import ROLE_ADMIN, VALID_ROLES


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "sid"]}
        )

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        user_id = int(payload["sub"])
        session_id = int(payload["sid"])

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    except (TypeError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user or session information"
        )

    # Check the corresponding session in PostgreSQL.
    auth_session = db.get(AuthSession, session_id)

    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or has been revoked"
        )

    now = datetime.now(timezone.utc)
    session_expiry = auth_session.expires_at

    # Handle a naive timestamp defensively.
    if session_expiry.tzinfo is None:
        session_expiry = session_expiry.replace(
            tzinfo=timezone.utc
        )

    if session_expiry <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login session has expired"
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Login already requires verification; this also protects
    # tokens issued before an account became unverified.
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not verified"
        )

    return user


def require_roles(*allowed_roles: str):
    """Build a dependency that only admits users with one of the roles.

    Usage:
        @router.get("/x", dependencies=[Depends(require_roles(ROLE_ADMIN))])
        def handler(user: User = Depends(require_roles(ROLE_ADMIN))): ...
    """

    unknown = set(allowed_roles) - VALID_ROLES
    if not allowed_roles or unknown:
        raise ValueError(f"Invalid role configuration: {sorted(unknown)}")

    def role_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )
        return current_user

    return role_checker


# Convenience dependency for admin-only endpoints.
require_admin = require_roles(ROLE_ADMIN)
