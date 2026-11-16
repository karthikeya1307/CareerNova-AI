"""Phase 8 review fixes: closed internships (M1, M2) and minor issues 1-5."""

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from assistant_support import ask, new_conversation, result_ids, seeded, source_ids, student  # noqa: F401
from backend import database
from backend.models import AssistantRateLimit, Internship, Message, SavedInternship

PAST = datetime.now(timezone.utc) - timedelta(days=2)
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


def run_matching(client, user):
    response = client.post(f"/matches/resumes/{user['resume_id']}?k=5", headers=user["headers"])
    assert response.status_code in (200, 201), response.text
    return [r["internship"]["internship_id"] for r in response.json()["results"]]


def llm_hour_count(user_id):
    with database.engine.connect() as conn:
        return conn.execute(select(func.coalesce(func.sum(AssistantRateLimit.count), 0)).where(
            AssistantRateLimit.user_id == user_id, AssistantRateLimit.bucket == "llm_hour")).scalar()


# ------------------------------------------------------------------
# M1: closed internships are never presented as current matches
# ------------------------------------------------------------------

def test_top_matches_hide_deactivated_and_expired_internships(client, student, seeded):
    ranked = run_matching(client, student)
    assert len(ranked) >= 3
    seeded.get(Internship, ranked[0]).is_active = False          # deactivated
    seeded.get(Internship, ranked[1]).deadline = PAST             # deadline passed
    seeded.get(Internship, ranked[2]).deadline = FUTURE           # still open
    seeded.commit()
    cid = new_conversation(client, student)
    top = ask(client, student, cid, "show my top matches")
    shown = result_ids(top)
    assert str(ranked[0]) not in shown and str(ranked[1]) not in shown
    assert shown[0] == str(ranked[2])
    assert "2 that are no longer open are not shown" in top["content"]
    assert any(w["code"] == "closed_matches_hidden" for w in top["warnings"])
    assert top["content"].splitlines()[1].startswith("1. ")       # numbering follows what is shown
    first = ask(client, student, cid, "why is the first one a good match?")
    assert source_ids(first, "internship") == [str(ranked[2])] and "no longer open" not in first["content"]


def test_all_matches_closed(client, student, seeded):
    for internship_id in run_matching(client, student):
        seeded.get(Internship, internship_id).is_active = False
    seeded.commit()
    cid = new_conversation(client, student)
    top = ask(client, student, cid, "show my top matches")
    assert "None of the internships in your latest match run are still open" in top["content"]
    assert top["result_set"] is None and top["suggested_actions"][0]["endpoint"].startswith("/matches/resumes/")


@pytest.mark.parametrize("change, reason", [
    ({"is_active": False}, "it has been deactivated"),
    ({"deadline": PAST}, "application deadline"),
])
def test_explanations_of_closed_internships_say_so(client, student, seeded, change, reason):
    ranked = run_matching(client, student)
    cid = new_conversation(client, student)
    ask(client, student, cid, "show my top matches")
    internship = seeded.get(Internship, ranked[0])
    for key, value in change.items():
        setattr(internship, key, value)
    seeded.commit()
    explain = ask(client, student, cid, f"explain my match score for internship #{ranked[0]}")
    lines = explain["content"].splitlines()
    assert "is no longer open" in lines[0] and "for reference" in lines[0].lower()
    assert "no longer open" in lines[1] and reason in lines[1]
    assert any(w["code"] == "internship_closed" for w in explain["warnings"])


def test_detail_and_gap_answers_flag_a_passed_deadline(client, student, seeded):
    target = seeded.get(Internship, student["open"][0])
    target.deadline = PAST
    seeded.commit()
    cid = new_conversation(client, student)
    detail = ask(client, student, cid, f"tell me more about internship #{target.internship_id}")
    assert "This internship is no longer open: its application deadline" in detail["content"]
    assert not any(a["endpoint"].startswith("/applications/bookmarks/") for a in detail["suggested_actions"])
    gap = ask(client, student, cid, "what skills am I missing for it?")
    assert "no longer open" in gap["content"]
    open_one = seeded.get(Internship, student["open"][1])
    open_one.deadline = FUTURE
    seeded.commit()
    fresh = ask(client, student, cid, f"tell me more about internship #{open_one.internship_id}")
    assert "no longer open" not in fresh["content"]


# ------------------------------------------------------------------
# M2: semantic search applies the same eligibility as the keyword fallback
# ------------------------------------------------------------------

