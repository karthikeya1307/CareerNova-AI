"""Phase 4: skill-gap APIs, persistence, progress and re-parse detection."""

import io
from datetime import datetime, timedelta, timezone

import pytest
from docx import Document
from sqlalchemy import func, select

from backend.models import (
    Internship, MatchResult, Resume, ResumeExtraction, SkillGapRecommendation,
)
from backend.services.internship_seed import load_dataset, seed_internships, validate_records
from backend.services.resume_skills import sync_resume_skills

SUBSET = load_dataset()[:30]
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def seeded(db_session):
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    return db_session


def add_resume(db, user_id, skills):
    resume = Resume(user_id=user_id, filename="cv.pdf", file_path="uploads/resumes/x/0.pdf",
                    file_type="pdf", status="completed")
    db.add(resume)
    db.flush()
    data = {"skills": skills, "technical_skills": skills, "education": []}
    db.add(ResumeExtraction(resume_id=resume.resume_id, parser_type="pypdf",
                            extracted_data=data, status="completed"))
    sync_resume_skills(db, resume.resume_id, data)
    db.commit()
    return resume.resume_id


@pytest.fixture
def student(create_user, seeded):
    user = create_user()
    user["resume_id"] = add_resume(seeded, user["user_id"], ["Python", "MySQL", "Git"])
    return user


def first_internship(db):
    return db.scalar(select(Internship).order_by(Internship.internship_id).limit(1))


def count(db, *where):
    query = select(func.count()).select_from(SkillGapRecommendation)
    return db.scalar(query.where(*where) if where else query)


# ------------------------------------------------------------------
# Authentication and ownership
# ------------------------------------------------------------------

@pytest.mark.parametrize("method, path", [
    ("GET", "/skill-gaps/resumes/1/internships/1"),
    ("POST", "/skill-gaps/resumes/1"),
    ("GET", "/skill-gaps"),
    ("PATCH", "/skill-gaps/1"),
])
def test_login_required(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_other_users_get_404_everywhere(client, student, create_user, seeded):
    other = create_user()
    rid, iid = student["resume_id"], first_internship(seeded).internship_id
    client.post(f"/matches/resumes/{rid}", headers=student["headers"])
    rec_id = client.post(f"/skill-gaps/resumes/{rid}", headers=student["headers"], json={}
                         ).json()["recommendations"][0]["recommendation_id"]

    h = other["headers"]
    assert client.get(f"/skill-gaps/resumes/{rid}/internships/{iid}", headers=h).status_code == 404
    assert client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={}).status_code == 404
    assert client.get(f"/skill-gaps?resume_id={rid}", headers=h).status_code == 404
    assert client.get("/skill-gaps", headers=h).json() == []
    assert client.patch(f"/skill-gaps/{rec_id}", headers=h, json={"status": "completed"}).status_code == 404


# ------------------------------------------------------------------
# Single internship analysis
# ------------------------------------------------------------------

def test_single_internship_analysis(client, student, seeded):
    internship = first_internship(seeded)
    response = client.get(
        f"/skill-gaps/resumes/{student['resume_id']}/internships/{internship.internship_id}",
        headers=student["headers"],
    )
    assert response.status_code == 200
    data = response.json()

    posting_skills = {l.skill.name for l in internship.skill_links}
    reported = {i["skill"] for i in data["matched"] + data["partial"] + data["missing"]}
    assert reported == posting_skills                        # nothing invented, nothing lost
    assert {i["skill"] for i in data["matched"]} <= {"Python", "MySQL", "Git"}
    for item in data["partial"]:
        assert item["related_skills"] and item["related_skills"][0]["skill"] in {"Python", "MySQL", "Git"}
    assert {p["skill"] for p in data["learning_plans"]} == {i["skill"] for i in data["partial"] + data["missing"]}
    assert sorted(data["learning_order"]) == sorted(p["skill"] for p in data["learning_plans"])
    assert data["algorithm_version"] == "gap-v1" and data["learning_plan_version"]
    assert count(seeded) == 0                                # read-only


def test_partial_match_is_reported(client, create_user, seeded):
    user = create_user()
    rid = add_resume(seeded, user["user_id"], ["MySQL"])
    target = next(i for i in seeded.scalars(select(Internship))
                  if "SQL" in {l.skill.name for l in i.skill_links})
    data = client.get(f"/skill-gaps/resumes/{rid}/internships/{target.internship_id}",
                      headers=user["headers"]).json()
    partial = {i["skill"]: i for i in data["partial"]}
    assert "SQL" in partial and partial["SQL"]["related_skills"][0]["skill"] == "MySQL"


