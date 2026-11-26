"""Account invitations: an administrator creates a pending account, the person sets their own password.

* A token is 256 bits of randomness (``secrets.token_urlsafe(32)``); only its SHA-256 hash is stored.
* Single use: accepting marks it used. Issuing a new invitation revokes the previous one.
* Expires after ``INVITATION_EXPIRE_HOURS`` (72).
* Re-sending is rate-limited per account: at most one per ``RESEND_COOLDOWN`` and
  ``MAX_PER_DAY`` per 24 hours.
* Accepting sets the password (Argon2), verifies the email address (the link proves the person
  received the email) and signs out any other sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.models import AuthSession, User, UserInvitation
from backend.utils.tokens import generate_secure_token, hash_token

INVITATION_EXPIRE_HOURS = 72
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_PER_DAY = 5


class InvitationError(Exception):
    """``code`` is stable for the API: invalid | expired | used | revoked | inactive | not_pending |
    cooldown | daily_limit."""

    def __init__(self, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_pending(user: User) -> bool:
    """Created by an administrator and not activated yet."""
    return not user.is_verified


def latest(db: Session, user_id: int) -> UserInvitation | None:
    return db.scalar(select(UserInvitation).where(UserInvitation.user_id == user_id)
                     .order_by(UserInvitation.invitation_id.desc()).limit(1))


def status_of(invitation: UserInvitation | None) -> str:
    if invitation is None:
        return "none"
    if invitation.used_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if aware(invitation.expires_at) <= now():
        return "expired"
    return "pending"


def check_send_allowed(db: Session, user: User) -> None:
    if not user.is_active:
        raise InvitationError("inactive", "This account is deactivated. Reactivate it before inviting.")
    if not is_pending(user):
        raise InvitationError("not_pending", "This account is already active; no invitation is needed.")
    recent = latest(db, user.user_id)
    if recent is not None:
        elapsed = now() - aware(recent.created_at)
        if elapsed < RESEND_COOLDOWN:
            wait = int((RESEND_COOLDOWN - elapsed).total_seconds()) + 1
            raise InvitationError("cooldown", f"An invitation was just sent. Try again in {wait} seconds.", wait)
    sent_today = db.scalar(select(func.count()).select_from(UserInvitation).where(
        UserInvitation.user_id == user.user_id, UserInvitation.created_at > now() - timedelta(days=1)))
    if sent_today >= MAX_PER_DAY:
        raise InvitationError("daily_limit", f"At most {MAX_PER_DAY} invitations per account per day.", 3600)


def issue(db: Session, user: User, invited_by: User | None) -> tuple[UserInvitation, str]:
    """Revoke earlier open invitations and create a new one. Returns (invitation, raw token).

    The caller commits; the raw token is only used to build the email link and is never stored.
    """
    db.execute(update(UserInvitation)
               .where(UserInvitation.user_id == user.user_id, UserInvitation.used_at.is_(None),
                      UserInvitation.revoked_at.is_(None))
               .values(revoked_at=now()))
    raw = generate_secure_token()
    invitation = UserInvitation(
        user_id=user.user_id,
        invited_by_user_id=invited_by.user_id if invited_by is not None else None,
        token_hash=hash_token(raw),
        expires_at=now() + timedelta(hours=INVITATION_EXPIRE_HOURS),
    )
    db.add(invitation)
    db.flush()
    return invitation, raw


def find_valid(db: Session, raw_token: str, *, lock: bool = False) -> tuple[UserInvitation, User]:
    query = select(UserInvitation).where(UserInvitation.token_hash == hash_token(raw_token or ""))
    if lock:
        query = query.with_for_update()
    invitation = db.scalar(query)
    if invitation is None:
        raise InvitationError("invalid", "This invitation link is not valid.")
    if invitation.used_at is not None:
        raise InvitationError("used", "This invitation has already been used. Sign in instead.")
    if invitation.revoked_at is not None:
        raise InvitationError("revoked", "This invitation was replaced or cancelled. Ask for a new one.")
    if aware(invitation.expires_at) <= now():
        raise InvitationError("expired", "This invitation has expired. Ask your administrator for a new one.")
    user = db.get(User, invitation.user_id)
    if user is None or not user.is_active:
        raise InvitationError("inactive", "This account is not available. Contact your administrator.")
    return invitation, user


def accept(db: Session, raw_token: str, password_hash: str) -> User:
    """Set the password and activate the account. The caller commits."""
    invitation, user = find_valid(db, raw_token, lock=True)
    moment = now()
    user.password_hash = password_hash
    user.is_verified = True
    invitation.used_at = moment
    db.execute(update(AuthSession).where(AuthSession.user_id == user.user_id, AuthSession.revoked_at.is_(None))
               .values(revoked_at=moment))
    return user


def revoke_open(db: Session, user: User) -> int:
    return db.execute(update(UserInvitation)
                      .where(UserInvitation.user_id == user.user_id, UserInvitation.used_at.is_(None),
                             UserInvitation.revoked_at.is_(None))
                      .values(revoked_at=now())).rowcount
