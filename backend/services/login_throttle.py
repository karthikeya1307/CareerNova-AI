"""Throttling of password sign-in attempts.

Each attempt first *reserves* a slot atomically (INSERT ... ON CONFLICT DO
UPDATE ... RETURNING count), before the password is checked. A reservation
beyond the limit is refused with ``LoginThrottled``, so even a burst of
concurrent attempts gets at most ``EMAIL_LIMIT`` password checks per window
for one email (and ``IP_LIMIT`` per client address).

* A successful sign-in (correct password) clears the email counter and gives
  the address its slot back.
* Counters use fixed windows of ``WINDOW``; ``Retry-After`` is the time until
  the window ends.
* Keys are SHA-256 hashes of the normalised email / client address, so no
  plaintext is stored, and the response is the same whether or not the email
  belongs to an account (no account enumeration).
* Counters run in their own, immediately committed transaction.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

EMAIL_LIMIT = 5
IP_LIMIT = 50
WINDOW = timedelta(minutes=15)
KEEP_FOR = timedelta(days=1)

UPSERT = text("""
    INSERT INTO auth_rate_limits (bucket, key_hash, window_start, count)
    VALUES (:bucket, :key_hash, :window_start, 1)
    ON CONFLICT (bucket, key_hash, window_start)
    DO UPDATE SET count = auth_rate_limits.count + 1
    RETURNING count
""")
RELEASE = text("""
    UPDATE auth_rate_limits SET count = count - 1
    WHERE bucket = :bucket AND key_hash = :key_hash AND window_start = :window_start AND count > 0
""")
CLEAR = text("DELETE FROM auth_rate_limits WHERE bucket = 'login_email' AND key_hash = :key_hash")
CLEANUP = text("DELETE FROM auth_rate_limits WHERE window_start < :before")


class LoginThrottled(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Too many failed sign-in attempts")
        self.retry_after = retry_after


@dataclass
class Reservation:
    email_key: str
    ip_key: str | None
    window_start: datetime
    email_count: int

    @property
    def locks_now(self) -> bool:
        """True for the attempt that uses the last allowed slot for this email."""
        return self.email_count == EMAIL_LIMIT


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def window_start(now: datetime) -> datetime:
    seconds = int(WINDOW.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=timezone.utc)


def reserve(engine: Engine, email: str, ip: str | None, now: datetime | None = None) -> Reservation:
    """Reserve one sign-in attempt, or raise LoginThrottled."""
    now = now or datetime.now(timezone.utc)
    start = window_start(now)
    email_key = _hash("email:" + email.strip().lower())
    ip_key = _hash("ip:" + ip) if ip else None
    with engine.begin() as conn:
        email_count = conn.execute(UPSERT, {"bucket": "login_email", "key_hash": email_key,
                                            "window_start": start}).scalar()
        ip_count = (conn.execute(UPSERT, {"bucket": "login_ip", "key_hash": ip_key,
                                          "window_start": start}).scalar() if ip_key else 0)
        conn.execute(CLEANUP, {"before": now - KEEP_FOR})
    if email_count > EMAIL_LIMIT or ip_count > IP_LIMIT:
        retry = int((start + WINDOW - now).total_seconds()) + 1
        raise LoginThrottled(max(retry, 1))
    return Reservation(email_key, ip_key, start, email_count)


def succeeded(engine: Engine, reservation: Reservation) -> None:
    """Correct password: clear the email counter and return the address slot."""
    with engine.begin() as conn:
        conn.execute(CLEAR, {"key_hash": reservation.email_key})
        if reservation.ip_key:
            conn.execute(RELEASE, {"bucket": "login_ip", "key_hash": reservation.ip_key,
                                   "window_start": reservation.window_start})
