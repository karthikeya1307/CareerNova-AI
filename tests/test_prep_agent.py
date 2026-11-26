"""HR assignment: resume-based interview preparation agent (chat + REST). Test database only.

The shared student resume (assistant_support.resume_docx) shows Python, FastAPI, PostgreSQL, Docker,
Git and SQL, a B.Tech in Information Technology, a software internship using FastAPI/PostgreSQL and an
"Inventory API" project using Docker.
"""

import re

from assistant_support import ask, new_conversation, other, seeded, student  # noqa: F401
from backend.services import career_tracks, prep
from backend.services.assistant import prep_agent


def h(user):
    return user["headers"]


# ------------------------------------------------------------------
# Role recommendation engine (REST)
# ------------------------------------------------------------------

def test_roles_are_ranked_from_the_resume_with_reasons(client, student):  # noqa: F811
    body = client.get("/prep/roles", headers=h(student)).json()
    roles = body["roles"]
    assert body["resume_id"] == student["resume_id"] and len(roles) == 5
    assert [r["score"] for r in roles] == sorted((r["score"] for r in roles), reverse=True)
    top = roles[0]
    assert top["slug"] in ("python-developer", "backend-developer", "software-developer")
    assert set(top["core"]["have"]) <= {"Python", "FastAPI", "SQL", "Git", "Docker", "REST API", "Django", "Node.js",
                                        "Data Structures", "PostgreSQL"}
    assert any("Python" in r for r in top["reasons"])
    # Evidence names the student's own internship or project, never invented entries.
    titles = [e["title"] for places in top["evidence"].values() for e in places]
    assert titles and all(("Intern" in t) or ("Inventory" in t) or ("REST" in t) or ("Docker" in t) or ("FastAPI" in t) for t in titles)


def test_role_fit_for_a_role_the_resume_does_not_cover(client, student):  # noqa: F811
    java = client.get("/prep/roles/java-developer", headers=h(student)).json()
    python = client.get("/prep/roles/python-developer", headers=h(student)).json()
    assert java["score"] < python["score"]
    assert "Java" in java["core"]["missing"] and "Spring Boot" in java["core"]["missing"]
    assert java["readiness"]["level"] in ("possible", "long_term", "close")


def test_technical_questions_by_level_start_with_resume_skills(client, student):  # noqa: F811
    data = client.get("/prep/roles/python-developer/technical-questions", headers=h(student)).json()
    assert set(data["levels"]) == {"beginner", "intermediate", "advanced"}
    for level, items in data["levels"].items():
        assert items and all(q["level"] == level for q in items)
        assert items[0]["skill_status"] == "on_resume"
        # python-developer core skills Django is not on the resume: one slot per level asks about it.
        assert any(q["skill_status"] == "role_missing" for q in items)
    assert data["project_questions"] and "Inventory API" in " ".join(q["question"] for q in data["project_questions"]) \
        or "Software Intern" in " ".join(q["question"] for q in data["project_questions"])
    only = client.get("/prep/roles/python-developer/technical-questions?level=advanced", headers=h(student)).json()
    assert list(only["levels"]) == ["advanced"]
    assert client.get("/prep/roles/python-developer/technical-questions?level=expert", headers=h(student)).status_code == 422


def test_hr_questions_are_personalised_with_resume_facts_only(client, student):  # noqa: F811
    data = client.get("/prep/roles/data-analyst/hr-questions", headers=h(student)).json()
    texts = [q["question"] for q in data["questions"]]
    assert "Tell me about yourself." in texts
    assert "Why are you interested in the Data Analyst role?" in texts
    personalised = [q for q in data["questions"] if q["personalised"]]
    assert any("Software Intern" in q["question"] or "Inventory API" in q["question"] for q in personalised)


