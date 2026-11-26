"""P3: skill progress + per-job roadmap, career tracks, job-source tracking (test database only)."""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
from sqlalchemy import select

from assistant_support import seeded, student  # noqa: F401
from backend.models import AdminAuditEvent, Internship, SkillGapRecommendation, SkillProgress
from backend.services import career_tracks, job_sources, skill_progress


def h(user):
    return user["headers"]


def first_open(db):
    return db.scalars(select(Internship).where(Internship.is_active.is_(True)).order_by(Internship.internship_id)).first()


# ------------------------------------------------------------------
# Skill progress
# ------------------------------------------------------------------

def test_progress_moves_through_the_four_states_and_persists(client, student, db_session):  # noqa: F811
    for state in ("learning", "practiced", "completed", "not_started"):
        response = client.put("/skill-gaps/progress", headers=h(student), json={"skill": "docker", "status": state})
        assert response.status_code == 200 and response.json()["skill"] == "Docker" and response.json()["status"] == state
    listed = client.get("/skill-gaps/progress", headers=h(student)).json()
    assert listed["statuses"] == ["not_started", "learning", "practiced", "completed"]
    assert listed["skills"]["Docker"]["status"] == "not_started"
    assert db_session.scalars(select(SkillProgress)).all()[0].status == "not_started"       # one row, updated


def test_progress_validation_and_isolation(client, student, create_user):  # noqa: F811
    assert client.put("/skill-gaps/progress", headers=h(student), json={"skill": "Docker", "status": "mastered"}).status_code == 422
    unknown = client.put("/skill-gaps/progress", headers=h(student), json={"skill": "Underwater Basket Weaving", "status": "learning"})
    assert unknown.status_code == 404
    client.put("/skill-gaps/progress", headers=h(student), json={"skill": "CI/CD", "status": "learning"})
    other = create_user()
    assert client.get("/skill-gaps/progress", headers=h(other)).json()["skills"] == {}
    assert client.get("/skill-gaps/progress").status_code == 401


def test_progress_updates_matching_recommendations(client, student, db_session):  # noqa: F811
    client.post(f"/matches/resumes/{student['resume_id']}?k=5", headers=h(student))
    generated = client.post(f"/skill-gaps/resumes/{student['resume_id']}", headers=h(student))
    assert generated.status_code in (200, 201), generated.text
    rec = db_session.scalars(select(SkillGapRecommendation).where(SkillGapRecommendation.is_current.is_(True))).first()
    skill_name = rec.skill.name
    client.put("/skill-gaps/progress", headers=h(student), json={"skill": skill_name, "status": "practiced"})
    db_session.expire_all()
    assert db_session.get(SkillGapRecommendation, rec.recommendation_id).status == "in_progress"
    client.put("/skill-gaps/progress", headers=h(student), json={"skill": skill_name, "status": "completed"})
    db_session.expire_all()
    updated = db_session.get(SkillGapRecommendation, rec.recommendation_id)
    assert updated.status == "completed" and updated.completed_via == "user"


# ------------------------------------------------------------------
# Per-job roadmap
# ------------------------------------------------------------------

def test_roadmap_for_one_job(client, student, seeded):  # noqa: F811
    job = first_open(seeded)
    url = f"/skill-gaps/resumes/{student['resume_id']}/internships/{job.internship_id}/roadmap"
    roadmap = client.get(url, headers=h(student)).json()
    assert roadmap["internship_id"] == job.internship_id and roadmap["progress"]["completed"] == 0
    required, preferred = [l.skill.name for l in job.skill_links if l.importance == "required"], \
                          [l.skill.name for l in job.skill_links if l.importance == "preferred"]
    for step in roadmap["steps"]:
        assert step["skill"] in required + preferred and step["skill"] not in roadmap["have"]
        assert step["gap"] in ("missing", "partial") and step["status"] == "not_started"
        assert step["why"].startswith(f"{job.title} at {job.company} lists {step['skill']}")
        assert step["learning"]["topics"] and step["project"]
        if step["resource"]:
            assert urlparse(step["resource"]["url"]).scheme == "https"
    if roadmap["steps"]:
        target = roadmap["steps"][0]["skill"]
        client.put("/skill-gaps/progress", headers=h(student), json={"skill": target, "status": "completed"})
        again = client.get(url, headers=h(student)).json()
        assert again["steps"][0]["status"] == "completed" and again["progress"]["completed"] == 1