def test_semantic_search_excludes_inactive_and_expired(client, student, seeded):
    from backend.services import embeddings, vector_index
    expired, inactive, future = (seeded.get(Internship, i) for i in student["open"][:3])
    expired.deadline, future.deadline = PAST, FUTURE
    seeded.commit()
    vector_index.rebuild_index(embeddings.get_embedder())        # index built while all three were active
    inactive.is_active = False
    seeded.commit()
    cid = new_conversation(client, student)
    found = set()
    for target in (expired, inactive, future):
        answer = ask(client, student, cid, f"find internships about {target.title} {target.company}")
        assert not any(w["code"] == "semantic_search_unavailable" for w in answer["warnings"])
        found |= set(result_ids(answer))
    assert str(expired.internship_id) not in found and str(inactive.internship_id) not in found
    assert str(future.internship_id) in found


# ------------------------------------------------------------------
# Minor 1: free text typed by the student never reaches the AI
# ------------------------------------------------------------------

THIRD_PARTY = ("Priya Sharma", "priya.sharma@acme.example", "98765 43210", "Rahul")


def test_reminders_documents_and_external_labels_are_not_sent(client, student, seeded, fake_llm):
    from backend.models import GeneratedDocument
    h = student["headers"]
    external = client.post("/applications", headers=h, json={
        "company_name": "Rahul's Studio", "title": "Intern for Priya Sharma", "contact_name": "Priya Sharma",
        "contact_email": "priya.sharma@acme.example", "notes": "call 98765 43210"}).json()
    client.post(f"/applications/{external['application_id']}/reminders", headers=h, json={
        "title": "Call Priya Sharma on 98765 43210 or priya.sharma@acme.example",
        "remind_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "description": "Rahul"})
    seeded.add(GeneratedDocument(user_id=student["user_id"], document_type="cover_letter",
                                 title="Letter for Priya Sharma", content="x"))
    seeded.commit()
    provider = fake_llm({"sentences": []})
    cid = new_conversation(client, student)
    for question in ("show my reminders", "show my applications", "show my documents"):
        ask(client, student, cid, question, use_llm=True, llm_consent=True)
    assert len(provider.calls) == 3
    sent = json.dumps([c["payload"] for c in provider.calls])
    for secret in THIRD_PARTY:
        assert secret.lower() not in sent.lower(), secret
    assert "an external application" in sent and "Cover letter (version 1)" in sent


def test_question_text_with_names_phones_and_emails_is_never_sent(client, student, fake_llm):
    provider = fake_llm({"sentences": []})
    cid = new_conversation(client, student)
    ask(client, student, cid, "Priya Sharma (priya.sharma@acme.example, 98765 43210) asked: what skills are on "
                              "my resume?", use_llm=True, llm_consent=True)
    payload = provider.calls[0]["payload"]
    assert set(payload) == {"topic", "facts"} and payload["topic"] == "the student's resume"
    for secret in THIRD_PARTY:
        assert secret.lower() not in json.dumps(payload).lower()


def test_ai_answer_is_verified_against_the_ai_safe_facts(client, student, fake_llm):
    h = student["headers"]
    client.post("/applications", headers=h, json={"company_name": "Rahul's Studio", "title": "Intern",
                                                  "status": "APPLIED"})
    fake_llm({"sentences": [{"text": "You have 1 application tracked so far.", "fact_ids": ["F1"]}]})
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "show my applications", use_llm=True, llm_consent=True)
    assert answer["generation_method"] in ("llm", "deterministic")      # verification decides; never an error
    sneaky = fake_llm({"sentences": [{"text": "Your application with Rahul's Studio is APPLIED.",
                                      "fact_ids": ["F1"]}]})
    leaked = ask(client, student, cid, "show my applications", use_llm=True, llm_consent=True)
    assert sneaky.calls and leaked["generation_method"] == "deterministic"   # name wasn't in what the AI saw


def test_capabilities_disclose_what_is_never_sent(client, student, fake_llm):
    fake_llm({})
    llm = client.get("/assistant/capabilities", headers=student["headers"]).json()["llm"]
    assert "Never sent: the text of your question" in llm["assistant_disclosure"]
    assert "reminder titles" in llm["assistant_disclosure"]


# ------------------------------------------------------------------
# Minor 2: only expected search errors fall back; database errors are safe
# ------------------------------------------------------------------

def test_index_and_embedding_errors_fall_back_to_keywords(client, student, monkeypatch):
    from backend.services import embeddings, vector_index

    def no_model(*args, **kwargs):
        raise embeddings.EmbeddingError("model unavailable")

    monkeypatch.setattr(vector_index, "search", no_model)
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "Find internships about data")
    assert any(w["code"] == "semantic_search_unavailable" for w in answer["warnings"])


def test_database_errors_are_not_swallowed_and_do_not_leak(client, student, seeded, monkeypatch):
    from backend.services import vector_index

    def broken(*args, **kwargs):
        raise OperationalError("SELECT secret_internal_query", {}, Exception("connection reset"))

    monkeypatch.setattr(vector_index, "search", broken)
    cid = new_conversation(client, student)
    response = client.post(f"/assistant/conversations/{cid}/messages", headers=student["headers"],
                           json={"message": "Find internships about data"})
    assert response.status_code == 503
    assert response.json() == {"detail": "The assistant could not answer right now. Please try again."}
    assert "secret_internal_query" not in response.text
    seeded.expire_all()
    assert seeded.scalar(select(func.count()).select_from(Message)) == 0          # nothing saved


