"""Phase 6: interview APIs - sessions, modes, answers, progress, privacy."""

import io
from datetime import datetime, timedelta, timezone

import pytest
from docx import Document
from sqlalchemy import func, select

from backend.models import (
    GeneratedDocument, Internship, InterviewAnswer, InterviewQuestion, InterviewSession,
    MatchResult, Resume, User,
)
from backend.services.internship_seed import load_dataset, seed_internships, validate_records
from backend.services.llm.base import LLMError

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUBSET = load_dataset()[:20]


def resume_docx():
    document = Document()
    for line in [
        "Asha Rao", "asha@example.com | +91 90000 00002",
        "SUMMARY", "Backend developer who designs REST APIs.",
        "SKILLS", "Python, FastAPI, PostgreSQL, Docker, Git, SQL",
        "EDUCATION", "B.Tech Information Technology, Example Institute of Technology, 2026",
        "EXPERIENCE", "Software Intern, Example Systems, 2025",
        "Built 12 REST endpoints with FastAPI and PostgreSQL.",
        "PROJECTS", "Inventory API", "Deployed a Docker service used by 20 users.",
    ]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def seeded(db_session):
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    return db_session


@pytest.fixture
def student(client, create_user, seeded):
    user = create_user()
    upload = client.post("/resumes/upload", headers=user["headers"], files={"file": ("cv.docx", resume_docx(), DOCX)})
    assert upload.status_code == 201
    user["resume_id"] = upload.json()["resume_id"]
    user["internship_id"] = seeded.scalar(select(Internship.internship_id).order_by(Internship.internship_id))
    return user


def start(client, user, **extra):
    body = {"resume_id": user["resume_id"], "internship_id": user["internship_id"], **extra}
    return client.post("/interviews/sessions", headers=user["headers"], json=body)


def answer(client, user, session_id, question_id, text="I built it and as a result I learned a lot.", **extra):
    return client.post(f"/interviews/sessions/{session_id}/questions/{question_id}/answers",
                       headers=user["headers"], json={"answer_text": text, **extra})


# ------------------------------------------------------------------
# Authentication and ownership
# ------------------------------------------------------------------