def test_inactive_or_expired_internship_returns_404(client, student, seeded):
    internship = first_internship(seeded)
    path = f"/skill-gaps/resumes/{student['resume_id']}/internships/{internship.internship_id}"

    internship.deadline = datetime.now(timezone.utc) - timedelta(days=1)
    seeded.commit()
    assert client.get(path, headers=student["headers"]).status_code == 404

    internship.deadline, internship.is_active = None, False
    seeded.commit()
    assert client.get(path, headers=student["headers"]).status_code == 404


# ------------------------------------------------------------------
# Generate recommendations
# ------------------------------------------------------------------

def test_generate_requires_a_run_or_selection(client, student):
    response = client.post(f"/skill-gaps/resumes/{student['resume_id']}", headers=student["headers"])
    assert response.status_code == 409


def test_generate_from_latest_run(client, student, seeded):
    rid, h = student["resume_id"], student["headers"]
    run = client.post(f"/matches/resumes/{rid}?k=5", headers=h).json()
    scores_before = {r["internship"]["internship_id"]: r["score"] for r in run["results"]}

    response = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={"top_k": 5})
    assert response.status_code == 201
    data = response.json()

    assert data["source"] == "match_run" and data["run_id"] == run["run_id"]
    assert [i["internship_id"] for i in data["internships"]] == list(scores_before)
    for analysed in data["internships"]:
        assert analysed["relevance"] == pytest.approx(scores_before[analysed["internship_id"]] / 100)

    recs = data["recommendations"]
    assert recs, "expected some gaps"
    priorities = [r["priority_score"] for r in recs]
    assert priorities == sorted(priorities, reverse=True)
    assert all(0 <= p <= 100 for p in priorities)
    have = {"Python", "MySQL", "Git"}
    for rec in recs:
        assert rec["skill"] not in have
        assert rec["status"] == "pending" and rec["is_current"]
        assert set(rec["internship_ids"]) <= set(scores_before)
        assert rec["learning_plan"]["skill"] == rec["skill"]
        assert "http://" not in rec["recommended_action"]
    assert sorted(data["learning_order"]) == sorted(r["skill"] for r in recs)

    # Phase 3 results are untouched.
    rows = seeded.scalars(select(MatchResult).where(MatchResult.resume_id == rid)).all()
    assert {r.internship_id: r.score for r in rows} == scores_before


def test_generate_from_selected_internships(client, student, seeded):
    ids = [i.internship_id for i in seeded.scalars(select(Internship).order_by(Internship.internship_id).limit(3))]
    response = client.post(f"/skill-gaps/resumes/{student['resume_id']}", headers=student["headers"],
                           json={"internship_ids": ids})
    assert response.status_code == 201
    data = response.json()
    assert data["source"] == "selection" and data["run_id"] is None
    assert [i["internship_id"] for i in data["internships"]] == ids
    assert all(0 < i["relevance"] <= 1 for i in data["internships"])


@pytest.mark.parametrize("body", [
    {"internship_ids": [1, 1]},
    {"internship_ids": []},
    {"internship_ids": [1], "run_id": "00000000-0000-0000-0000-000000000000"},
    {"top_k": 0},
])
def test_generate_validation(client, student, body):
    response = client.post(f"/skill-gaps/resumes/{student['resume_id']}", headers=student["headers"], json=body)
    assert response.status_code == 422


def test_generate_rejects_unavailable_internships(client, student, seeded):
    internship = first_internship(seeded)
    internship.is_active = False
    seeded.commit()
    response = client.post(f"/skill-gaps/resumes/{student['resume_id']}", headers=student["headers"],
                           json={"internship_ids": [internship.internship_id, 999999]})
    assert response.status_code == 404


def test_generate_with_foreign_run_id_is_404(client, student, create_user, seeded):
    other = create_user()
    other_rid = add_resume(seeded, other["user_id"], ["Python"])
    other_run = client.post(f"/matches/resumes/{other_rid}", headers=other["headers"]).json()
    response = client.post(f"/skill-gaps/resumes/{student['resume_id']}", headers=student["headers"],
                           json={"run_id": other_run["run_id"]})
    assert response.status_code == 404


def test_resume_without_skills_is_422(client, create_user, seeded):
    user = create_user()
    rid = add_resume(seeded, user["user_id"], [])
    ids = [first_internship(seeded).internship_id]
    response = client.post(f"/skill-gaps/resumes/{rid}", headers=user["headers"], json={"internship_ids": ids})
    assert response.status_code == 422


