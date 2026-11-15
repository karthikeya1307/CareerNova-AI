"""Phase 3: matching API endpoints."""

import uuid

import pytest
from sqlalchemy import select

from backend.models import Internship, Resume, ResumeExtraction, User
from backend.services.internship_seed import load_dataset, seed_internships, validate_records
from backend.services.resume_skills import sync_resume_skills

SUBSET = load_dataset()[:30]


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
    user["resume_id"] = add_resume(seeded, user["user_id"], ["Python", "SQL", "Linux", "Git", "Docker"])
    return user


COMPONENT_NAMES = ["skills", "semantic", "education", "location"]


def assert_item_shape(item):
    assert 0 <= item["score"] <= 100
    assert item["label"] in {"Excellent", "Strong", "Fair", "Weak"}
    assert [c["name"] for c in item["components"]] == COMPONENT_NAMES
    for key in ("matched_required_skills", "missing_required_skills",
                "matched_preferred_skills", "missing_preferred_skills",
                "missing_information", "caps_applied", "explanation"):
        assert isinstance(item[key], list)
    assert item["internship"]["internship_id"]
    assert item["algorithm_version"] == "v1"


# ------------------------------------------------------------------
# Access control
# ------------------------------------------------------------------

@pytest.mark.parametrize("method, path", [
    ("POST", "/matches/resumes/1"), ("GET", "/matches/resumes/1"),
    ("GET", "/matches/resumes/1/history"), ("GET", f"/matches/runs/{uuid.uuid4()}"),
    ("GET", "/matches/resumes/1/internships/1"),
])
def test_login_required(client, method, path):
    assert client.request(method, path).status_code == 401


def test_other_users_resume_returns_404(client, student, create_user, seeded):
    other = create_user()
    rid = student["resume_id"]
    iid = seeded.scalar(select(Internship.internship_id).limit(1))

    run = client.post(f"/matches/resumes/{rid}", headers=student["headers"]).json()

    for method, path in [
        ("POST", f"/matches/resumes/{rid}"), ("GET", f"/matches/resumes/{rid}"),
        ("GET", f"/matches/resumes/{rid}/history"), ("GET", f"/matches/runs/{run['run_id']}"),
        ("GET", f"/matches/resumes/{rid}/internships/{iid}"),
    ]:
        assert client.request(method, path, headers=other["headers"]).status_code == 404


# ------------------------------------------------------------------
# Runs
# ------------------------------------------------------------------

def test_run_latest_history_and_detail(client, student):
    headers, rid = student["headers"], student["resume_id"]

    assert client.get(f"/matches/resumes/{rid}", headers=headers).status_code == 404

    created = client.post(f"/matches/resumes/{rid}?k=5", headers=headers)
    assert created.status_code == 201
    run = created.json()
    assert run["resume_id"] == rid and run["algorithm_version"] == "v1"
    assert 1 <= len(run["results"]) <= 5
    assert [r["rank"] for r in run["results"]] == list(range(1, len(run["results"]) + 1))
    for item in run["results"]:
        assert_item_shape(item)

    latest = client.get(f"/matches/resumes/{rid}", headers=headers).json()
    assert latest["run_id"] == run["run_id"]
    assert [r["score"] for r in latest["results"]] == [r["score"] for r in run["results"]]
    assert latest["results"][0]["components"] == run["results"][0]["components"]

    second = client.post(f"/matches/resumes/{rid}?k=3", headers=headers).json()
    history = client.get(f"/matches/resumes/{rid}/history", headers=headers).json()
    assert [h["run_id"] for h in history] == [second["run_id"], run["run_id"]]
    assert history[1]["result_count"] == len(run["results"])
    assert history[1]["top_score"] == run["results"][0]["score"]

    detail = client.get(f"/matches/runs/{run['run_id']}", headers=headers)
    assert detail.status_code == 200 and detail.json()["run_id"] == run["run_id"]

    assert client.get(f"/matches/runs/{uuid.uuid4()}", headers=headers).status_code == 404


def test_query_validation(client, student):
    headers, rid = student["headers"], student["resume_id"]
    assert client.post(f"/matches/resumes/{rid}?k=0", headers=headers).status_code == 422
    assert client.post(f"/matches/resumes/{rid}?k=51", headers=headers).status_code == 422
    assert client.post(f"/matches/resumes/{rid}?work_mode=Moon", headers=headers).status_code == 422