@pytest.mark.parametrize("method, path", [
    ("GET", "/interviews/question-bank/version"), ("GET", "/interviews/questions/preview?resume_id=1"),
    ("POST", "/interviews/sessions"), ("GET", "/interviews/sessions"), ("GET", "/interviews/sessions/1"),
    ("POST", "/interviews/sessions/1/questions/1/reveal"), ("POST", "/interviews/sessions/1/questions/1/answers"),
    ("GET", "/interviews/sessions/1/questions/1/answers"), ("POST", "/interviews/sessions/1/complete"),
    ("DELETE", "/interviews/sessions/1"), ("GET", "/interviews/progress"),
])
def test_login_required(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_other_users_cannot_access(client, student, create_user):
    session = start(client, student).json()
    sid, qid = session["session_id"], session["questions"][0]["question_id"]
    other = create_user()
    h = other["headers"]
    assert client.post("/interviews/sessions", headers=h, json={"resume_id": student["resume_id"]}).status_code == 404
    assert client.get(f"/interviews/questions/preview?resume_id={student['resume_id']}", headers=h).status_code == 404
    for method, path in [("GET", f"/interviews/sessions/{sid}"),
                         ("POST", f"/interviews/sessions/{sid}/questions/{qid}/reveal"),
                         ("GET", f"/interviews/sessions/{sid}/questions/{qid}/answers"),
                         ("POST", f"/interviews/sessions/{sid}/complete"),
                         ("DELETE", f"/interviews/sessions/{sid}")]:
        assert client.request(method, path, headers=h).status_code == 404
    assert answer(client, other, sid, qid).status_code == 404
    assert client.get("/interviews/sessions", headers=h).json() == []
    assert client.get("/interviews/progress", headers=h).json()["sessions_total"] == 0


# ------------------------------------------------------------------
# Creation, modes and preview
# ------------------------------------------------------------------

def test_practice_session_shows_suggested_answers(client, student):
    response = start(client, student)
    assert response.status_code == 201
    session = response.json()
    assert session["mode"] == "practice" and session["status"] == "started"
    assert session["total_questions"] == len(session["questions"]) == 8
    assert [q["position"] for q in session["questions"]] == list(range(1, 9))
    assert {q["category"] for q in session["questions"]} == {"technical", "project", "behavioral", "internship"}
    assert all(q["suggested_answer"] and q["key_points"] for q in session["questions"])
    assert session["generation_method"] == "deterministic"


def test_mock_mode_hides_answers_until_answered_or_revealed(client, student):
    session = start(client, student, mode="mock", time_limit_seconds=120).json()
    sid = session["session_id"]
    first, second = session["questions"][0], session["questions"][1]
    assert all(q["suggested_answer"] is None and q["key_points"] is None for q in session["questions"])
    assert first["time_limit_seconds"] == 120

    revealed = client.post(f"/interviews/sessions/{sid}/questions/{first['question_id']}/reveal",
                           headers=student["headers"]).json()
    assert revealed["revealed"] and revealed["suggested_answer"]

    answer(client, student, sid, second["question_id"], time_taken_seconds=150)
    detail = client.get(f"/interviews/sessions/{sid}", headers=student["headers"]).json()
    second_now = next(q for q in detail["questions"] if q["question_id"] == second["question_id"])
    assert second_now["suggested_answer"] is not None
    assert second_now["evaluation"]["over_time_limit"] is True
    assert all(q["suggested_answer"] is None for q in detail["questions"][2:])


def test_preview_does_not_save(client, student, seeded):
    response = client.get(f"/interviews/questions/preview?resume_id={student['resume_id']}"
                          f"&internship_id={student['internship_id']}&technical=2&project=1&behavioral=1&internship=0",
                          headers=student["headers"])
    assert response.status_code == 200 and len(response.json()) == 4
    assert seeded.scalar(select(func.count()).select_from(InterviewSession)) == 0
    bad = client.get(f"/interviews/questions/preview?resume_id={student['resume_id']}&technical=0&project=0"
                     "&behavioral=0&internship=0", headers=student["headers"])
    assert bad.status_code == 422


@pytest.mark.parametrize("extra", [
    {"mix": {"technical": 0, "project": 0, "behavioral": 0, "internship": 0}},
    {"mix": {"technical": 11}},
    {"mode": "exam"},
    {"difficulty": "extreme"},
    {"time_limit_seconds": 5},
])
def test_create_validation(client, student, extra):
    assert start(client, student, **extra).status_code == 422


def test_inactive_internship_and_missing_extraction(client, student, create_user, seeded):
    internship = seeded.get(Internship, student["internship_id"])
    internship.deadline = datetime.now(timezone.utc) - timedelta(days=1)
    seeded.commit()
    assert start(client, student).status_code == 404

    user = create_user()
    resume = Resume(user_id=user["user_id"], filename="x.pdf", file_path="x/0.pdf", file_type="pdf", status="uploaded")
    seeded.add(resume)
    seeded.commit()
    response = client.post("/interviews/sessions", headers=user["headers"], json={"resume_id": resume.resume_id})
    assert response.status_code == 422


def test_general_session_without_internship(client, student):
    session = client.post("/interviews/sessions", headers=student["headers"],
                          json={"resume_id": student["resume_id"]}).json()
    assert session["internship_id"] is None
    assert "internship" not in {q["category"] for q in session["questions"]}


# ------------------------------------------------------------------
# Answers, retries, completion, progress
# ------------------------------------------------------------------

def test_answer_retry_complete_and_progress(client, student):
    h = student["headers"]
    session = start(client, student, mix={"technical": 2, "project": 1, "behavioral": 1, "internship": 0}).json()
    sid = session["session_id"]
    technical = next(q for q in session["questions"] if q["category"] == "technical")

    first = answer(client, student, sid, technical["question_id"], "I am not sure about this one.")
    assert first.status_code == 201
    assert first.json()["attempt"] == 1 and first.json()["feedback_source"] == "rubric"
    good_points = " ".join(client.get(f"/interviews/sessions/{sid}", headers=h).json()["questions"][0]["key_points"])
    second = answer(client, student, sid, technical["question_id"],
                    f"{good_points}. In my projects I applied this carefully and explained the trade-offs to my team.")
    assert second.json()["attempt"] == 2
    assert second.json()["score"] > first.json()["score"]

    attempts = client.get(f"/interviews/sessions/{sid}/questions/{technical['question_id']}/answers", headers=h).json()
    assert [a["attempt"] for a in attempts] == [1, 2]

    detail = client.get(f"/interviews/sessions/{sid}", headers=h).json()
    assert detail["status"] == "in_progress" and detail["answered_count"] == 1

    completed = client.post(f"/interviews/sessions/{sid}/complete", headers=h).json()
    summary = completed["summary"]
    assert completed["status"] == "completed" and completed["completed_at"]
    assert summary["answered"] == 1 and summary["total"] == 4
    assert completed["score"] == pytest.approx(round(second.json()["score"] / 4, 1), abs=0.1)
    assert "technical" in summary["by_category"]

    assert answer(client, student, sid, technical["question_id"]).status_code == 409
    assert client.post(f"/interviews/sessions/{sid}/complete", headers=h).status_code == 409

    progress = client.get("/interviews/progress", headers=h).json()
    assert progress["sessions_completed"] == 1 and progress["answers_total"] == 2
    assert progress["retry_improvement"]["questions_retried"] == 1
    assert progress["retry_improvement"]["average_change"] > 0
    assert progress["trend"][0]["session_id"] == sid


@pytest.mark.parametrize("text", ["", "   ", "x" * 5001])
def test_answer_validation(client, student, text):
    session = start(client, student).json()
    response = answer(client, student, session["session_id"], session["questions"][0]["question_id"], text)
    assert response.status_code == 422


def test_history_filters_and_delete(client, student, seeded):
    h = student["headers"]
    a = start(client, student).json()
    b = start(client, student, mode="mock").json()
    client.post(f"/interviews/sessions/{a['session_id']}/complete", headers=h)

    assert [s["session_id"] for s in client.get("/interviews/sessions?status=completed", headers=h).json()] == [a["session_id"]]
    assert len(client.get(f"/interviews/sessions?internship_id={student['internship_id']}", headers=h).json()) == 2

    answer(client, student, b["session_id"], b["questions"][0]["question_id"])
    question_ids = [q["question_id"] for q in b["questions"]]
    assert seeded.scalar(select(func.count()).select_from(InterviewAnswer)
                         .where(InterviewAnswer.question_id.in_(question_ids))) == 1

    assert client.delete(f"/interviews/sessions/{b['session_id']}", headers=h).status_code == 204
    assert client.get(f"/interviews/sessions/{b['session_id']}", headers=h).status_code == 404
    seeded.expire_all()
    assert seeded.scalar(select(func.count()).select_from(InterviewQuestion)
                         .where(InterviewQuestion.session_id == b["session_id"])) == 0
    assert seeded.scalar(select(func.count()).select_from(InterviewAnswer)
                         .where(InterviewAnswer.question_id.in_(question_ids))) == 0
    # The other session is untouched.
    assert client.get(f"/interviews/sessions/{a['session_id']}", headers=h).status_code == 200


def test_resume_deletion_keeps_history_and_user_deletion_cascades(client, student, seeded):
    h = student["headers"]
    session = start(client, student).json()
    assert client.delete(f"/resumes/{student['resume_id']}", headers=h).status_code == 204
    kept = client.get(f"/interviews/sessions/{session['session_id']}", headers=h).json()
    assert kept["resume_id"] is None
    assert answer(client, student, session["session_id"], session["questions"][0]["question_id"]).status_code == 201

    seeded.delete(seeded.get(User, student["user_id"]))
    seeded.commit()
    for model in (InterviewSession, InterviewQuestion, InterviewAnswer):
        assert seeded.scalar(select(func.count()).select_from(model)) == 0


# ------------------------------------------------------------------
# Optional LLM: consent, configuration, grounding, privacy
# ------------------------------------------------------------------

def test_llm_requires_consent_and_configuration(client, student):
    assert start(client, student, use_llm=True).status_code == 422
    assert start(client, student, use_llm=True, llm_consent=True).status_code == 503
    session = start(client, student).json()
    qid = session["questions"][0]["question_id"]
    assert answer(client, student, session["session_id"], qid, use_llm_feedback=True).status_code == 422
    assert answer(client, student, session["session_id"], qid, use_llm_feedback=True,
                  llm_consent=True).status_code == 503


def test_llm_tailored_questions_are_validated(client, student, fake_llm):
    provider = fake_llm({"questions": [
        {"category": "project", "text": "How did you design the REST endpoints in your Software Intern role?",
         "fact_ids": ["exp-1"]},
        {"category": "project", "text": "How did you lead the Kubernetes migration at Google?", "fact_ids": ["exp-1"]},
        {"category": "internship", "text": "What did you do at your previous company?", "fact_ids": ["exp-9"]},
    ]})
    session = start(client, student, use_llm=True, llm_consent=True).json()
    texts = [q["text"] for q in session["questions"]]
    assert "How did you design the REST endpoints in your Software Intern role?" in texts
    assert not any("Kubernetes" in t or "previous company" in t for t in texts)
    assert session["generation_method"] == "llm"
    assert session["summary"]["generation"]["llm"] == {"used": True, "accepted": 1, "rejected": 2}
    assert "Asha Rao" not in str(provider.calls[0]["payload"])


def test_llm_feedback_is_scrubbed_and_falls_back(client, student, fake_llm):
    session = start(client, student).json()
    sid, qid = session["session_id"], session["questions"][0]["question_id"]
    provider = fake_llm({"feedback": "Good structure; add a concrete example.", "tips": ["Mention trade-offs."]})
    text = "I am Asha Rao, reach me at asha@example.com or +91 90000 00002. An inner join matches both tables."
    result = answer(client, student, sid, qid, text, use_llm_feedback=True, llm_consent=True).json()
    assert result["feedback_source"] == "llm" and result["feedback"].startswith("Good structure")
    assert "Rubric score" in result["feedback"]
    sent = str(provider.calls[0]["payload"])
    for secret in ("Asha Rao", "asha@example.com", "90000 00002"):
        assert secret not in sent

    fake_llm(error=LLMError("The language-model provider could not be reached."))
    fallback = answer(client, student, sid, qid, "An inner join matches rows in both tables.",
                      use_llm_feedback=True, llm_consent=True).json()
    assert fallback["feedback_source"] == "rubric"
    assert fallback["evaluation"]["llm_warnings"][0]["code"] == "llm_unavailable"


def test_bank_version_endpoint(client, student):
    info = client.get("/interviews/question-bank/version", headers=student["headers"]).json()
    assert info["skills_covered"] == 69 and info["technical_questions"] == 207


def test_interviews_do_not_change_earlier_modules(client, student, seeded):
    h, rid = student["headers"], student["resume_id"]
    run = client.post(f"/matches/resumes/{rid}?k=5", headers=h).json()
    gaps = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={}).json()
    doc = client.post("/documents/resume", headers=h,
                      json={"resume_id": rid, "internship_id": student["internship_id"]}).json()

    session = start(client, student).json()
    for q in session["questions"][:3]:
        answer(client, student, session["session_id"], q["question_id"])
    client.post(f"/interviews/sessions/{session['session_id']}/complete", headers=h)

    rows = seeded.scalars(select(MatchResult).where(MatchResult.run_id == run["run_id"])).all()
    assert sorted(r.score for r in rows) == sorted(r["score"] for r in run["results"])
    after = client.get(f"/skill-gaps?resume_id={rid}", headers=h).json()
    assert [(r["skill"], r["status"]) for r in after] == [(r["skill"], r["status"]) for r in gaps["recommendations"]]
    assert seeded.get(GeneratedDocument, doc["document_id"]).current_version == 1