def test_regenerating_preserves_progress_and_avoids_duplicates(client, student, seeded):
    rid, h = student["resume_id"], student["headers"]
    client.post(f"/matches/resumes/{rid}?k=5", headers=h)
    first = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={}).json()["recommendations"]
    target = first[0]
    client.patch(f"/skill-gaps/{target['recommendation_id']}", headers=h, json={"status": "in_progress"})

    second = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={}).json()["recommendations"]
    again = {r["recommendation_id"]: r for r in second}
    assert again[target["recommendation_id"]]["status"] == "in_progress"
    assert count(seeded, SkillGapRecommendation.resume_id == rid) == len(first)


def test_skills_no_longer_in_analysis_become_not_current(client, student, seeded):
    rid, h = student["resume_id"], student["headers"]
    internships = seeded.scalars(select(Internship).order_by(Internship.internship_id)).all()
    a = next(i for i in internships if {l.skill.name for l in i.skill_links} - {"Python", "MySQL", "Git"})
    first = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={"internship_ids": [a.internship_id]}).json()
    a_skills = {r["skill"] for r in first["recommendations"]}

    b = next(i for i in internships
             if i.internship_id != a.internship_id
             and a_skills - {l.skill.name for l in i.skill_links})
    client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={"internship_ids": [b.internship_id]})

    current = {r["skill"] for r in client.get("/skill-gaps", headers=h).json()}
    everything = {r["skill"]: r for r in client.get("/skill-gaps?current_only=false", headers=h).json()}
    dropped = a_skills - current
    assert dropped
    assert all(everything[s]["is_current"] is False for s in dropped)


# ------------------------------------------------------------------
# List and progress
# ------------------------------------------------------------------

def test_list_filters_and_progress_updates(client, student):
    rid, h = student["resume_id"], student["headers"]
    client.post(f"/matches/resumes/{rid}?k=5", headers=h)
    recs = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={}).json()["recommendations"]
    rec_id = recs[0]["recommendation_id"]

    updated = client.patch(f"/skill-gaps/{rec_id}", headers=h, json={"status": "completed"}).json()
    assert updated["status"] == "completed" and updated["completed_via"] == "user"
    assert updated["completed_at"] and updated["started_at"]

    completed = client.get("/skill-gaps?status=completed", headers=h).json()
    assert [r["recommendation_id"] for r in completed] == [rec_id]
    assert len(client.get(f"/skill-gaps?resume_id={rid}&status=pending", headers=h).json()) == len(recs) - 1

    assert client.patch(f"/skill-gaps/{rec_id}", headers=h, json={"status": "done"}).status_code == 422
    assert client.get("/skill-gaps?status=done", headers=h).status_code == 422
    assert client.patch("/skill-gaps/999999", headers=h, json={"status": "pending"}).status_code == 404


# ------------------------------------------------------------------
# Newly acquired skills on re-parse
# ------------------------------------------------------------------

def make_docx(skills):
    document = Document()
    for line in ["Candidate", "candidate@example.com", "SKILLS", ", ".join(skills)]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_reparse_detects_newly_acquired_skills(client, create_user, seeded, isolated_uploads):
    user = create_user()
    h = user["headers"]
    upload = client.post("/resumes/upload", headers=h,
                         files={"file": ("cv.docx", make_docx(["Python", "Git"]), DOCX)}).json()
    rid = upload["resume_id"]
    client.post(f"/matches/resumes/{rid}?k=5", headers=h)
    recs = client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={}).json()["recommendations"]
    learned = recs[0]["skill"]

    stored = next(isolated_uploads.rglob("*.docx"))
    stored.write_bytes(make_docx(["Python", "Git", learned]))
    assert client.post(f"/resumes/{rid}/reparse", headers=h).status_code == 200

    rec = next(r for r in client.get("/skill-gaps?current_only=false", headers=h).json()
               if r["skill"] == learned)
    assert rec["status"] == "completed" and rec["completed_via"] == "resume"


def test_deleting_resume_removes_its_recommendations(client, student, seeded):
    rid, h = student["resume_id"], student["headers"]
    client.post(f"/matches/resumes/{rid}", headers=h)
    client.post(f"/skill-gaps/resumes/{rid}", headers=h, json={})
    assert count(seeded, SkillGapRecommendation.resume_id == rid) > 0

    seeded.delete(seeded.get(Resume, rid))
    seeded.commit()
    assert count(seeded, SkillGapRecommendation.resume_id == rid) == 0