def test_work_mode_and_location_parameters(client, student):
    headers, rid = student["headers"], student["resume_id"]
    run = client.post(
        f"/matches/resumes/{rid}?k=20&work_mode=Onsite&location=Pune", headers=headers
    ).json()
    assert run["filters"] == {"k": 20, "work_mode": "Onsite", "location_override": True}
    assert all(r["internship"]["work_mode"] == "Onsite" for r in run["results"])


def test_resume_without_skills_returns_422(client, create_user, seeded):
    user = create_user()
    rid = add_resume(seeded, user["user_id"], [])
    response = client.post(f"/matches/resumes/{rid}", headers=user["headers"])
    assert response.status_code == 422


# ------------------------------------------------------------------
# Single internship score
# ------------------------------------------------------------------

def test_single_internship_score(client, student, create_user, seeded):
    headers, rid = student["headers"], student["resume_id"]
    internship = seeded.scalar(select(Internship).limit(1))

    response = client.get(
        f"/matches/resumes/{rid}/internships/{internship.internship_id}", headers=headers
    )
    assert response.status_code == 200
    item = response.json()
    assert_item_shape(item)
    assert item["rank"] is None

    internship.is_active = False
    seeded.commit()
    assert client.get(
        f"/matches/resumes/{rid}/internships/{internship.internship_id}", headers=headers
    ).status_code == 404
    assert client.get(
        f"/matches/resumes/{rid}/internships/999999", headers=headers
    ).status_code == 404


def test_single_score_rejects_expired_internship(client, student, seeded):
    from datetime import datetime, timedelta, timezone

    internship = seeded.scalar(select(Internship).limit(1))
    internship.deadline = datetime.now(timezone.utc) - timedelta(days=1)
    seeded.commit()

    response = client.get(
        f"/matches/resumes/{student['resume_id']}/internships/{internship.internship_id}",
        headers=student["headers"],
    )
    assert response.status_code == 404


def test_items_expose_consistent_score_breakdown(client, student):
    run = client.post(f"/matches/resumes/{student['resume_id']}?k=10",
                      headers=student["headers"]).json()
    for item in run["results"]:
        weighted = sum(c["weighted"] for c in item["components"])
        assert weighted == pytest.approx(item["score_before_caps"], abs=0.05)
        assert item["score"] <= item["score_before_caps"] + 0.05


def test_deleting_resume_via_api_removes_its_match_history(client, student):
    headers, rid = student["headers"], student["resume_id"]
    run = client.post(f"/matches/resumes/{rid}", headers=headers).json()

    assert client.delete(f"/resumes/{rid}", headers=headers).status_code == 204
    assert client.get(f"/matches/resumes/{rid}", headers=headers).status_code == 404
    assert client.get(f"/matches/runs/{run['run_id']}", headers=headers).status_code == 404


def test_resume_deleted_during_matching_returns_409(client, student, monkeypatch):
    from sqlalchemy import delete as sql_delete

    from backend import database
    from backend.services import matching_agent

    original = matching_agent.find_candidates

    def delete_resume_midway(db, context, semantic, work_mode, now):
        result = original(db, context, semantic, work_mode, now)
        with database.engine.begin() as connection:   # a separate request
            connection.execute(sql_delete(Resume).where(Resume.resume_id == student["resume_id"]))
        return result

    monkeypatch.setattr(matching_agent, "find_candidates", delete_resume_midway)
    response = client.post(f"/matches/resumes/{student['resume_id']}", headers=student["headers"])
    assert response.status_code == 409


def test_missing_profile_reported_in_results(client, student):
    run = client.post(f"/matches/resumes/{student['resume_id']}", headers=student["headers"]).json()
    item = run["results"][0]
    statuses = {c["name"]: c["status"] for c in item["components"]}
    assert statuses["semantic"] == "unavailable"           # no index built in this test
    assert item["data_completeness"] < 1.0
    assert item["label"] != "Excellent"
    assert any("degree" in m.lower() for m in item["missing_information"]) or statuses["education"] != "unknown"