def test_guidance_separates_samples_from_verified_resume_facts(client, student):  # noqa: F811
    q = client.get("/prep/roles/python-developer/technical-questions?level=beginner", headers=h(student)).json()
    qid = q["levels"]["beginner"][0]["id"]
    g = client.get(f"/prep/guidance/{qid}?role=python-developer", headers=h(student)).json()
    assert g["kind"] == "technical" and g["expects"] and g["points"] and g["structure"] and g["mistakes"]
    assert g["sample_answer"]["is_sample"] is True and "not your personal experience" in g["sample_answer"]["label"]

    about = client.get("/prep/guidance/hr-about?role=backend-developer", headers=h(student)).json()
    draft = about["sample_answer"]
    assert draft["is_sample"] is False and "only from your resume" in draft["label"]
    assert "Information Technology" in draft["text"] and "Backend Developer" in draft["text"]
    assert "[" in draft["text"]          # placeholders for the student, not invented achievements
    assert client.get("/prep/guidance/nope", headers=h(student)).status_code == 404


def test_roadmap_prioritises_missing_core_skills(client, student):  # noqa: F811
    r = client.get("/prep/roles/java-developer/roadmap", headers=h(student)).json()
    topics = {t["skill"]: t for s in r["stages"] for t in s["topics"]}
    assert topics["Java"]["priority"] == "high" and topics["Java"]["on_resume"] is False
    assert topics["SQL"]["priority"] == "low" and topics["SQL"]["on_resume"] is True
    assert r["coding_exercises"] and r["project_ideas"] and r["interview_practice"]
    assert any("Inventory API" in p for p in r["project_improvements"])
    assert "Java" in r["skill_gaps"]["core_missing"]


def test_prep_api_needs_a_parsed_resume_and_enforces_ownership(client, create_user, student, other):  # noqa: F811
    assert client.get("/prep/roles").status_code == 401
    fresh = create_user()
    response = client.get("/prep/roles", headers=h(fresh))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "resume_required"
    # Another student's resume id is never usable.
    assert client.get(f"/prep/roles?resume_id={other['resume_id']}", headers=h(student)).status_code == 404
    assert client.get("/prep/roles/not-a-role", headers=h(student)).status_code == 404


# ------------------------------------------------------------------
# The same agent inside the career assistant
# ------------------------------------------------------------------

def test_chat_resume_to_role_to_questions_to_guidance_to_roadmap(client, student):  # noqa: F811
    cid = new_conversation(client, student, assistant="interview")
    a = ask(client, student, cid, "Which roles are suitable for my resume?")
    assert a["intent"] == "role_recommendation" and "fit" in a["content"]
    assert any(s["type"] == "resume" for s in a["sources"]) and any(s["type"] == "career_track" for s in a["sources"])

    a = ask(client, student, cid, "Prepare me for Backend Developer")
    assert a["intent"] == "role_select" and "Target role set: Backend Developer" in a["content"]

    a = ask(client, student, cid, "Generate technical questions")       # uses the selected role
    assert a["intent"] == "technical_questions" and "Backend Developer" in a["content"]
    assert "## Beginner" in a["content"] and "## Advanced" in a["content"]
    numbered = re.findall(r"^(\d+)\. ", a["content"], re.M)
    assert len(numbered) >= 6

    a = ask(client, student, cid, "How do I answer question 1?")
    assert a["intent"] == "answer_guidance"
    for heading in ("What the interviewer expects", "## Points to mention", "## Suggested structure",
                    "## Common mistakes to avoid"):
        assert heading in a["content"]

    a = ask(client, student, cid, "Generate HR questions")
    assert a["intent"] == "hr_questions" and "Tell me about yourself." in a["content"]
    a = ask(client, student, cid, "How do I answer question 1?")
    assert "Draft built only from your resume" in a["content"] and "Information Technology" in a["content"]

    a = ask(client, student, cid, "Create my preparation roadmap")
    assert a["intent"] == "prep_roadmap" and "## Step 1" in a["content"] and "[HIGH]" in a["content"] or "[LOW]" in a["content"]


def test_chat_personal_questions(client, student):  # noqa: F811
    cid = new_conversation(client, student, assistant="interview")
    a = ask(client, student, cid, "What are my strongest technical skills?")
    assert a["intent"] == "strengths" and "FastAPI" in a["content"]
    a = ask(client, student, cid, "Am I suitable for a Data Scientist role?")
    assert a["intent"] == "role_fit" and "Data Scientist" in a["content"] and "Missing core skills" in a["content"]
    a = ask(client, student, cid, "What are my weaknesses?")
    assert a["intent"] == "weaknesses" and "Data Scientist" in a["content"]      # the role just discussed
    a = ask(client, student, cid, "What should I learn to become an AI Engineer?")
    assert a["intent"] == "prep_roadmap" and "AI Engineer" in a["content"] and "Machine Learning" in a["content"]


