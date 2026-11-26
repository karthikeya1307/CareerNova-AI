"""Phase 5: /documents API, versions, downloads, consent and ownership."""

import io
from datetime import datetime, timedelta, timezone

import pytest
from docx import Document
from sqlalchemy import func, select

from backend.models import (
    GeneratedDocument, GeneratedDocumentVersion, Internship, MatchResult, Resume, User,
)
from backend.services.fact_check import skill_mentions
from backend.services.internship_seed import load_dataset, seed_internships, validate_records
from backend.services.resume_parser import parse_resume_file

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUBSET = load_dataset()[:20]


def resume_docx(name="Asha Rao", email="asha@example.com"):
    document = Document()
    for line in [
        name, f"{email} | +91 90000 00002",
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
    upload = client.post("/resumes/upload", headers=user["headers"],
                         files={"file": ("cv.docx", resume_docx(), DOCX)})
    assert upload.status_code == 201, upload.text
    user["resume_id"] = upload.json()["resume_id"]
    user["internship_id"] = seeded.scalar(select(Internship.internship_id).order_by(Internship.internship_id))
    return user


def create(client, user, kind="resume", **extra):
    body = {"resume_id": user["resume_id"], "internship_id": user["internship_id"], **extra}
    return client.post(f"/documents/{'resume' if kind == 'resume' else 'cover-letter'}",
                       headers=user["headers"], json=body)


# ------------------------------------------------------------------
# Authentication and ownership
# ------------------------------------------------------------------

@pytest.mark.parametrize("method, path", [
    ("GET", "/documents/llm-status"),
    ("GET", "/documents/resumes/1/internships/1/ats-report"),
    ("POST", "/documents/resume"), ("POST", "/documents/cover-letter"),
    ("GET", "/documents"), ("GET", "/documents/1"), ("PATCH", "/documents/1"),
    ("GET", "/documents/1/versions"), ("POST", "/documents/1/versions/1/restore"),
    ("GET", "/documents/1/download"), ("DELETE", "/documents/1"),
])
def test_login_required(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_other_users_cannot_access(client, student, create_user):
    doc_id = create(client, student).json()["document_id"]
    other = create_user()
    h = other["headers"]
    rid, iid = student["resume_id"], student["internship_id"]

    assert client.get(f"/documents/resumes/{rid}/internships/{iid}/ats-report", headers=h).status_code == 404
    assert client.post("/documents/resume", headers=h, json={"resume_id": rid, "internship_id": iid}).status_code == 404
    assert client.post("/documents/cover-letter", headers=h, json={"resume_id": rid, "internship_id": iid}).status_code == 404
    for method, path in [("GET", f"/documents/{doc_id}"), ("GET", f"/documents/{doc_id}/versions"),
                         ("POST", f"/documents/{doc_id}/versions/1/restore"),
                         ("GET", f"/documents/{doc_id}/download"), ("DELETE", f"/documents/{doc_id}")]:
        assert client.request(method, path, headers=h).status_code == 404
    patch = client.patch(f"/documents/{doc_id}", headers=h, json={"content": {"type": "resume", "sections": []}})
    assert patch.status_code == 404
    assert client.get("/documents", headers=h).json() == []


# ------------------------------------------------------------------
# Creation (deterministic default)
# ------------------------------------------------------------------

def test_llm_status_disabled_by_default(client, student):
    assert client.get("/documents/llm-status", headers=student["headers"]).json() == {
        "available": False, "provider": None, "model": None, "disclosure": None}


def test_create_tailored_resume(client, student, seeded):
    response = create(client, student)
    assert response.status_code == 201
    doc = response.json()

    assert doc["document_type"] == "resume" and doc["generation_method"] == "deterministic"
    assert doc["current_version"] == 1 and doc["llm_provider"] is None
    assert doc["content"].startswith("Asha Rao")            # header filled locally
    assert doc["ats_report"]["required_coverage"]["total"] >= 1
    assert doc["fact_check"]["llm"]["used"] is False

    internship = seeded.get(Internship, student["internship_id"])
    candidate_skills = {"Python", "FastAPI", "PostgreSQL", "Docker", "Git", "SQL", "REST API"}
    assert skill_mentions(doc["content"]) <= candidate_skills
    missing = set(doc["ats_report"]["missing_keywords"])
    assert not (missing & skill_mentions(doc["content"]))   # missing keywords never inserted
    assert internship.title in doc["title"]


def test_create_cover_letter(client, student):
    response = create(client, student, kind="cover", tone="concise")
    assert response.status_code == 201
    doc = response.json()
    assert doc["document_type"] == "cover_letter"
    assert doc["content"].rstrip().endswith("Asha Rao")
    assert "motivation" not in {p["key"] for p in doc["content_json"]["paragraphs"]}


def test_cover_letter_rejects_unknown_emphasis(client, student):
    assert create(client, student, kind="cover", emphasize_skills=["Rust"]).status_code == 422


@pytest.mark.parametrize("body", [
    {"options": {"max_skills": 1}},
    {"options": {"max_bullets": 9}},
    {"tone": "angry"},
])
def test_validation(client, student, body):
    kind = "cover" if "tone" in body else "resume"
    assert create(client, student, kind=kind, **body).status_code == 422


def test_inactive_or_expired_internship_is_404(client, student, seeded):
    internship = seeded.get(Internship, student["internship_id"])
    internship.deadline = datetime.now(timezone.utc) - timedelta(days=1)
    seeded.commit()
    assert create(client, student).status_code == 404
    path = f"/documents/resumes/{student['resume_id']}/internships/{student['internship_id']}/ats-report"
    assert client.get(path, headers=student["headers"]).status_code == 404


def test_resume_without_extraction_is_422(client, create_user, seeded):
    user = create_user()
    resume = Resume(user_id=user["user_id"], filename="x.pdf", file_path="x/0.pdf",
                    file_type="pdf", status="uploaded")
    seeded.add(resume)
    seeded.commit()
    iid = seeded.scalar(select(Internship.internship_id).limit(1))
    response = client.post("/documents/resume", headers=user["headers"],
                           json={"resume_id": resume.resume_id, "internship_id": iid})
    assert response.status_code == 422


# ------------------------------------------------------------------
# Consent and LLM
# ------------------------------------------------------------------

def test_llm_requires_consent_then_configuration(client, student):
    assert create(client, student, use_llm=True).status_code == 422                     # no consent
    assert create(client, student, use_llm=True, llm_consent=True).status_code == 503   # not configured


def test_llm_generation_with_mocked_provider(client, student, fake_llm):
    provider = fake_llm({"summary": {"text": "Experienced at Google with Kubernetes.", "fact_ids": ["sum-1"]},
                         "bullets": []})
    status = client.get("/documents/llm-status", headers=student["headers"]).json()
    assert status["available"] is True and "never sent" in status["disclosure"]

    doc = create(client, student, use_llm=True, llm_consent=True).json()
    assert doc["generation_method"] == "llm" and doc["llm_provider"] == "fake"
    assert "Google" not in doc["content"] and "Kubernetes" not in doc["content"]
    assert doc["fact_check"]["llm"]["rejected"] == 1

    payload = str(provider.calls[0]["payload"])
    for secret in ("Asha Rao", "asha@example.com", "90000 00002"):
        assert secret not in payload


def test_llm_not_called_without_opt_in(client, student, fake_llm):
    provider = fake_llm({})
    doc = create(client, student).json()
    assert provider.calls == [] and doc["generation_method"] == "deterministic"


# ------------------------------------------------------------------
# Editing, versions, restore
# ------------------------------------------------------------------

def test_edit_versions_and_restore(client, student):
    h = student["headers"]
    doc = create(client, student).json()
    original = doc["content_json"]

    edited = {**original, "sections": [*original["sections"],
              {"key": "extra", "title": "Highlights",
               "items": [{"heading": None, "lines": ["Led a Kubernetes migration at Google."], "fact_ids": []}]}]}
    response = client.patch(f"/documents/{doc['document_id']}", headers=h,
                            json={"title": "My tailored resume", "content": edited})
    assert response.status_code == 200
    updated = response.json()
    assert updated["current_version"] == 2 and updated["title"] == "My tailored resume"
    assert "Led a Kubernetes migration at Google." in updated["content"]       # saved as written
    codes = {w["code"] for w in updated["fact_check"]["warnings"]}
    assert {"unsupported_skill", "unsupported_term"} <= codes                   # but flagged

    versions = client.get(f"/documents/{doc['document_id']}/versions", headers=h).json()
    assert [(v["version"], v["source"]) for v in versions] == [(1, "generated"), (2, "edited")]
    assert versions[1]["warning_count"] >= 2

    restored = client.post(f"/documents/{doc['document_id']}/versions/1/restore", headers=h).json()
    assert restored["current_version"] == 3 and restored["content_json"] == original
    assert client.post(f"/documents/{doc['document_id']}/versions/99/restore", headers=h).status_code == 404


@pytest.mark.parametrize("content", [
    {"type": "cover_letter", "paragraphs": [{"key": "a", "text": "Hi"}]},     # wrong type for a resume
    {"type": "resume", "sections": [{"key": "s", "title": "", "items": []}]},  # empty title
    {"type": "resume", "sections": [{"key": "s", "title": "T",
                                     "items": [{"lines": ["x" * 501]}]}]},    # line too long
    {"type": "memo", "sections": []},
])
def test_invalid_edits_rejected(client, student, content):
    doc_id = create(client, student).json()["document_id"]
    response = client.patch(f"/documents/{doc_id}", headers=student["headers"], json={"content": content})
    assert response.status_code == 422


# ------------------------------------------------------------------
# List, download, delete
# ------------------------------------------------------------------

def test_list_filters(client, student):
    h = student["headers"]
    create(client, student)
    create(client, student, kind="cover")
    assert len(client.get("/documents", headers=h).json()) == 2
    assert [d["document_type"] for d in client.get("/documents?type=cover_letter", headers=h).json()] == ["cover_letter"]
    assert len(client.get(f"/documents?resume_id={student['resume_id']}", headers=h).json()) == 2
    assert client.get("/documents?type=memo", headers=h).status_code == 422


def test_downloads(client, student):
    h = student["headers"]
    doc_id = create(client, student).json()["document_id"]

    docx = client.get(f"/documents/{doc_id}/download?format=docx", headers=h)
    assert docx.status_code == 200 and docx.headers["content-type"] == DOCX
    assert docx.headers["content-disposition"].startswith('attachment; filename="Resume_')
    assert docx.headers["x-content-type-options"] == "nosniff"
    parsed = parse_resume_file(docx.content, "x.docx")["extracted_data"]
    assert {"Python", "FastAPI", "Docker"} <= set(parsed["skills"])

    txt = client.get(f"/documents/{doc_id}/download?format=txt", headers=h)
    assert txt.headers["content-type"].startswith("text/plain")
    assert txt.text.startswith("Asha Rao") and "SKILLS" in txt.text

    assert client.get(f"/documents/{doc_id}/download?format=pdf", headers=h).status_code == 422


def test_delete_removes_document_and_versions(client, student, seeded):
    h = student["headers"]
    doc_id = create(client, student).json()["document_id"]
    assert client.delete(f"/documents/{doc_id}", headers=h).status_code == 204
    assert client.get(f"/documents/{doc_id}", headers=h).status_code == 404
    count = seeded.scalar(select(func.count()).select_from(GeneratedDocumentVersion)
                          .where(GeneratedDocumentVersion.document_id == doc_id))
    assert count == 0


def test_resume_deletion_keeps_document_but_edits_warn(client, student, seeded):
    h = student["headers"]
    doc = create(client, student).json()
    assert client.delete(f"/resumes/{student['resume_id']}", headers=h).status_code == 204

    kept = client.get(f"/documents/{doc['document_id']}", headers=h).json()
    assert kept["resume_id"] is None
    edit = client.patch(f"/documents/{doc['document_id']}", headers=h, json={"content": doc["content_json"]}).json()
    assert edit["fact_check"]["warnings"][0]["code"] == "source_unavailable"


def test_user_deletion_cascades(client, student, seeded):
    create(client, student)
    seeded.delete(seeded.get(User, student["user_id"]))
    seeded.commit()
    assert seeded.scalar(select(func.count()).select_from(GeneratedDocument)) == 0
    assert seeded.scalar(select(func.count()).select_from(GeneratedDocumentVersion)) == 0


def test_documents_do_not_change_matching_or_skill_gaps(client, student, seeded):
    h, rid = student["headers"], student["resume_id"]
    run = client.post(f"/matches/resumes/{rid}?k=5", headers=h).json()
    gaps = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={}).json()

    create(client, student)
    create(client, student, kind="cover")

    rows = seeded.scalars(select(MatchResult).where(MatchResult.run_id == run["run_id"])).all()
    assert sorted(r.score for r in rows) == sorted(r["score"] for r in run["results"])
    after = client.get(f"/skill-gaps?resume_id={rid}", headers=h).json()
    assert [(r["skill"], r["priority_score"], r["status"]) for r in after] == [
        (r["skill"], r["priority_score"], r["status"]) for r in gaps["recommendations"]]


# ------------------------------------------------------------------
# Assignment 1: cover letter for the selected internship, end to end (test database only)
# ------------------------------------------------------------------

def test_cover_letter_end_to_end_uses_the_selected_internship_and_never_invents_skills(client, student, seeded):
    first, second = seeded.scalars(select(Internship).order_by(Internship.internship_id).limit(2)).all()
    first.description = "Build Python services with FastAPI and PostgreSQL for the payments team. Join stand-ups."
    first.min_education = "B.Tech or B.E. in Computer Science or IT"
    second.description = "Operate Kubernetes clusters and Terraform pipelines for the platform team."
    second.min_education = "MBA"
    seeded.commit()
    resume_skills = {"Python", "FastAPI", "PostgreSQL", "Docker", "Git", "SQL", "REST API"}

    # What the internship picker shows: responsibilities, required skills and education requirement.
    details = client.get(f"/internships/{first.internship_id}", headers=student["headers"]).json()
    assert details["description"].startswith("Build Python services")
    assert details["min_education"].startswith("B.Tech") and details["required_skills"]

    letters = {}
    for internship in (first, second):
        response = client.post("/documents/cover-letter", headers=student["headers"],
                               json={"resume_id": student["resume_id"], "internship_id": internship.internship_id})
        assert response.status_code == 201, response.text
        letters[internship.internship_id] = response.json()["content"]

    one, two = letters[first.internship_id], letters[second.internship_id]
    assert first.company in one and first.title in one and second.company not in one
    assert second.company in two and second.title in two and first.company not in two
    # Responsibilities are quoted from the posting, attributed to it, only when the student has the skills.
    assert "Your posting says the role requires the following: “Build Python services with FastAPI and " \
           "PostgreSQL for the payments team.”" in one
    assert "Kubernetes" not in two and "Terraform" not in two and "Your posting says" not in two
    # The education requirement is mentioned only when the student's degree matches it.
    assert "match the education it asks for (B.Tech or B.E. in Computer Science or IT)" in one
    assert "MBA" not in two
    # No qualification outside the resume: every skill named in either letter is on the resume.
    for letter in (one, two):
        assert skill_mentions(letter) <= resume_skills, skill_mentions(letter) - resume_skills
        assert letter.rstrip().endswith("Asha Rao")
