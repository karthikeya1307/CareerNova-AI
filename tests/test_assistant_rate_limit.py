"""Phase 8: atomic, concurrency-safe rate limiting."""

import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from assistant_support import ask, new_conversation, seeded, student  # noqa: F401 (fixtures)
from backend import database
from backend.models import AssistantRateLimit, User
from backend.services.assistant import rate_limit


def test_limit_returns_429_with_retry_after(client, student, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "minute", 2)
    cid = new_conversation(client, student)
    ask(client, student, cid, "hi")
    ask(client, student, cid, "hi")
    response = client.post(f"/assistant/conversations/{cid}/messages", headers=student["headers"],
                           json={"message": "hi"})
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 61 and "Try again in" in response.json()["detail"]


def test_limits_are_per_user(client, student, create_user, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "minute", 1)
    other = create_user()
    mine, theirs = new_conversation(client, student), new_conversation(client, other)
    ask(client, student, mine, "hi")
    ask(client, student, mine, "hi", expect=429)
    ask(client, other, theirs, "hi")                     # unaffected


def test_ai_requests_have_their_own_hourly_limit(client, student, monkeypatch, fake_llm):
    """Over the AI limit the provider is not called; the standard answer is returned with a warning."""
    monkeypatch.setitem(rate_limit.LIMITS, "llm_hour", 1)
    provider = fake_llm({"sentences": []})
    cid = new_conversation(client, student)
    ask(client, student, cid, "What skills are on my resume?", use_llm=True, llm_consent=True)
    limited = ask(client, student, cid, "What skills are on my resume?", use_llm=True, llm_consent=True)
    assert len(provider.calls) == 1 and limited["generation_method"] == "deterministic"
    warning = next(w for w in limited["warnings"] if w["code"] == "ai_rate_limited")
    assert warning["retry_after"] >= 1
    ask(client, student, cid, "show my applications")    # plain answers still work


def test_concurrent_requests_never_exceed_the_limit(student, monkeypatch):
    """20 simultaneous requests on separate connections: exactly LIMIT succeed; the counter equals 20."""
    limit, attempts = 5, 20
    monkeypatch.setitem(rate_limit.LIMITS, "minute", limit)
    now = datetime.now(timezone.utc).replace(second=30)
    barrier, outcomes, lock = threading.Barrier(attempts), [], threading.Lock()

    def worker():
        barrier.wait()
        try:
            rate_limit.hit(database.engine, student["user_id"], ("minute",), now=now)
            result = "ok"
        except rate_limit.RateLimited:
            result = "limited"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert outcomes.count("ok") == limit and outcomes.count("limited") == attempts - limit
    with database.engine.connect() as conn:
        count = conn.execute(select(AssistantRateLimit.count).where(
            AssistantRateLimit.user_id == student["user_id"], AssistantRateLimit.bucket == "minute")).scalar()
    assert count == attempts


def test_windows_reset_and_old_rows_are_cleaned(student, monkeypatch):
    uid = student["user_id"]
    old = datetime.now(timezone.utc) - timedelta(days=3)
    rate_limit.hit(database.engine, uid, ("minute", "day"), now=old)
    now = datetime.now(timezone.utc)
    rate_limit.hit(database.engine, uid, ("minute",), now=now)
    with database.engine.connect() as conn:
        windows = conn.execute(select(AssistantRateLimit.window_start).where(AssistantRateLimit.user_id == uid)
                               ).scalars().all()
    assert len(windows) == 1                               # the 3-day-old rows were removed
    monkeypatch.setitem(rate_limit.LIMITS, "minute", 1)
    with pytest.raises(rate_limit.RateLimited) as exc:
        rate_limit.hit(database.engine, uid, ("minute",), now=now)
    assert exc.value.bucket == "minute"


def test_counters_are_deleted_with_the_account(student, seeded):
    rate_limit.hit(database.engine, student["user_id"], ("minute",))
    seeded.delete(seeded.get(User, student["user_id"]))
    seeded.commit()
    assert seeded.scalar(select(func.count()).select_from(AssistantRateLimit)) == 0
