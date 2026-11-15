"""Shared fixtures and helpers for the Phase 7 application-tracking tests."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import or_, select

from backend.models import Internship
from backend.services.internship_seed import load_dataset, seed_internships, validate_records

SUBSET = load_dataset()[:20]
IST = timezone(timedelta(hours=5, minutes=30))


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def in_days(days: float, tz=timezone.utc) -> str:
    return (now_utc() + timedelta(days=days)).astimezone(tz).isoformat()


@pytest.fixture
def seeded(db_session):
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    return db_session


def open_internships(db, count=3):
    """Active internships whose deadline is still open."""
    return list(db.scalars(
        select(Internship).where(Internship.is_active.is_(True),
                                 or_(Internship.deadline.is_(None), Internship.deadline > now_utc()))
        .order_by(Internship.internship_id).limit(count)))


@pytest.fixture
def student(create_user, seeded):
    user = create_user()
    user["internships"] = [i.internship_id for i in open_internships(seeded, 4)]
    assert len(user["internships"]) >= 3
    return user


@pytest.fixture
def other(create_user, seeded):
    return create_user()


def create(client, user, **body):
    return client.post("/applications", headers=user["headers"], json=body)


def internal(client, user, index=0, **extra):
    response = create(client, user, internship_id=user["internships"][index], **extra)
    assert response.status_code == 201, response.text
    return response.json()


def external(client, user, **extra):
    body = {"company_name": "Acme Robotics", "title": "Software Intern", **extra}
    response = create(client, user, **body)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, user, application_id, status, **extra):
    return client.patch(f"/applications/{application_id}/status", headers=user["headers"],
                        json={"status": status, **extra})


def add_round(client, user, application_id, **extra):
    body = {"interview_type": "technical", "mode": "online", "scheduled_at": in_days(3), **extra}
    return client.post(f"/applications/{application_id}/interviews", headers=user["headers"], json=body)


def add_reminder(client, user, application_id, **extra):
    body = {"title": "Follow up with recruiter", "remind_at": in_days(2), **extra}
    return client.post(f"/applications/{application_id}/reminders", headers=user["headers"], json=body)


def history(client, user, application_id):
    return client.get(f"/applications/{application_id}/history", headers=user["headers"]).json()
