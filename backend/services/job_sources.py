"""Job-source tracking: where a listing came from, how fresh it is, and duplicate detection.

Nothing here fetches live jobs. Listings come from the curated dataset (labelled as sample
listings) or are added by administrators, who can record the source URL and posting date and mark
a listing as verified. Unknown values stay unknown (None); nothing is guessed.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Internship

STALE_AFTER = timedelta(days=30)
SOURCE_LABELS = {
    "dataset": "Sample listing (curated dataset)",
    "admin": "Added by an administrator",
    "manual": "Added manually",
}
SOURCES = tuple(SOURCE_LABELS)


def dedup_key(title: str | None, company: str | None, location: str | None) -> str:
    """sha256 of the normalised "title|company|location" (case, spacing and punctuation ignored).
    The same rule is used by migration e1f3a5c7b9d2 to backfill existing rows."""
    def norm(value):
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return hashlib.sha256(f"{norm(title)}|{norm(company)}|{norm(location)}".encode("utf-8")).hexdigest()


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def freshness(internship: Internship, now: datetime | None = None) -> str:
    """expired | verified (checked within 30 days) | stale (checked earlier) | unverified."""
    now = now or datetime.now(timezone.utc)
    deadline = _aware(internship.deadline)
    if not internship.is_active or (deadline is not None and deadline < now):
        return "expired"
    verified = _aware(internship.last_verified_at)
    if verified is None:
        return "unverified"
    return "verified" if now - verified <= STALE_AFTER else "stale"


def source_label(internship: Internship) -> str:
    return SOURCE_LABELS.get(internship.source, internship.source or "Unknown source")


def find_duplicate(db: Session, key: str, exclude_id: int | None = None) -> int | None:
    query = select(Internship.internship_id).where(Internship.dedup_key == key, Internship.is_active.is_(True))
    if exclude_id is not None:
        query = query.where(Internship.internship_id != exclude_id)
    return db.scalar(query.order_by(Internship.internship_id).limit(1))


def unique_listings(internships: list[Internship]) -> tuple[list[Internship], int]:
    """Keep the first listing for each dedup key; returns (listings, number hidden as duplicates)."""
    seen: set[str] = set()
    kept: list[Internship] = []
    for item in internships:
        key = item.dedup_key or dedup_key(item.title, item.company, item.location)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return kept, len(internships) - len(kept)
