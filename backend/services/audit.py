"""Audit log for administrative and security actions.

``record`` adds an ``AdminAuditEvent`` to the caller's session, so the event is
committed in the same transaction as the action it describes (both or neither).

Details may contain only identifiers, roles, labels and changed field values.
Any key that looks like a secret (password, hash, token, secret, credential,
SMTP, API key ...) is refused with ValueError, and values must be plain
scalars or short lists of scalars, so nothing sensitive can be logged by
accident.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from backend.models import AdminAuditEvent, User

ACTIONS = frozenset({
    "superadmin.bootstrap",
    "user.create",
    "user.role_change",
    "user.deactivate",
    "user.reactivate",
    "user.invite",
    "user.invite_revoke",
    "user.activate",
    "auth.login_locked",
    "index.rebuild",
    "internship.create",
    "internship.update",
    "internship.deactivate",
    "internship.verify",
})

FORBIDDEN_KEY = re.compile(r"pass|hash|token|secret|credential|smtp|api_?key|otp|jwt|cookie|session", re.IGNORECASE)
MAX_TEXT = 300
MAX_LIST = 50


class UnsafeAuditDetails(ValueError):
    """Raised when audit details would contain something that may be secret."""


def _clean(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_TEXT]
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_LIST:
            raise UnsafeAuditDetails("audit detail lists are limited in size")
        return [_clean(v) for v in value if v is None or isinstance(v, (bool, int, float, str))]
    raise UnsafeAuditDetails(f"unsupported audit detail type: {type(value).__name__}")


def safe_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if not isinstance(key, str) or FORBIDDEN_KEY.search(key):
            raise UnsafeAuditDetails(f"audit detail key not allowed: {key!r}")
        cleaned[key] = _clean(value)
    return cleaned


def user_label(user: User | None) -> str | None:
    if user is None:
        return None
    return f"{user.first_name} {user.last_name} <{user.email}>"[:MAX_TEXT]


def record(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    target: User | None = None,
    target_label: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AdminAuditEvent:
    if action not in ACTIONS:
        raise ValueError(f"unknown audit action: {action}")
    event = AdminAuditEvent(
        actor_user_id=actor.user_id if actor is not None else None,
        actor_role=actor.role if actor is not None else None,
        action=action,
        target_user_id=target.user_id if target is not None else None,
        target_label=(target_label or user_label(target)),
        details=safe_details(details),
        ip_address=(ip_address or None) and str(ip_address)[:64],
    )
    db.add(event)
    return event