def test_roadmap_orders_prerequisites_first(db_session):
    from backend.models import InternshipSkill, Skill
    job = Internship(internship_id=1, title="Platform Intern", company="Nimbus", is_active=True, domain="DevOps/Cloud")
    job.skill_links = [InternshipSkill(skill=Skill(skill_id=i, name=n), importance="required")
                       for i, n in enumerate(["Kubernetes", "Docker", "Linux"])]
    order = [s["skill"] for s in skill_progress.roadmap(db_session, 0, [], job, 0)["steps"]]
    from backend.services.learning_plans import plan_for
    for i, name in enumerate(order):
        for prereq in plan_for(name).get("prerequisites", []):
            if prereq in order:
                assert order.index(prereq) < i, (prereq, name)


def test_roadmap_is_owner_only_and_needs_an_open_job(client, student, create_user, seeded):  # noqa: F811
    job = first_open(seeded)
    other = create_user()
    assert client.get(f"/skill-gaps/resumes/{student['resume_id']}/internships/{job.internship_id}/roadmap",
                      headers=h(other)).status_code == 404
    job.is_active = False
    seeded.commit()
    assert client.get(f"/skill-gaps/resumes/{student['resume_id']}/internships/{job.internship_id}/roadmap",
                      headers=h(student)).status_code == 404


# ------------------------------------------------------------------
# Career tracks
# ------------------------------------------------------------------

def test_eleven_tracks_with_complete_content(client, create_user):
    user = create_user()
    tracks = client.get("/career-tracks", headers=h(user)).json()
    assert {t["slug"] for t in tracks} == career_tracks.EXPECTED_SLUGS and len(tracks) == 14
    for summary in tracks:
        detail = client.get(f"/career-tracks/{summary['slug']}", headers=h(user)).json()
        assert detail["skills"] and detail["roadmap"] and detail["exercises"] and detail["projects"]
        assert detail["resume_advice"] and detail["interview_questions"], summary["slug"]
        assert detail["coverage"] is None                                           # no resume given
        for skill in detail["skills"]:
            assert skill["status"] == "not_started" and skill["topics"]
            if skill["resource"]:
                assert urlparse(skill["resource"]["url"]).scheme == "https"
    assert client.get("/career-tracks/astronaut", headers=h(user)).status_code == 404


def test_interview_questions_come_from_the_question_bank():
    from backend.services.question_bank import technical_bank
    bank = {q["question"] for questions in technical_bank()["technical"].values() for q in questions}
    for track in career_tracks.load_tracks():
        for q in career_tracks.detail(track)["interview_questions"]:
            assert q["question"] in bank


def test_resources_are_only_curated_official_links():
    curated = skill_progress.official_resources()
    for track in career_tracks.load_tracks():
        for skill in career_tracks.detail(track)["skills"]:
            assert skill["resource"] in (None, curated.get(skill["skill"]))


def test_track_coverage_progress_and_jobs(client, student, create_user, seeded):  # noqa: F811
    client.put("/skill-gaps/progress", headers=h(student), json={"skill": "Docker", "status": "learning"})
    detail = client.get("/career-tracks/python-developer", headers=h(student),
                        params={"resume_id": student["resume_id"]}).json()
    by_skill = {s["skill"]: s for s in detail["skills"]}
    assert by_skill["Python"]["on_resume"] is True and by_skill["Docker"]["status"] == "learning"
    assert detail["coverage"]["on_resume"] >= 3
    stranger = create_user()
    assert client.get("/career-tracks/python-developer", headers=h(stranger),
                      params={"resume_id": student["resume_id"]}).status_code == 404
    jobs = client.get("/career-tracks/data-scientist/jobs", headers=h(student)).json()["items"]
    overlaps = [j["track_skill_overlap"] for j in jobs]
    assert overlaps == sorted(overlaps, reverse=True) and all(o >= 2 for o in overlaps)
    assert all(j["internship"]["source_label"] == "Sample listing (curated dataset)" for j in jobs)


