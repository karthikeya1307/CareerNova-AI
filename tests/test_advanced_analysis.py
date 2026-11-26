"""Advanced Matches and Skills & Gaps (test database, synthetic resumes only)."""

from backend.services import job_insights
from test_profile_and_versions import h, upload

RESUME = ["Asha Rao", "asha@example.com | +91 90000 00002", "SKILLS",
          "Python, SQL, Java, Git, HTML, Docker, Communication",
          "EDUCATION", "B.Tech Computer Science, Example Institute of Technology, 2026",
          "PROJECTS", "Sales Report", "Built a report with Python and SQL for 3 stores.",
          "Portfolio Site", "Built a personal site with HTML and CSS."]


def analysis(client, user, role=None):
    response = client.get("/skill-gaps/role-analysis", headers=h(user), params={"role": role} if role else {})
    assert response.status_code == 200, response.text
    return response.json()


def test_general_analysis_groups_skills_with_evidence_and_lists_no_gaps(client, create_user):
    user = create_user()
    upload(client, user, RESUME)
    body = analysis(client, user)
    assert body["mode"] == "general" and body["gaps"] == [] and "choose a target role" in body["note"]
    groups = {g["group"]: {s["skill"]: s for s in g["skills"]} for g in body["current_skills"]}
    assert {"Python", "Java"} <= set(groups["Programming languages"])
    assert groups["Programming languages"]["Python"]["status"] == "demonstrated"         # used in a project
    assert groups["Programming languages"]["Python"]["where"] == ["Sales Report"]
    assert groups["Programming languages"]["Java"]["status"] == "listed"                 # only in the skills list
    assert "Docker" in groups["Cloud & DevOps"] and "SQL" in groups["Databases"]
    assert all("Communication" not in g for g in groups.values())                       # soft skills not listed here
    assert len(body["roles"]) == 14


def test_different_roles_give_different_requirements_and_gaps(client, create_user):
    user = create_user()
    upload(client, user, RESUME)
    java, frontend = analysis(client, user, "java-developer"), analysis(client, user, "frontend-developer")
    assert java["role"]["title"] != frontend["role"]["title"]
    java_skills = {r["skill"] for r in java["requirements"]}
    frontend_skills = {r["skill"] for r in frontend["requirements"]}
    assert java_skills != frontend_skills
    assert {g["skill"] for g in java["gaps"]} != {g["skill"] for g in frontend["gaps"]}
    # Every gap is one of the role's own skills - nothing unrelated is recommended.
    assert {g["skill"] for g in java["gaps"]} <= java_skills
    assert {g["skill"] for g in frontend["gaps"]} <= frontend_skills


def test_gap_statuses_priorities_and_advice(client, create_user):
    user = create_user()
    upload(client, user, RESUME)
    body = analysis(client, user, "java-developer")
    req = {r["skill"]: r for r in body["requirements"]}
    assert req["Java"]["status"] == "listed"
    gaps = {g["skill"]: g for g in body["gaps"]}
    java_gap = gaps["Java"]
    assert java_gap["headline"] == "Listed but not demonstrated" and java_gap["priority"] in ("medium", "low")
    missing_core = [g for g in body["gaps"] if g["status"] == "not_found" and g["importance"] == "core"]
    assert missing_core and all(g["priority"] == "high" and g["headline"] == "Not found in your resume" for g in missing_core)
    priorities = [g["priority"] for g in body["gaps"]]
    assert priorities == sorted(priorities, key={"high": 0, "medium": 1, "low": 2}.get)  # most important first
    for g in body["gaps"]:
        assert g["why"] and g["learn"] and g["practice"] and g["resume_tip"]
        assert body["role"]["title"] in g["why"]
    assert "does not mean you lack it" in body["note"]
    fit = body["fit"]
    assert 0 <= fit["score"] <= 100 and fit["core_total"] == len([r for r in body["requirements"] if r["importance"] == "core"])
    assert "Java" not in body["learning_priorities"] or gaps["Java"]["priority"] != "low"


def test_errors_and_privacy(client, create_user):
    owner, other = create_user(), create_user()
    rid = upload(client, owner, RESUME)
    assert client.get("/skill-gaps/role-analysis", params={"role": "java-developer"}).status_code == 401
    no_resume = client.get("/skill-gaps/role-analysis", headers=h(other), params={"resume_id": rid})
    assert no_resume.status_code == 409 and no_resume.json()["detail"]["code"] == "resume_required"   # never the owner's
    unknown = client.get("/skill-gaps/role-analysis", headers=h(owner), params={"role": "astronaut"})
    assert unknown.status_code == 404
    assert client.get("/skill-gaps/role-analysis", headers=h(owner), params={"role": "../x"}).status_code == 422


def test_match_insights_show_evidence_and_never_claim_a_skill_is_lacking():
    from test_job_matching_modes import internship as make_internship

    internship = make_internship(required=("Python", "SQL", "Kubernetes"), preferred=("Java",))
    evidence = {"python": ["Sales Report"], "sql": ["Sales Report"]}
    result = job_insights.build(internship, {"components": []}, ["Python", "SQL", "Java"], None, evidence=evidence)
    assert {"skill": "Python", "where": ["Sales Report"]} in result["relevant_experience"]
    assert "Java" in result["listed_only_skills"]
    assert any("Your resume shows Python in: Sales Report." == r for r in result["reasons"])
    missing = {m["skill"]: m for m in result["missing_skills"]}
    assert "does not mean you lack the skill" in missing["Kubernetes"]["note"]
    assert result["improvements"][0].startswith("Learn Kubernetes (required for this role)")
    assert "not found in your resume" in result["improvements"][0]
