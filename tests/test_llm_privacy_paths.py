"""Every request to the AI provider is scrubbed: no path can leak personal data.

The four paths that can reach Groq (all through ``document_common.call_llm``):
  1. Phase 5 tailored resume         POST /documents/resume        (use_llm)
  2. Phase 5 cover letter            POST /documents/cover-letter  (use_llm)
  3. Phase 6 AI-tailored questions   POST /interviews/sessions     (use_llm)
  4. Phase 6 answer feedback         POST .../answers              (use_llm_feedback)

The test resume deliberately hides personal details inside its summary,
experience and project text (not only in the contact header). The provider
is always the mocked FakeLLM; nothing leaves the machine.
"""

import io
import json

import pytest
from docx import Document
from sqlalchemy import select

from backend.models import Internship
from backend.services.document_common import FactCheckLog, validate_llm_statement
from backend.services.fact_base import CandidateFacts, Fact
from backend.services.internship_seed import load_dataset, seed_internships, validate_records

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUBSET = load_dataset()[:20]

SECRETS = ("asha", "rao", "12 mg road", "indiranagar", "560001", "560 001", "flat no", "asha@example.com",
           "asha.rao@example.com", "90000 00002", "98765 43210", "linkedin.com/in/asharao")


def leaky_resume_docx():
    document = Document()
    for line in [
        "Asha Rao", "asha@example.com | +91 90000 00002 | linkedin.com/in/asharao",
        "12 MG Road, Indiranagar, Bengaluru 560001",
        "SUMMARY",
        "Asha is a backend developer who designs REST APIs. Contact Asha Rao at asha.rao@example.com.",
        "SKILLS", "Python, FastAPI, PostgreSQL, Docker, Git, SQL",
        "EDUCATION", "B.Tech Information Technology, Example Institute of Technology, 2026",
        "EXPERIENCE", "Software Intern, Example Systems, 2025",
        "Rao built 12 REST endpoints with FastAPI and PostgreSQL from the office at Flat No. 4B, 12 MG Road.",
        "PROJECTS", "Inventory API",
        "Deployed a Docker service used by 20 users; demo requests to +91 98765 43210, PIN 560 001.",
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
    upload = client.post("/resumes/upload", headers=user["headers"],
                         files={"file": ("cv.docx", leaky_resume_docx(), DOCX)})
    assert upload.status_code == 201, upload.text
    user["resume_id"] = upload.json()["resume_id"]
    user["internship_id"] = seeded.scalar(select(Internship.internship_id).order_by(Internship.internship_id))
    return user


def candidate_part(payload):
    """Everything in the request except the public internship record."""
    return json.dumps({k: v for k, v in payload.items() if k != "internship"}, ensure_ascii=False).lower()


def assert_clean(provider, must_keep):
    assert provider.calls, "the mocked provider was not called"
    for call in provider.calls:
        sent = candidate_part(call["payload"])
        for secret in SECRETS:
            assert secret not in sent, (secret, sent[:400])
        assert must_keep in sent                       # the useful content still goes through


def test_path_1_tailored_resume(client, student, fake_llm):
    provider = fake_llm({"summary": None, "bullets": []})
    response = client.post("/documents/resume", headers=student["headers"], json={
        "resume_id": student["resume_id"], "internship_id": student["internship_id"],
        "use_llm": True, "llm_consent": True})
    assert response.status_code == 201, response.text
    assert_clean(provider, "rest")


def test_path_2_cover_letter(client, student, fake_llm):
    provider = fake_llm({"paragraphs": []})
    response = client.post("/documents/cover-letter", headers=student["headers"], json={
        "resume_id": student["resume_id"], "internship_id": student["internship_id"],
        "use_llm": True, "llm_consent": True})
    assert response.status_code == 201, response.text
    assert_clean(provider, "rest")


def test_path_3_ai_tailored_interview_questions(client, student, fake_llm):
    provider = fake_llm({"questions": [
        {"category": "project", "text": "How did you design the REST endpoints in your Software Intern role?",
         "fact_ids": ["exp-1"]},
        {"category": "project", "text": "What did you build at [removed] for the team there?", "fact_ids": ["exp-1"]},
    ]})
    response = client.post("/interviews/sessions", headers=student["headers"], json={
        "resume_id": student["resume_id"], "internship_id": student["internship_id"],
        "use_llm": True, "llm_consent": True})
    assert response.status_code == 201, response.text
    assert_clean(provider, "rest")
    session = response.json()
    texts = [q["text"] for q in session["questions"]]
    assert not any("[removed]" in t for t in texts)          # placeholders are never shown as questions
    rejected = session["summary"]["generation"]["rejected_statements"]
    assert any(p["code"] == "privacy_placeholder" for r in rejected for p in r["problems"])


def test_path_4_answer_feedback(client, student, fake_llm):
    session = client.post("/interviews/sessions", headers=student["headers"], json={
        "resume_id": student["resume_id"], "internship_id": student["internship_id"]}).json()
    provider = fake_llm({"feedback": "Clear answer.", "tips": []})
    qid = session["questions"][0]["question_id"]
    text = ("I am Asha, surname Rao, living at Flat No. 4B, 12 MG Road, Indiranagar 560001. Mail "
            "asha.rao@example.com or call +91 98765 43210. An inner join returns only rows that match in both "
            "tables, while a REST API exposes resources.")
    response = client.post(f"/interviews/sessions/{session['session_id']}/questions/{qid}/answers",
                           headers=student["headers"],
                           json={"answer_text": text, "use_llm_feedback": True, "llm_consent": True})
    assert response.status_code == 201 and response.json()["feedback_source"] == "llm"
    assert_clean(provider, "inner join returns only rows")


def test_ai_is_never_called_without_opt_in_on_any_path(client, student, fake_llm):
    provider = fake_llm({})
    h, body = student["headers"], {"resume_id": student["resume_id"], "internship_id": student["internship_id"]}
    assert client.post("/documents/resume", headers=h, json=body).status_code == 201
    assert client.post("/documents/cover-letter", headers=h, json=body).status_code == 201
    session = client.post("/interviews/sessions", headers=h, json=body).json()
    qid = session["questions"][0]["question_id"]
    assert client.post(f"/interviews/sessions/{session['session_id']}/questions/{qid}/answers", headers=h,
                       json={"answer_text": "An inner join returns rows that match in both tables."}).status_code == 201
    for path, extra in (("/documents/resume", {"use_llm": True}), ("/documents/cover-letter", {"use_llm": True}),
                        ("/interviews/sessions", {"use_llm": True})):
        assert client.post(path, headers=h, json={**body, **extra}).status_code == 422     # no consent
    assert provider.calls == []


def test_guard_blocks_documents_too_when_scrubbing_is_bypassed(client, student, fake_llm, monkeypatch):
    from backend.services import llm_privacy

    monkeypatch.setattr(llm_privacy, "scrub_llm_payload", lambda payload, details: payload)
    provider = fake_llm({"summary": None, "bullets": []})
    doc = client.post("/documents/resume", headers=student["headers"], json={
        "resume_id": student["resume_id"], "internship_id": student["internship_id"],
        "use_llm": True, "llm_consent": True}).json()
    assert provider.calls == [] and doc["generation_method"] == "deterministic"
    warning = next(w for w in doc["fact_check"]["warnings"] if w["code"] == "privacy_guard")
    assert "asha" not in json.dumps(warning).lower() and "560001" not in json.dumps(warning)


def test_stored_documents_keep_the_students_own_details(client, student, fake_llm):
    fake_llm({"summary": None, "bullets": []})
    doc = client.post("/documents/resume", headers=student["headers"], json={
        "resume_id": student["resume_id"], "internship_id": student["internship_id"],
        "use_llm": True, "llm_consent": True}).json()
    assert doc["content"].startswith("Asha Rao")             # header is filled locally, never by the AI


def test_statements_repeating_removed_details_are_rejected():
    candidate = CandidateFacts(1, {"name": "Asha Rao"}, [Fact("sum-1", "summary", "Backend developer.")], ["Python"])
    log = FactCheckLog()
    assert validate_llm_statement(log, "summary", "Backend developer based in [removed].", ["sum-1"],
                                  candidate, []) is None
    assert log.rejected[0]["problems"][0]["code"] == "privacy_placeholder"
