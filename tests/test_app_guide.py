"""Application Assistant: step-by-step guidance through the real CareerNova AI workflow (test database only).

The steps name the real pages, say what the student provides and what CareerNova does next, and adapt to the
student's own records: a step is marked done only when the data proves it. The Application Assistant keeps its
CareerNova-only scope and the Interview Preparation Assistant stays a separate experience.
"""

import re

import pytest

from assistant_support import ask, new_conversation, seeded, student  # noqa: F401
from backend.services.assistant import app_guide


def endpoints(answer):
    return [a["endpoint"] for a in answer["suggested_actions"] or []]


def step_line(content, number):
    return next(line for line in content.splitlines() if line.startswith(f"{number}. "))


@pytest.mark.parametrize("text, topic", [
    ("How does this application work?", "overview"),
    ("How does CareerNova AI work?", "overview"),
    ("How do I get started?", "overview"),
    ("Where should I start?", "overview"),
    ("What should I do next?", "overview"),
    ("what is the flow of this product", "overview"),
    ("What should I do after uploading my resume?", "after_resume"),
    ("How can I find internships?", "internships"),
    ("Where can I find suitable internships?", "internships"),
    ("How can I prepare for interviews?", "interviews"),
    ("How do I prepare for an interview?", "interviews"),
    ("What should I do after registration?", "after_registration"),
    ("I just signed up, what now? What should I do after signing up?", "after_registration"),
    ("How can I improve my resume?", "improve_resume"),
    ("How can I improve my resume for this internship?", None),   # a data question about one internship
    ("How do I upload my resume?", None),                     # still a product-guide question
    ("How does interview preparation work?", None),            # still a product-guide question
    ("What is this application?", None),
    ("Give me HR interview questions", None),
    ("who is ronaldo", None),
])
def test_workflow_questions_are_recognised(text, topic):
    assert app_guide.detect(text) == topic


def test_new_student_gets_numbered_steps_with_real_pages_and_nothing_claimed(client, create_user):
    user = create_user()
    cid = new_conversation(client, user)
    answer = ask(client, user, cid, "How does this application work?")
    assert answer["intent"] == "app_guide"
    content = answer["content"]
    numbered = [line for line in content.splitlines() if re.match(r"^\d{1,2}\. ", line)]
    assert [int(line.split(".")[0]) for line in numbered] == list(range(1, 11))
    for page in ("Profile", "Resumes", "Matches", "Skill gaps", "Interview Prep Assistant", "Interview practice"):
        assert page in content
    assert step_line(content, 1).startswith("1. ✓ ")                          # signed in: proven by the session
    for n in range(2, 11):
        assert "✓" not in step_line(content, n), n                              # nothing else is claimed
    assert "no resume uploaded" in step_line(content, 3)
    assert "## Your next step" in content and "**2. Complete your profile** - go to **Profile**" in content
    assert "You provide:" in content and "CareerNova then" in content
    assert endpoints(answer) == ["/profile"]
    assert "product_doc" in {s["type"] for s in answer["sources"]}
    assert answer["generation_method"] == "deterministic"
    listed = client.get("/assistant/conversations", headers=user["headers"]).json()["items"]
    assert listed[0]["title"] == "How CareerNova AI works"


def test_guidance_follows_the_students_real_progress(client, student):  # noqa: F811
    h = student["headers"]
    cid = new_conversation(client, student)
    first = ask(client, student, cid, "How do I get started?")["content"]
    assert "✓" in step_line(first, 3) and "is parsed" in step_line(first, 3)  # the fixture uploaded a resume
    score = client.get(f"/resumes/{student['resume_id']}/readiness", headers=h).json()
    assert f"{score['score']}/100 ({score['label']})" in step_line(first, 5)  # the real score, not a constant
    assert "no match results for this resume yet" in step_line(first, 6) and "✓" not in step_line(first, 6)
    assert "**2. Complete your profile**" in first                            # next: the empty profile

    assert client.post("/profiles/", headers=h, json={"college": "Example Institute", "degree": "B.Tech",
                                                      "graduation_year": 2026, "location": "Pune"}).status_code == 201
    assert client.post(f"/matches/resumes/{student['resume_id']}", headers=h).status_code == 201
    later = ask(client, student, cid, "What should I do next?")["content"]
    assert "✓" in step_line(later, 2) and "✓" in step_line(later, 6)
    assert "**7. Understand your skill gaps** - go to **Skill gaps**" in later   # the next undone step