def test_programming_errors_are_not_swallowed(client, student, monkeypatch):
    from backend.services import vector_index

    def bug(*args, **kwargs):
        raise ValueError("unexpected bug")

    monkeypatch.setattr(vector_index, "search", bug)
    cid = new_conversation(client, student)
    with pytest.raises(ValueError, match="unexpected bug"):
        client.post(f"/assistant/conversations/{cid}/messages", headers=student["headers"],
                    json={"message": "Find internships about data"})


# ------------------------------------------------------------------
# Minor 3: deleted bookmarks are marked unavailable
# ------------------------------------------------------------------

def test_deleted_bookmark_source_is_unavailable(client, student, seeded):
    h, iid = student["headers"], student["open"][0]
    client.post(f"/applications/bookmarks/{iid}", headers=h)
    cid = new_conversation(client, student)
    detail = ask(client, student, cid, f"tell me more about internship #{iid}")
    bookmark_ids = source_ids(detail, "bookmark")
    assert bookmark_ids and next(s for s in detail["sources"] if s["type"] == "bookmark")["available"] is True
    client.delete(f"/applications/bookmarks/{iid}", headers=h)
    history = client.get(f"/assistant/conversations/{cid}/messages", headers=h).json()
    shown = next(m for m in history if m["message_id"] == detail["message_id"])
    assert next(s for s in shown["sources"] if s["type"] == "bookmark")["available"] is False
    assert seeded.scalar(select(func.count()).select_from(SavedInternship)) == 0


# ------------------------------------------------------------------
# Minor 4: focus labels (behaviour unchanged after simplification)
# ------------------------------------------------------------------

def test_focus_label_comes_from_the_list_or_the_message(client, student, seeded):
    from backend.models import Conversation
    from backend.services.assistant.resolver import load_focus
    cid = new_conversation(client, student)
    listing = ask(client, student, cid, "Find internships about data")
    ask(client, student, cid, "tell me more about the second one")
    seeded.expire_all()
    focus, intent = load_focus(seeded, seeded.get(Conversation, cid))
    assert focus.id == result_ids(listing)[1] and focus.label == listing["result_set"]["items"][1]["label"]
    assert intent == "internship_detail"


# ------------------------------------------------------------------
# Minor 5: the hourly AI limit counts only real provider calls
# ------------------------------------------------------------------

def test_ai_requests_without_facts_do_not_count(client, student, fake_llm):
    provider = fake_llm({"sentences": []})
    cid = new_conversation(client, student)
    ask(client, student, cid, "hi", use_llm=True, llm_consent=True)
    ask(client, student, cid, "asdf qwerty", use_llm=True, llm_consent=True)
    assert provider.calls == [] and llm_hour_count(student["user_id"]) == 0


def test_ai_requests_with_facts_count_once_per_provider_call(client, student, fake_llm):
    provider = fake_llm({"sentences": []})
    cid = new_conversation(client, student)
    ask(client, student, cid, "What skills are on my resume?", use_llm=True, llm_consent=True)
    ask(client, student, cid, "show my application dashboard", use_llm=True, llm_consent=True)
    assert len(provider.calls) == 2 and llm_hour_count(student["user_id"]) == 2


def test_privacy_refusal_does_not_count(client, student, fake_llm, monkeypatch):
    from backend.services import llm_privacy
    monkeypatch.setattr(llm_privacy, "find_llm_payload_personal_data", lambda payload, details: ["name"])
    provider = fake_llm({"sentences": []})
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "What skills are on my resume?", use_llm=True, llm_consent=True)
    assert provider.calls == [] and llm_hour_count(student["user_id"]) == 0
    assert any(w["code"] == "privacy_guard" for w in answer["warnings"])


def test_concurrent_ai_calls_never_exceed_the_hourly_limit(student, monkeypatch):
    from backend.services.assistant import rate_limit
    from backend.services.assistant.llm_rewrite import CountingProvider
    from backend.services.llm.base import LLMError

    class Recorder:
        name, model = "fake", "fake-model"

        def __init__(self):
            self.calls, self.lock = 0, threading.Lock()

        def complete_json(self, system, user):
            with self.lock:
                self.calls += 1
            return {}

    monkeypatch.setitem(rate_limit.LIMITS, "llm_hour", 3)
    inner, barrier, errors = Recorder(), threading.Barrier(12), []

    def worker():
        counting = CountingProvider(inner, database.engine, student["user_id"])
        barrier.wait()
        try:
            counting.complete_json("s", "{}")
        except LLMError:
            errors.append(1)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert inner.calls == 3 and len(errors) == 9
