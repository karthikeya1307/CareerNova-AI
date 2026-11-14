"""Phase 1: resume skills, re-parse, download, delete and backfill."""

import io
from urllib.parse import unquote

import pytest
from docx import Document
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from backend import manage
from backend.models import Resume, ResumeExtraction, ResumeSkill, Skill

DOCX_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def make_docx(skill_line="Python, React.js, A WS, Basic, Antigravity") -> bytes:
    document = Document()
    for line in [
        "Asha Rao",
        "asha@example.com | +91 98765 43210",
        "SKILLS",
        skill_line,
        "SOFT SKILLS",
        "Communication, Teamwork",
        "EDUCATION",
        "B.Tech Computer Science, Example Institute of Technology, 2026",
    ]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def upload(client, headers, content=None, name="resume.docx"):
    response = client.post(
        "/resumes/upload",
        headers=headers,
        files={"file": (name, content or make_docx(), DOCX_TYPE)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def count(db, model, *where):
    query = select(func.count()).select_from(model)
    if where:
        query = query.where(*where)
    return db.scalar(query)


# ------------------------------------------------------------------
# Upload persists normalized skills
# ------------------------------------------------------------------

def test_upload_links_normalized_skills(client, create_user, db_session):
    user = create_user()
    data = upload(client, user["headers"])

    # Existing response fields are unchanged.
    assert "Python" in data["extracted_data"]["skills"]

    names = {s["name"] for s in data["normalized_skills"]}
    assert {"Python", "React", "AWS", "Antigravity",
            "Communication", "Teamwork"} <= names
    assert "Basic" not in names
    assert "React.js" not in names

    by_name = {s["name"]: s for s in data["normalized_skills"]}
    assert by_name["Antigravity"]["category"] == "other"
    assert by_name["Communication"]["category"] == "soft_skill"

    links = count(db_session, ResumeSkill,
                  ResumeSkill.resume_id == data["resume_id"])
    assert links == len(data["normalized_skills"])


def test_skills_endpoint_and_detail(client, create_user):
    user = create_user()
    data = upload(client, user["headers"])

    skills = client.get(
        f"/resumes/{data['resume_id']}/skills", headers=user["headers"]
    )
    assert skills.status_code == 200
    assert {s["name"] for s in skills.json()["skills"]} == {
        s["name"] for s in data["normalized_skills"]
    }

    detail = client.get(
        f"/resumes/{data['resume_id']}", headers=user["headers"]
    ).json()
    assert len(detail["normalized_skills"]) == len(data["normalized_skills"])


def test_shared_skills_are_reused_across_resumes(client, create_user, db_session):
    first = create_user()
    second = create_user()

    upload(client, first["headers"])
    skills_after_first = count(db_session, Skill)

    upload(client, second["headers"])
    assert count(db_session, Skill) == skills_after_first


def test_skill_names_are_unique_ignoring_case(db_session):
    db_session.add(Skill(name="AWS", category="cloud_devops"))
    db_session.commit()

    db_session.add(Skill(name="aws", category="other"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ------------------------------------------------------------------
# Ownership
# ------------------------------------------------------------------

@pytest.mark.parametrize("method, suffix", [
    ("GET", "/skills"),
    ("POST", "/reparse"),
    ("GET", "/download"),
    ("DELETE", ""),
])
def test_other_users_get_404(client, create_user, method, suffix):
    owner = create_user()
    other = create_user()
    resume_id = upload(client, owner["headers"])["resume_id"]

    response = client.request(
        method, f"/resumes/{resume_id}{suffix}", headers=other["headers"]
    )
    assert response.status_code == 404


@pytest.mark.parametrize("method, suffix", [
    ("GET", "/1/skills"), ("POST", "/1/reparse"),
    ("GET", "/1/download"), ("DELETE", "/1"),
])
def test_endpoints_require_authentication(client, method, suffix):
    assert client.request(method, f"/resumes{suffix}").status_code == 401


# ------------------------------------------------------------------
# Re-parse keeps history
# ------------------------------------------------------------------

def test_reparse_adds_extraction_and_keeps_history(client, create_user, db_session):
    user = create_user()
    resume_id = upload(client, user["headers"])["resume_id"]

    response = client.post(
        f"/resumes/{resume_id}/reparse", headers=user["headers"]
    )
    assert response.status_code == 200
    assert {s["name"] for s in response.json()["normalized_skills"]} >= {
        "Python", "React", "AWS"
    }

    assert count(db_session, ResumeExtraction,
                 ResumeExtraction.resume_id == resume_id) == 2


def test_failed_reparse_is_recorded_and_previous_data_kept(
    client, create_user, db_session, isolated_uploads
):
    user = create_user()
    data = upload(client, user["headers"])
    resume_id = data["resume_id"]

    stored = next(isolated_uploads.rglob("*.docx"))
    stored.write_bytes(b"corrupted content")

    response = client.post(
        f"/resumes/{resume_id}/reparse", headers=user["headers"]
    )
    assert response.status_code == 422

    extractions = db_session.scalars(
        select(ResumeExtraction)
        .where(ResumeExtraction.resume_id == resume_id)
        .order_by(ResumeExtraction.extraction_id)
    ).all()
    assert [e.status for e in extractions] == ["completed", "failed"]
    assert extractions[1].error_message

    # Detail still serves the last successful extraction and skills.
    detail = client.get(f"/resumes/{resume_id}", headers=user["headers"])
    assert detail.status_code == 200
    assert detail.json()["extracted_data"] == data["extracted_data"]
    assert len(detail.json()["normalized_skills"]) == len(
        data["normalized_skills"]
    )


def test_reparse_missing_file_returns_404(client, create_user, isolated_uploads):
    user = create_user()
    resume_id = upload(client, user["headers"])["resume_id"]

    next(isolated_uploads.rglob("*.docx")).unlink()

    response = client.post(
        f"/resumes/{resume_id}/reparse", headers=user["headers"]
    )
    assert response.status_code == 404


# ------------------------------------------------------------------
# Download
# ------------------------------------------------------------------

def test_download_returns_original_file(client, create_user):
    user = create_user()
    content = make_docx()
    resume_id = upload(
        client, user["headers"], content=content, name="Asha CV.docx"
    )["resume_id"]

    response = client.get(
        f"/resumes/{resume_id}/download", headers=user["headers"]
    )
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == DOCX_TYPE
    # Names with spaces are sent RFC 5987-encoded: filename*=utf-8''Asha%20CV.docx
    disposition = unquote(response.headers["content-disposition"])
    assert disposition.startswith("attachment;")
    assert "Asha CV.docx" in disposition
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("tampered_path", [
    "../../.env",
    "uploads/resumes/1/../../../.env",
    "C:/Windows/win.ini",
    "uploads/resumes/1/not-a-server-name.docx",
])
def test_download_rejects_tampered_paths(client, create_user, db_session, tampered_path):
    user = create_user()
    resume_id = upload(client, user["headers"])["resume_id"]

    resume = db_session.get(Resume, resume_id)
    resume.file_path = tampered_path
    db_session.commit()

    response = client.get(
        f"/resumes/{resume_id}/download", headers=user["headers"]
    )
    assert response.status_code == 404


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------

def test_delete_removes_resume_links_and_file_but_not_skills(
    client, create_user, db_session, isolated_uploads
):
    owner = create_user()
    other = create_user()

    doomed = upload(client, owner["headers"])["resume_id"]
    kept = upload(client, other["headers"])["resume_id"]

    skills_before = count(db_session, Skill)
    kept_links_before = count(db_session, ResumeSkill,
                              ResumeSkill.resume_id == kept)
    assert len(list(isolated_uploads.rglob("*.docx"))) == 2

    response = client.delete(f"/resumes/{doomed}", headers=owner["headers"])
    assert response.status_code == 204

    db_session.expire_all()
    assert db_session.get(Resume, doomed) is None
    assert count(db_session, ResumeExtraction,
                 ResumeExtraction.resume_id == doomed) == 0
    assert count(db_session, ResumeSkill,
                 ResumeSkill.resume_id == doomed) == 0

    # Shared skills and the other resume are untouched.
    assert count(db_session, Skill) == skills_before
    assert count(db_session, ResumeSkill,
                 ResumeSkill.resume_id == kept) == kept_links_before

    assert len(list(isolated_uploads.rglob("*.docx"))) == 1
    assert client.get(
        f"/resumes/{doomed}", headers=owner["headers"]
    ).status_code == 404


def test_delete_succeeds_when_file_already_missing(
    client, create_user, isolated_uploads
):
    user = create_user()
    resume_id = upload(client, user["headers"])["resume_id"]
    next(isolated_uploads.rglob("*.docx")).unlink()

    response = client.delete(f"/resumes/{resume_id}", headers=user["headers"])
    assert response.status_code == 204


# ------------------------------------------------------------------
# Backfill command
# ------------------------------------------------------------------

def test_backfill_dry_run_writes_nothing(client, create_user, db_session, capsys):
    user = create_user()
    resume_id = upload(client, user["headers"])["resume_id"]

    # Simulate a resume uploaded before Phase 1.
    db_session.execute(delete(ResumeSkill))
    db_session.execute(delete(Skill))
    db_session.commit()

    assert manage.main(["backfill-skills"]) == 0
    output = capsys.readouterr().out

    assert "DRY RUN" in output
    assert f"resume {resume_id}:" in output
    assert "React.js->React" in output
    assert "asha@example.com" not in output  # no personal data printed

    db_session.expire_all()
    assert count(db_session, ResumeSkill) == 0
    assert count(db_session, Skill) == 0


def test_backfill_apply_is_idempotent(client, create_user, db_session, capsys):
    user = create_user()
    resume_id = upload(client, user["headers"])["resume_id"]
    expected = count(db_session, ResumeSkill,
                     ResumeSkill.resume_id == resume_id)

    db_session.execute(delete(ResumeSkill))
    db_session.commit()

    assert manage.main(["backfill-skills", "--apply"]) == 0
    db_session.expire_all()
    first_links = count(db_session, ResumeSkill)
    first_skills = count(db_session, Skill)
    assert first_links == expected

    assert manage.main(["backfill-skills", "--apply"]) == 0
    db_session.expire_all()
    assert count(db_session, ResumeSkill) == first_links
    assert count(db_session, Skill) == first_skills
