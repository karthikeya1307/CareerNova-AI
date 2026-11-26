"""P2: job insights and the two matching modes (For My Resume / Explore Any Job). Test database only."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from assistant_support import seeded, student  # noqa: F401
from backend.models import Internship, InternshipSkill, Skill
from backend.services import job_insights
from backend.services.matching_agent import is_eligible

KEYS = {"skill_match", "eligibility", "application_readiness", "category", "category_label", "matched_skills",
        "partial_skills", "missing_skills", "reasons", "improvements", "application_url", "source"}


def internship(required=(), preferred=(), **extra):
    item = Internship(internship_id=1, title="Backend Intern", company="Nimbus", is_active=True,
                      application_url="https://example.com/apply", source="dataset", **extra)
    item.skill_links = [InternshipSkill(skill=Skill(skill_id=n, name=s, category="language"), importance=imp)
                        for n, (s, imp) in enumerate([*[(s, "required") for s in required],
                                                      *[(s, "preferred") for s in preferred]])]
    return item


EDU_OK = {"components": [{"name": "education", "score": 1.0, "status": "assessed", "detail": "B.Tech meets the requirement"}]}


# ------------------------------------------------------------------
# Insights formula
# ------------------------------------------------------------------

def test_skill_match_formula_and_apply_now():
    job = internship(required=("Python", "SQL"), preferred=("Docker",))
    result = job_insights.build(job, EDU_OK, ["Python", "SQL", "Docker"], readiness_score=80)
    assert result["skill_match"] == 100 and result["category"] == "apply_now"
    assert result["application_readiness"] == round(0.6 * 100 + 0.25 * 80 + 0.15 * 100)
    assert set(result) >= KEYS and result["application_url"] == "https://example.com/apply"
    assert result["reasons"][0] == "You have 2 of 2 required skills: Python, SQL."


def test_partial_and_missing_skills_lower_the_match():
    job = internship(required=("Python", "PostgreSQL", "Kubernetes"), preferred=("Docker",))
    result = job_insights.build(job, EDU_OK, ["Python", "MySQL"], readiness_score=60)
    assert [s["skill"] for s in result["matched_skills"]] == ["Python"]
    assert result["partial_skills"] == [{"skill": "PostgreSQL", "importance": "required", "related": ["MySQL"]}]
    assert {s["skill"] for s in result["missing_skills"]} == {"Kubernetes", "Docker"}
    # required share = (1 + 0.5 + 0) / 3 = 0.5 ; preferred share = 0
    assert result["skill_match"] == round(100 * (0.8 * 0.5 + 0.2 * 0))
    assert result["category"] == "improve"
    assert result["improvements"][0].startswith("Learn Kubernetes (required for this role)")
    assert any("readiness 60/100" in tip for tip in result["improvements"])
    assert any("MySQL" in r for r in result["reasons"])


def test_long_term_when_far_off_or_not_eligible_or_closed():
    far = job_insights.build(internship(required=("Go", "Rust", "Kafka", "Kubernetes")), EDU_OK, ["Excel"], 70)
    assert far["category"] == "long_term" and far["skill_match"] == 0
    below = {"components": [{"name": "education", "score": 0.1, "status": "assessed", "detail": "is below the degree requirement"}]}
    not_eligible = job_insights.build(internship(required=("Python",)), below, ["Python"], 90)
    assert not_eligible["eligibility"]["status"] == "not_eligible" and not_eligible["category"] == "long_term"
    closed = job_insights.build(internship(required=("Python",), deadline=datetime.now(timezone.utc) - timedelta(days=1)),
                                EDU_OK, ["Python"], 90)
    assert closed["eligibility"]["status"] == "closed" and closed["category"] == "long_term"


@pytest.mark.parametrize("component, status", [
    (None, "open"),
    ({"name": "education", "status": "not_stated", "score": 0.5}, "open"),
    ({"name": "education", "status": "unknown", "score": 0.3}, "unknown"),
    ({"name": "education", "status": "assessed", "score": 0.5}, "check"),
])
def test_eligibility_states(component, status):
    breakdown = {"components": [component] if component else []}
    assert job_insights.build(internship(required=("Python",)), breakdown, ["Python"], None)["eligibility"]["status"] == status


def test_no_skills_listed_gives_no_skill_match_instead_of_a_made_up_number():
    result = job_insights.build(internship(), EDU_OK, ["Python"], None)
    assert result["skill_match"] is None and result["matched_skills"] == [] and result["category"] == "improve"


# ------------------------------------------------------------------
# For My Resume (existing matching endpoints, now with insights)
# ------------------------------------------------------------------

def test_for_my_resume_results_carry_insights(client, student):  # noqa: F811
    run = client.post(f"/matches/resumes/{student['resume_id']}?k=5", headers=student["headers"])
    assert run.status_code == 201
    for item in run.json()["results"]:
        insights = item["insights"]
        assert set(insights) >= KEYS
        assert insights["category"] in ("apply_now", "improve", "long_term")
        matched = {s["skill"] for s in insights["matched_skills"]}
        assert set(item["matched_required_skills"]) <= matched           # consistent with the score breakdown
        assert insights["application_url"] == item["internship"]["application_url"]
    latest = client.get(f"/matches/resumes/{student['resume_id']}", headers=student["headers"]).json()
    assert all(r["insights"] for r in latest["results"])
    one = client.get(f"/matches/resumes/{student['resume_id']}/internships/{latest['results'][0]['internship']['internship_id']}",
                     headers=student["headers"]).json()
    assert one["insights"]["skill_match"] is not None


# ------------------------------------------------------------------
# Explore Any Job
# ------------------------------------------------------------------

def test_explore_without_a_resume_lists_every_open_job(client, student, seeded):  # noqa: F811
    open_jobs = [i for i in seeded.scalars(select(Internship).where(Internship.is_active.is_(True))) if is_eligible(i)]
    page = client.get("/matches/explore", headers=student["headers"], params={"limit": 50}).json()
    assert page["mode"] == "explore" and page["resume_id"] is None
    assert page["total"] == len(open_jobs) and page["category_counts"] is None
    assert all(item["insights"] is None and item["score"] is None for item in page["items"])


def test_explore_with_a_resume_scores_every_job_without_restricting_the_list(client, student, seeded):  # noqa: F811
    params = {"resume_id": student["resume_id"], "limit": 50}
    page = client.get("/matches/explore", headers=student["headers"], params=params).json()
    plain = client.get("/matches/explore", headers=student["headers"], params={"limit": 50}).json()
    assert page["total"] == plain["total"]                              # not limited to the best matches
    assert all(set(item["insights"]) >= KEYS for item in page["items"])
    counts = page["category_counts"]
    assert sum(counts.values()) == page["total"]
    for category, count in counts.items():
        filtered = client.get("/matches/explore", headers=student["headers"],
                              params={**params, "category": category}).json()
        assert filtered["total"] == count
        assert all(i["insights"]["category"] == category for i in filtered["items"])


def test_explore_filters_and_paging(client, student, seeded):  # noqa: F811
    first = seeded.scalars(select(Internship).where(Internship.is_active.is_(True)).order_by(Internship.internship_id)).first()
    word = first.title.split()[0]
    hits = client.get("/matches/explore", headers=student["headers"], params={"q": word}).json()
    assert hits["total"] >= 1 and all(word.lower() in (i["internship"]["title"] + i["internship"]["company"]
                                                        + (i["internship"]["description"] or "")
                                                        + (i["internship"]["domain"] or "")).lower()
                                       for i in hits["items"])
    page1 = client.get("/matches/explore", headers=student["headers"], params={"limit": 3}).json()
    page2 = client.get("/matches/explore", headers=student["headers"], params={"limit": 3, "skip": 3}).json()
    assert len(page1["items"]) == 3 and {i["internship"]["internship_id"] for i in page1["items"]}.isdisjoint(
        {i["internship"]["internship_id"] for i in page2["items"]})


def test_explore_hides_closed_jobs_and_other_students_resumes(client, student, create_user, seeded):  # noqa: F811
    job = seeded.scalars(select(Internship).where(Internship.is_active.is_(True))).first()
    job.deadline = datetime.now(timezone.utc) - timedelta(days=1)
    seeded.commit()
    ids = {i["internship"]["internship_id"] for i in
           client.get("/matches/explore", headers=student["headers"], params={"limit": 50}).json()["items"]}
    assert job.internship_id not in ids
    stranger = create_user()
    assert client.get("/matches/explore", headers=stranger["headers"],
                      params={"resume_id": student["resume_id"]}).status_code == 404
    assert client.get("/matches/explore").status_code == 401