# ------------------------------------------------------------------
# Phase 6 review fixes: privacy, warnings, defaults, notices, labelling
# ------------------------------------------------------------------

def resume_with_address_docx():
    document = Document()
    for line in [
        "Asha Rao", "asha@example.com | +91 90000 00002", "12 MG Road, Indiranagar, Bengaluru 560001",
        "SUMMARY", "Backend developer who designs REST APIs.",
        "SKILLS", "Python, FastAPI, PostgreSQL, Docker, Git, SQL",
        "EDUCATION", "B.Tech Information Technology, Example Institute of Technology, 2026",
        "PROJECTS", "Inventory API", "Deployed a Docker service used by 20 users.",
    ]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def addressed_student(client, create_user, seeded):
    user = create_user()
    upload = client.post("/resumes/upload", headers=user["headers"],
                         files={"file": ("cv.docx", resume_with_address_docx(), DOCX)})
    assert upload.status_code == 201
    user["resume_id"] = upload.json()["resume_id"]
    user["internship_id"] = seeded.scalar(select(Internship.internship_id).order_by(Internship.internship_id))
    return user


def test_ai_feedback_never_receives_personal_data(client, addressed_student, fake_llm):
    session = start(client, addressed_student).json()
    sid, qid = session["session_id"], session["questions"][0]["question_id"]
    provider = fake_llm({"feedback": "Clear explanation; add an example.", "tips": []})
    text = ("Hi, I am Asha. Rao here, from 12 MG Road, Indiranagar, Bengaluru 560001, Flat No. 4B, PIN 560 001. "
            "Mail asha@example.com or call +91 90000 00002. An inner join returns only rows that match in both "
            "tables, while a left join returns all rows from the left table.")
    result = answer(client, addressed_student, sid, qid, text, use_llm_feedback=True, llm_consent=True).json()
    assert result["feedback_source"] == "llm" and len(provider.calls) == 1
    sent = str(provider.calls[0]["payload"]).lower()
    for secret in ("asha", "rao", "12 mg road", "indiranagar", "bengaluru", "560001", "560 001", "flat no",
                   "asha@example.com", "90000 00002"):
        assert secret not in sent, secret
    assert "inner join returns only rows that match" in sent
    stored = client.get(f"/interviews/sessions/{sid}/questions/{qid}/answers",
                        headers=addressed_student["headers"]).json()[-1]
    assert stored["answer_text"] == text           # the student's own copy is never altered