def test_chat_asks_for_a_role_and_accepts_an_ordinal(client, student):  # noqa: F811
    cid = new_conversation(client, student, assistant="interview")
    a = ask(client, student, cid, "Generate HR questions")
    assert a["intent"] == "hr_questions" and "Which role should I prepare you for?" in a["content"]
    a = ask(client, student, cid, "the second one")
    assert a["intent"] == "hr_questions" and "Tell me about yourself." in a["content"]


def test_chat_without_a_resume_asks_for_one(client, create_user):
    user = create_user()
    cid = new_conversation(client, user, assistant="interview")
    a = ask(client, user, cid, "Which roles are suitable for me?")
    assert a["intent"] == "role_recommendation" and "Upload a PDF or DOCX resume" in a["content"]


def test_two_assistants_keep_separate_scopes(client, student):  # noqa: F811
    # Application Assistant: product guide + own data tools, unchanged; preparation requests are redirected.
    app = new_conversation(client, student)
    assert ask(client, student, app, "How do I upload my resume?")["intent"] == "product_help"
    assert ask(client, student, app, "show my applications")["intent"] == "application_status"
    assert ask(client, student, app, "what should I learn next?")["intent"] != "prep_roadmap"
    redirected = ask(client, student, app, "Which roles are suitable for my resume?")
    assert redirected["intent"] == "assistant_redirect" and "Interview Preparation Assistant" in redirected["content"]
    assert redirected["suggested_actions"][0]["endpoint"] == "/interview-assistant"
    off_topic = ask(client, student, app, "Who won the football world cup in 2018?")
    assert off_topic["intent"] in ("unknown", "product_help") and "CareerNova" in off_topic["content"]

    # Interview Preparation Assistant: preparation agent + interview-relevant data; the rest is redirected.
    prep = new_conversation(client, student, assistant="interview")
    assert ask(client, student, prep, "Which roles are suitable for my resume?")["intent"] == "role_recommendation"
    assert ask(client, student, prep, "what skills am I missing?")["intent"] == "skill_gap"
    moved = ask(client, student, prep, "How do I upload my resume?")
    assert moved["intent"] == "assistant_redirect" and moved["suggested_actions"][0]["endpoint"] == "/assistant"
    assert ask(client, student, prep, "show my applications")["intent"] == "assistant_redirect"
    scope = ask(client, student, prep, "Write me a poem about the sea")
    assert scope["intent"] == "out_of_scope" and "interview preparation" in scope["content"]

    # Each list shows only its own chats; documents attach only to interview chats.
    listed = lambda kind: [c["conversation_id"] for c in client.get(  # noqa: E731
        f"/assistant/conversations?assistant={kind}", headers=h(student)).json()["items"]]
    assert listed("application") == [app] and listed("interview") == [prep]
    detail = client.get(f"/assistant/conversations/{prep}", headers=h(student)).json()
    assert detail["assistant"] == "interview"
    assert client.put(f"/assistant/conversations/{app}/study-document", headers=h(student),
                      json={"document_id": None}).status_code == 409


def test_application_assistant_redirects_every_interview_prep_wording(client, student):  # noqa: F811
    # Interview-preparation wording always goes to the Interview Preparation Assistant, even when the old intent
    # classifier maps it to a shared tool; a generic learning-plan request is still answered here, as before the split.
    app = new_conversation(client, student)
    for wording in ("Give me HR interview questions", "Start a mock interview", "Create my preparation roadmap",
                    "Generate technical questions"):
        reply = ask(client, student, app, wording)
        assert reply["intent"] == "assistant_redirect", wording
        assert reply["suggested_actions"][0]["endpoint"] == "/interview-assistant"
    assert ask(client, student, app, "give me a learning plan")["intent"] != "assistant_redirect"


