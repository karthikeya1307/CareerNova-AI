"""Per-user rate limits for the assistant, safe under concurrency.

Each request increments a counter row with ONE atomic statement:

    INSERT ... VALUES (user, bucket, window, 1)
    ON CONFLICT (user_id, bucket, window_start)
    DO UPDATE SET count = assistant_rate_limits.count + 1
    RETURNING count

PostgreSQL serialises concurrent upserts on the same row, so every request
sees a distinct count and at most ``limit`` requests per window succeed -
there is no read-then-write race. The increment runs in its own short
transaction (committed immediately), so a rejected or failing request still
counts and the counter row is never held locked while an answer is built.
Rejected attempts count towards the window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

LIMITS = {"minute": 10, "day": 300, "llm_hour": 30}
WINDOWS = {"minute": timedelta(minutes=1), "day": timedelta(days=1), "llm_hour": timedelta(hours=1)}
KEEP_FOR = timedelta(days=2)

UPSERT = text("""
    INSERT INTO assistant_rate_limits (user_id, bucket, window_start, count)
    VALUES (:user_id, :bucket, :window_start, 1)
    ON CONFLICT (user_id, bucket, window_start)
    DO UPDATE SET count = assistant_rate_limits.count + 1
    RETURNING count
""")
CLEANUP = text("DELETE FROM assistant_rate_limits WHERE user_id = :user_id AND window_start < :before")


@dataclass
class RateLimited(Exception):
    bucket: str
    limit: int
    retry_after: int

    def __str__(self) -> str:
        return f"Too many requests ({self.bucket} limit {self.limit})."


def window_start(bucket: str, now: datetime) -> datetime:
    now = now.astimezone(timezone.utc)
    if bucket == "minute":
        return now.replace(second=0, microsecond=0)
    if bucket == "llm_hour":
        return now.replace(minute=0, second=0, microsecond=0)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def hit(engine: Engine, user_id: int, buckets: tuple[str, ...], now: datetime | None = None) -> None:
    """Count one request in each bucket; raise RateLimited if any limit is exceeded."""
    now = now or datetime.now(timezone.utc)
    exceeded: RateLimited | None = None
    with engine.begin() as conn:                 # separate, immediately committed transaction
        for bucket in buckets:
            start = window_start(bucket, now)
            count = conn.execute(UPSERT, {"user_id": user_id, "bucket": bucket, "window_start": start}).scalar()
            if count > LIMITS[bucket] and exceeded is None:
                retry = int((start + WINDOWS[bucket] - now).total_seconds()) + 1
                exceeded = RateLimited(bucket, LIMITS[bucket], max(retry, 1))
        conn.execute(CLEANUP, {"user_id": user_id, "before": now - KEEP_FOR})
    if exceeded is not None:
        raise exceeded