def test_privacy_guard_blocks_sending_when_scrubbing_fails(client, student, fake_llm, monkeypatch):
    from backend.services import interview_service, llm_privacy

    # Simulate both scrubbing steps failing. First name only: the older full-name
    # check alone would not have caught this.
    monkeypatch.setattr(interview_service, "scrub_personal", lambda text, details: text)
    monkeypatch.setattr(llm_privacy, "scrub_llm_payload", lambda payload, details: payload)
    session = start(client, student).json()
    provider = fake_llm({"feedback": "Should never be used.", "tips": []})
    result = answer(client, student, session["session_id"], session["questions"][0]["question_id"],
                    "I am Asha and an inner join returns only rows that match in both tables.",
                    use_llm_feedback=True, llm_consent=True).json()
    assert provider.calls == [] and result["feedback_source"] == "rubric"
    warning = result["evaluation"]["llm_warnings"][0]
    assert warning["code"] == "privacy_guard" and "name" in warning["detail"]
    assert "Asha" not in warning["detail"]           # warnings name the kind of data, never the value


def test_ai_feedback_warns_when_resume_was_deleted(client, student, fake_llm):
    session = start(client, student).json()
    assert client.delete(f"/resumes/{student['resume_id']}", headers=student["headers"]).status_code == 204
    provider = fake_llm({"feedback": "Should never be used.", "tips": []})
    result = answer(client, student, session["session_id"], session["questions"][0]["question_id"],
                    "An inner join returns only the rows that match in both tables.",
                    use_llm_feedback=True, llm_consent=True)
    assert result.status_code == 201
    body = result.json()
    assert provider.calls == [] and body["feedback_source"] == "rubric"
    assert body["evaluation"]["llm_warnings"][0]["code"] == "resume_unavailable"