def test_role_detection_and_catalogue():
    assert len(career_tracks.load_tracks()) == 14
    for text, slug in [("Am I suitable for a Java Developer role?", "java-developer"),
                       ("I want to become an AI/ML engineer", "ai-engineer"),
                       ("full-stack developer", "full-stack-developer"),
                       ("frontend", "frontend-developer"), ("JavaScript tips", None),
                       ("software engineer interview", "software-developer")]:
        found = prep.find_role(text)
        assert (found["slug"] if found else None) == slug, text
    assert prep_agent.detect("Which internship is suitable for my skills?") is None   # existing matches tool



# ------------------------------------------------------------------
# Role-based mock interview (existing interview engine + target role)
# ------------------------------------------------------------------

def test_mock_interview_for_a_target_role_answer_feedback_and_summary(client, student):  # noqa: F811
    response = client.post("/interviews/sessions", headers=h(student), json={
        "resume_id": student["resume_id"], "target_role": "backend-developer", "mode": "mock", "difficulty": "easy",
        "mix": {"technical": 3, "project": 0, "behavioral": 1, "internship": 0}})
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["title"] == "Mock interview - Backend Developer" and session["mode"] == "mock"
    assert session["summary"]["target_role"] == "backend-developer"
    track = career_tracks.get_track("backend-developer")
    role_skills = set(track["core_skills"] + track["advanced_skills"])
    technical = [q for q in session["questions"] if q["category"] == "technical"]
    assert technical and all(q["difficulty"] == "easy" for q in technical)
    assert technical[0]["skill"] in role_skills

    q = technical[0]
    answer = client.post(f"/interviews/sessions/{session['session_id']}/questions/{q['question_id']}/answers",
                         headers=h(student), json={"answer_text": "It is a way to organise code and data so it is reusable "
                                                                 "and easy to test, for example in my Inventory API project."})
    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert body["evaluation"] and body["feedback"]            # rubric feedback incl. missing points
    done = client.post(f"/interviews/sessions/{session['session_id']}/complete", headers=h(student))
    assert done.status_code == 200 and done.json()["status"] == "completed" and done.json()["summary"]

    assert client.post("/interviews/sessions", headers=h(student), json={
        "resume_id": student["resume_id"], "target_role": "astronaut"}).status_code == 422


# ------------------------------------------------------------------
# Phase 6 improvements
# ------------------------------------------------------------------

def test_recommended_roles_list_relevant_open_internships(client, student):  # noqa: F811
    roles = client.get("/prep/roles", headers=h(student)).json()["roles"]
    with_jobs = [r for r in roles if r["internships"]]
    assert with_jobs, "at least one recommended role should list open internships from the seeded data"
    job = with_jobs[0]["internships"][0]
    assert job["internship_id"] in student["open"] and {"matching_skills", "missing_skills"} <= set(job)
    cid = new_conversation(client, student, assistant="interview")
    a = ask(client, student, cid, "Which roles are suitable for my resume?")
    assert "Preparation priorities" in a["content"]
    assert "Internship to look at" in a["content"] and any(s["type"] == "internship" for s in a["sources"])


def test_hr_set_has_problem_solving_and_roadmap_has_practice_questions(client, student):  # noqa: F811
    hr = client.get("/prep/roles/backend-developer/hr-questions", headers=h(student)).json()
    assert any(q["theme"] == "problem_solving" for q in hr["questions"])
    roadmap = client.get("/prep/roles/java-developer/roadmap", headers=h(student)).json()
    assert roadmap["practice_questions"] and roadmap["practice_questions"][0]["skill"] in ("Java", "Spring Boot", "REST API", "Data Structures")
    cid = new_conversation(client, student, assistant="interview")
    a = ask(client, student, cid, "Create a roadmap for Java Developer")
    assert "## Interview questions to practise" in a["content"] and "Resource:" in a["content"]


def test_role_mock_interview_stays_on_role_skills(client, student):  # noqa: F811
    session = client.post("/interviews/sessions", headers=h(student), json={
        "resume_id": student["resume_id"], "target_role": "data-analyst", "mode": "mock",
        "mix": {"technical": 6, "project": 0, "behavioral": 0, "internship": 0}}).json()
    track = career_tracks.get_track("data-analyst")
    role_skills = set(track["core_skills"] + track["advanced_skills"])
    skills = {q["skill"] for q in session["questions"] if q["category"] == "technical"}
    assert skills and skills <= role_skills, skills          # no unrelated resume skills (e.g. FastAPI, Docker)
