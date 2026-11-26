"""Account security (Phase 1): throttling of failed sign-in attempts (test database only)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from backend import database
from backend.models import AdminAuditEvent, AuthRateLimit
from backend.services import login_throttle
from conftest import DEFAULT_PASSWORD

WRONG = "WrongPassw0rd"


def login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_five_failures_lock_the_email_even_for_the_right_password(client, create_user):
    user = create_user()
    for _ in range(login_throttle.EMAIL_LIMIT):
        assert login(client, user["email"], WRONG).status_code == 401
    locked = login(client, user["email"], DEFAULT_PASSWORD)
    assert locked.status_code == 429
    assert 0 < int(locked.headers["Retry-After"]) <= 15 * 60
    assert "Too many failed sign-in attempts" in locked.json()["detail"]


def test_successful_sign_in_clears_the_counter(client, create_user):
    user = create_user()
    for _ in range(login_throttle.EMAIL_LIMIT - 1):
        assert login(client, user["email"], WRONG).status_code == 401
    assert login(client, user["email"], DEFAULT_PASSWORD).status_code == 200
    for _ in range(login_throttle.EMAIL_LIMIT):
        assert login(client, user["email"], WRONG).status_code == 401
    assert login(client, user["email"], WRONG).status_code == 429


def test_unknown_and_known_emails_behave_the_same(client, create_user):
    user = create_user()
    known = [login(client, user["email"], WRONG) for _ in range(6)]
    unknown = [login(client, "nobody@example.com", WRONG) for _ in range(6)]
    assert [r.status_code for r in known] == [r.status_code for r in unknown] == [401] * 5 + [429]
    assert [r.json()["detail"] for r in known] == [r.json()["detail"] for r in unknown]


def test_email_matching_is_case_insensitive(client, create_user):
    user = create_user()
    for variant in [user["email"].upper(), user["email"], " " + user["email"].title()] + [user["email"]] * 2:
        login(client, variant.strip(), WRONG)
    assert login(client, user["email"], DEFAULT_PASSWORD).status_code == 429


def test_concurrent_failed_attempts_never_exceed_the_limit_at_the_database():
    email = "burst@example.com"
    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(lambda _: _reserve(email, f"10.0.0.{_ % 3}"), range(40)))
    assert outcomes.count("allowed") == login_throttle.EMAIL_LIMIT
    assert outcomes.count("throttled") == 40 - login_throttle.EMAIL_LIMIT
    with database.engine.connect() as conn:
        count = conn.execute(text("SELECT count FROM auth_rate_limits WHERE bucket = 'login_email'")).scalar()
    assert count == 40                                       # every attempt was counted atomically


def _reserve(email, ip):
    try:
        login_throttle.reserve(database.engine, email, ip)
        return "allowed"
    except login_throttle.LoginThrottled:
        return "throttled"


def test_concurrent_failed_sign_ins_through_the_api(client, create_user):
    user = create_user()
    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(pool.map(lambda _: login(client, user["email"], WRONG).status_code, range(12)))
    assert sorted(codes) == [401] * login_throttle.EMAIL_LIMIT + [429] * (12 - login_throttle.EMAIL_LIMIT)
    assert login(client, user["email"], DEFAULT_PASSWORD).status_code == 429


def test_address_limit_covers_many_different_emails(client, monkeypatch):
    monkeypatch.setattr(login_throttle, "IP_LIMIT", 3)
    codes = [login(client, f"spray{n}@example.com", WRONG).status_code for n in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def test_lock_expires_with_the_window():
    now = datetime(2026, 11, 19, 10, 3, tzinfo=timezone.utc)
    for _ in range(login_throttle.EMAIL_LIMIT):
        login_throttle.reserve(database.engine, "window@example.com", None, now=now)
    with pytest.raises(login_throttle.LoginThrottled) as exc:
        login_throttle.reserve(database.engine, "window@example.com", None, now=now)
    assert exc.value.retry_after == 12 * 60 + 1                     # until 10:15
    later = now + timedelta(minutes=16)
    assert login_throttle.reserve(database.engine, "window@example.com", None, now=later).email_count == 1


def test_counters_store_only_hashes(client, db_session):
    login(client, "privacy@example.com", WRONG)
    db_session.expire_all()
    rows = db_session.scalars(select(AuthRateLimit)).all()
    assert {r.bucket for r in rows} == {"login_email", "login_ip"}
    assert all(len(r.key_hash) == 64 and "privacy" not in r.key_hash for r in rows)


def test_lock_is_audited_once_without_secrets(client, create_user, db_session):
    user = create_user()
    for _ in range(8):
        login(client, user["email"], WRONG)
    for _ in range(6):
        login(client, "ghost@example.com", WRONG)
    db_session.expire_all()
    events = db_session.scalars(select(AdminAuditEvent).where(
        AdminAuditEvent.action == "auth.login_locked").order_by(AdminAuditEvent.event_id)).all()
    assert len(events) == 2
    assert events[0].target_user_id == user["user_id"]
    assert events[1].target_user_id is None and events[1].target_label == "unknown account"
    assert "ghost" not in str(events[1].details) and events[0].details == {"limit": 5, "window_minutes": 15}