def test_groq_is_off_unless_requested_with_consent(client, student, fake_llm):
    provider = fake_llm({"questions": [], "feedback": "x", "tips": []})
    session = start(client, student).json()
    result = answer(client, student, session["session_id"], session["questions"][0]["question_id"],
                    "An inner join returns only the rows that match in both tables.").json()
    assert provider.calls == [] and result["feedback_source"] == "rubric"
    assert session["generation_method"] == "deterministic"
    assert answer(client, student, session["session_id"], session["questions"][0]["question_id"],
                  use_llm_feedback=True).status_code == 422
    assert start(client, student, use_llm=True).status_code == 422
    assert provider.calls == []


def test_notices_explain_fewer_questions(client, student):
    h = student["headers"]
    full = start(client, student, mix={"technical": 2, "project": 5, "behavioral": 1, "internship": 0}).json()
    project = [n for n in full["notices"] if n["category"] == "project"]
    assert project and project[0]["code"] == "fewer_questions"
    assert project[0]["requested"] == 5 and project[0]["generated"] == 2
    assert full["total_questions"] == 2 + 2 + 1 and full["summary"]["requested_questions"] == 8

    general = client.post("/interviews/sessions", headers=h, json={
        "resume_id": student["resume_id"], "mix": {"technical": 1, "project": 1, "behavioral": 1, "internship": 2}})
    codes = {n["code"] for n in general.json()["notices"]}
    assert "internship_questions_replaced" in codes

    exact = start(client, student, mix={"technical": 2, "project": 1, "behavioral": 1, "internship": 1}).json()
    assert exact["notices"] == []
    assert client.get(f"/interviews/sessions/{full['session_id']}", headers=h).json()["notices"] == full["notices"]


def test_technical_answers_are_labelled_as_coverage_through_the_api(client, student):
    session = start(client, student).json()
    technical = next(q for q in session["questions"] if q["category"] == "technical")
    result = answer(client, student, session["session_id"], technical["question_id"],
                    "I do not know the answer to this question at all, sorry, I never learned it.").json()
    assert result["evaluation"]["score_basis"] == "key_point_coverage"
    assert result["evaluation"]["correctness_verified"] is False
    assert result["feedback"].startswith("Key-point coverage") and result["score"] <= 25
    info = client.get("/interviews/question-bank/version", headers=student["headers"]).json()
    assert info["questions_with_misconception_checks"] >= 140