def test_after_uploading_a_resume_lists_the_following_steps(client, student):  # noqa: F811
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "What should I do after uploading my resume?")
    content = answer["content"]
    assert answer["intent"] == "app_guide" and content.startswith("After uploading your resume")
    order = [content.index(f"**{n}. ") for n in (4, 5, 6, 7)]
    assert order == sorted(order)
    assert "Edit details" in content and "no corrections saved so far" in content
    assert {"/resumes", "/matches", "/skill-gaps"} <= set(endpoints(answer))


def test_improving_the_resume_uses_its_own_readiness_recommendations(client, student):  # noqa: F811
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "How can I improve my resume?")
    content = answer["content"]
    assert answer["intent"] == "app_guide" and "**4. Check the extracted details**" in content
    tips = client.get(f"/resumes/{student['resume_id']}/readiness", headers=student["headers"]).json()["recommendations"]
    assert tips and all(f"- {tip}" in content for tip in tips[:3])      # the real checks, not generic advice
    assert "Documents" in content and "/resumes" in endpoints(answer)


def test_after_registration_for_a_new_student(client, create_user):
    user = create_user()
    cid = new_conversation(client, user)
    answer = ask(client, user, cid, "What should I do after registration?")
    content = answer["content"]
    assert answer["intent"] == "app_guide" and content.startswith("After registering and signing in")
    assert [content.index(f"**{n}. ") for n in (2, 3, 4)] == sorted(content.index(f"**{n}. ") for n in (2, 3, 4))
    assert "no resume uploaded" in content and endpoints(answer)[:2] == ["/profile", "/resumes"]


def test_finding_internships(client, student):  # noqa: F811
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "How can I find internships?")
    assert answer["intent"] == "app_guide" and "**6. Find matching internships** - go to **Matches" in answer["content"]
    assert "Documents" in answer["content"] and "Applications" in answer["content"]
    assert endpoints(answer)[0] == "/matches"


def test_interview_question_points_to_the_separate_interview_assistant(client, student):  # noqa: F811
    app = new_conversation(client, student)
    answer = ask(client, student, app, "How can I prepare for interviews?")
    assert answer["intent"] == "app_guide"
    assert "Interview Preparation Assistant" in answer["content"] and "/interview-assistant" in endpoints(answer)
    assert "?" not in "".join(line for line in answer["content"].splitlines() if line.startswith("- You provide"))
    # The guide doesn't do interview preparation itself: questions still go to the other assistant.
    assert ask(client, student, app, "Give me HR interview questions")["intent"] == "assistant_redirect"
    # And the Interview Preparation Assistant never answers with the application guide.
    prep = new_conversation(client, student, assistant="interview")
    assert ask(client, student, prep, "How does this application work?")["intent"] != "app_guide"


def test_follow_ups_about_a_step_and_what_next(client, student):  # noqa: F811
    cid = new_conversation(client, student)
    assert ask(client, student, cid, "tell me more about step 4")["intent"] != "app_guide"   # no guide yet
    ask(client, student, cid, "How does this application work?")
    detail = ask(client, student, cid, "tell me more about step 4")
    assert detail["intent"] == "app_guide" and detail["content"].startswith("Step 4 of the CareerNova AI workflow")
    assert "**4. Check the extracted details**" in detail["content"] and "step 5" in detail["content"]
    assert endpoints(detail) == ["/resumes"]
    following = ask(client, student, cid, "what next?")
    assert following["intent"] == "app_guide" and "## Your next step" in following["content"]


def test_scope_and_existing_answers_are_unchanged(client, student):  # noqa: F811
    cid = new_conversation(client, student)
    assert ask(client, student, cid, "How do I upload my resume?")["intent"] == "product_help"
    declined = ask(client, student, cid, "who is ronaldo")
    assert declined["intent"] == "unknown" and declined["sources"] == []
    assert ask(client, student, cid, "show my applications")["intent"] == "application_status"