# ------------------------------------------------------------------
# Job-source tracking
# ------------------------------------------------------------------

@pytest.fixture
def admin(create_user):
    return create_user(role="admin")


def test_seeded_listings_have_dedup_keys_and_are_labelled_samples(client, student, seeded):  # noqa: F811
    job = first_open(seeded)
    assert job.dedup_key == job_sources.dedup_key(job.title, job.company, job.location)
    item = client.get(f"/internships/{job.internship_id}", headers=h(student)).json()
    assert item["source"] == "dataset" and item["source_label"] == "Sample listing (curated dataset)"
    assert item["freshness"] == "unverified" and item["posted_at"] is None and item["source_url"] is None


def test_admin_listing_with_source_details_duplicates_and_verification(client, admin, db_session):
    body = {"title": "Data Analyst Intern", "company": "Ledger Co", "location": "Pune",
            "source_url": "https://careers.example.com/jobs/123", "posted_at": "2026-11-20T00:00:00Z",
            "application_url": "https://careers.example.com/jobs/123/apply", "required_skills": ["SQL"]}
    created = client.post("/internships/", headers=h(admin), json=body)
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["source_url"] == body["source_url"] and job["posted_at"].startswith("2026-11-20")
    assert job["source"] == "admin" and job["freshness"] == "unverified"

    dup = client.post("/internships/", headers=h(admin), json={**body, "title": "data analyst  intern!", "company": "LEDGER CO."})
    assert dup.status_code == 409 and dup.json()["detail"]["existing_internship_id"] == job["internship_id"]
    other = client.post("/internships/", headers=h(admin), json={**body, "location": "Mumbai"}).json()
    clash = client.patch(f"/internships/{other['internship_id']}", headers=h(admin), json={"location": "Pune"})
    assert clash.status_code == 409

    assert client.post("/internships/", headers=h(admin), json={**body, "title": "X", "source_url": "javascript:alert(1)"}).status_code == 422
    verified = client.post(f"/internships/{job['internship_id']}/verify", headers=h(admin)).json()
    assert verified["freshness"] == "verified" and verified["last_verified_at"]
    assert db_session.scalars(select(AdminAuditEvent).where(AdminAuditEvent.action == "internship.verify")).one()


def test_freshness_states():
    now = datetime(2026, 11, 24, tzinfo=timezone.utc)
    job = Internship(title="t", company="c", is_active=True, source="admin")
    assert job_sources.freshness(job, now) == "unverified"
    job.last_verified_at = now - timedelta(days=3)
    assert job_sources.freshness(job, now) == "verified"
    job.last_verified_at = now - timedelta(days=45)
    assert job_sources.freshness(job, now) == "stale"
    job.deadline = now - timedelta(days=1)
    assert job_sources.freshness(job, now) == "expired"


def test_source_filters_and_duplicate_hiding_in_explore(client, student, admin, seeded):  # noqa: F811
    client.post("/internships/", headers=h(admin), json={"title": "Unique Admin Role", "company": "Acme", "required_skills": ["Python"]})
    admin_only = client.get("/internships/", headers=h(student), params={"source": "admin"}).json()
    assert admin_only["total"] == 1 and admin_only["items"][0]["source"] == "admin"
    assert client.get("/internships/", headers=h(student), params={"source": "scraped"}).status_code == 422
    explore = client.get("/matches/explore", headers=h(student), params={"source": "dataset", "limit": 50}).json()
    assert all(i["internship"]["source"] == "dataset" for i in explore["items"])

    # A duplicate that bypassed the API (e.g. an old import) is shown once.
    job = first_open(seeded)
    seeded.add(Internship(title=job.title, company=job.company, location=job.location, source="manual",
                          is_active=True, dedup_key=job.dedup_key))
    seeded.commit()
    page = client.get("/matches/explore", headers=h(student), params={"limit": 50}).json()
    ids = [i["internship"]["internship_id"] for i in page["items"]]
    assert job.internship_id in ids and page["duplicates_hidden"] == 1
    insights = client.get("/matches/explore", headers=h(student),
                          params={"resume_id": student["resume_id"], "limit": 1}).json()["items"][0]["insights"]
    assert {"source_label", "freshness", "source_url", "posted_at", "last_verified_at"} <= set(insights)
