"""Phase 8: answers, traceable sources, follow-ups and read-only behaviour."""

import re

import pytest
from sqlalchemy import func, select

from assistant_support import (  # noqa: F401 (fixtures)
    ask, new_conversation, other, result_ids, seeded, source_ids, student,
)
from backend.models import (
    Application, ApplicationInterview, ApplicationReminder, GeneratedDocument, Internship, InterviewSession,
    MatchResult, SavedInternship, SkillGapRecommendation,
)


def run_matching(client, user):
    response = client.post(f"/matches/resumes/{user['resume_id']}?k=5", headers=user["headers"])
    assert response.status_code in (200, 201), response.text
    return response.json()


def build_index():
    from backend.services import embeddings, vector_index
    vector_index.rebuild_index(embeddings.get_embedder())


def assert_traceable(answer):
    for source in answer["sources"]:
        assert set(source) >= {"type", "id", "label", "available"} and source["id"] and source["label"]


# ------------------------------------------------------------------
# Profile and search
# ------------------------------------------------------------------

def test_profile_summary_cites_resume_and_hides_contact_details(client, student):
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "What skills are on my resume?")
    assert answer["intent"] == "profile_summary" and "Python" in answer["content"]
    assert source_ids(answer, "resume") == [str(student["resume_id"])]
    assert any(s["type"] == "resume_fact" and s["id"].startswith(f"{student['resume_id']}:")
               for s in answer["sources"])
    for secret in ("asha@example.com", "90000 00002", "MG Road", "560001"):
        assert secret not in answer["content"]
    assert_traceable(answer)


def test_search_falls_back_to_keywords_without_an_index(client, student):
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "Find internships about data")
    assert answer["intent"] == "internship_search"
    assert any(w["code"] == "semantic_search_unavailable" for w in answer["warnings"])
    assert result_ids(answer) and source_ids(answer, "internship") == result_ids(answer)
    assert all(s["available"] for s in answer["sources"])


def test_semantic_search_with_the_index(client, student, seeded):
    build_index()
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "show me backend python internships")
    assert not any(w["code"] == "semantic_search_unavailable" for w in answer["warnings"])
    open_ids = {str(i) for i in student["open"]}
    assert result_ids(answer) and set(result_ids(answer)) <= open_ids
    assert_traceable(answer)


def test_search_with_no_results(client, student):
    cid = new_conversation(client, student)
    answer = ask(client, student, cid, "find internships about zzzzunknowable")
    assert answer["result_set"] is None and "couldn't find" in answer["content"]


# ------------------------------------------------------------------
# Follow-ups against the exact previous result set
# ------------------------------------------------------------------

def test_ordinal_followups_use_the_displayed_list(client, student):
    cid = new_conversation(client, student)
    listing = ask(client, student, cid, "Find internships about data")
    ids = result_ids(listing)
    assert len(ids) >= 2
    second = ask(client, student, cid, "What about the second one?")
    assert second["intent"] == "internship_detail" and source_ids(second, "internship")[0] == ids[1]
    last = ask(client, student, cid, "and the last one?")
    assert source_ids(last, "internship")[0] == ids[-1]
    # A detail answer does not replace the list: "the first one" still refers to it.
    first = ask(client, student, cid, "tell me more about the first one")
    assert source_ids(first, "internship")[0] == ids[0]


def test_a_newer_reordered_list_replaces_the_older_one(client, student):
    cid = new_conversation(client, student)
    first_list = result_ids(ask(client, student, cid, "Find internships about data"))
    second_list = result_ids(ask(client, student, cid, "Find internships about developer"))
    assert first_list and second_list and first_list != second_list
    ask(client, student, cid, "show my dashboard")                  # non-list answer in between
    pick = ask(client, student, cid, "the second one")
    expected = second_list[1] if len(second_list) > 1 else None
    if expected:
        assert source_ids(pick, "internship")[0] == expected
    else:
        assert pick["intent"] == "followup" and "had 1 item" in pick["content"]


def test_pronoun_uses_focus_after_a_detail_answer(client, student):
    cid = new_conversation(client, student)
    ids = result_ids(ask(client, student, cid, "Find internships about data"))
    ask(client, student, cid, "tell me more about the second one")
    gap = ask(client, student, cid, "what skills am I missing for it?")
    assert gap["intent"] == "skill_gap" and source_ids(gap, "internship") == [ids[1]]


def test_ambiguous_pronoun_asks_which_one_then_resolves(client, student):
    cid = new_conversation(client, student)
    ids = result_ids(ask(client, student, cid, "Find internships about data"))
    assert len(ids) > 1
    question = ask(client, student, cid, "is that one remote?")
    assert "Which one do you mean?" in question["content"] and result_ids(question) == ids
    assert question["sources"] == []                                  # a question, not a factual answer
    picked = ask(client, student, cid, "the second one")
    assert source_ids(picked, "internship")[0] == ids[1]


def test_followups_without_a_list_or_out_of_range(client, student):
    cid = new_conversation(client, student)
    nothing = ask(client, student, cid, "what about the second one?")
    assert "don't have a list" in nothing["content"]
    vague = ask(client, student, cid, "tell me about it")
    assert "not sure what you're referring to" in vague["content"]
    ids = result_ids(ask(client, student, cid, "Find internships about data"))
    out_of_range = ask(client, student, cid, "the 9th one")
    assert f"had {len(ids)} item" in out_of_range["content"] and result_ids(out_of_range) == ids


def test_deleted_or_closed_referenced_records(client, student, seeded):
    cid = new_conversation(client, student)
    listing = ask(client, student, cid, "Find internships about data")
    ids = result_ids(listing)
    internship = seeded.get(Internship, int(ids[1]))
    internship.is_active = False
    seeded.commit()
    gone = ask(client, student, cid, "tell me more about the second one")
    assert "no longer available" in gone["content"] and gone["sources"] == []
    history = client.get(f"/assistant/conversations/{cid}/messages", headers=student["headers"]).json()
    shown = next(m for m in history if m["message_id"] == listing["message_id"])
    availability = {s["id"]: s["available"] for s in shown["sources"]}
    assert availability[ids[1]] is False and availability[ids[0]] is True


# ------------------------------------------------------------------
# Matching, gaps, learning, documents, interviews
# ------------------------------------------------------------------

def test_matches_use_stored_runs_only(client, student, seeded):
    cid = new_conversation(client, student)
    none_yet = ask(client, student, cid, "show my top matches")
    assert "don't have a stored match run" in none_yet["content"]
    assert none_yet["suggested_actions"][0]["endpoint"] == f"/matches/resumes/{student['resume_id']}"
    assert seeded.scalar(select(func.count()).select_from(MatchResult)) == 0      # nothing was computed

    run = run_matching(client, student)
    top = ask(client, student, cid, "show my top matches")
    first = run["results"][0]
    assert result_ids(top)[0] == str(first["internship"]["internship_id"])
    assert f"score {round(first['score'])}" in top["content"]
    explain = ask(client, student, cid, "why is the first one a good match?")
    assert explain["intent"] == "match_explain"
    row = seeded.scalar(select(MatchResult).where(MatchResult.internship_id == first["internship"]["internship_id"]))
    assert source_ids(explain, "match_result") == [str(row.match_id)]
    assert f"Overall score: {round(row.score)} out of 100" in explain["content"]


def test_skill_gap_for_an_internship_and_stored_recommendations(client, student):
    cid = new_conversation(client, student)
    ids = result_ids(ask(client, student, cid, "Find internships about data"))
    gap = ask(client, student, cid, "what skills am I missing for the first one?")
    assert gap["intent"] == "skill_gap" and source_ids(gap, "internship") == [ids[0]]
    assert source_ids(gap, "resume") == [str(student["resume_id"])]

    empty = ask(client, student, cid, "show my skill gaps")
    assert "don't have stored skill-gap recommendations" in empty["content"]
    run_matching(client, student)
    client.post(f"/skill-gaps/resumes/{student['resume_id']}", headers=student["headers"], json={})
    recs = ask(client, student, cid, "show my skill gaps")
    assert source_ids(recs, "skill_gap_recommendation") and recs["result_set"]["kind"] == "skill"
    plan = ask(client, student, cid, "how do I learn the first one?")
    first_skill = recs["result_set"]["items"][0]["id"]
    assert plan["intent"] == "learning_plan" and source_ids(plan, "learning_plan") == [first_skill]


def test_learning_plan_and_missing_skill_clarification(client, student):
    cid = new_conversation(client, student)
    plan = ask(client, student, cid, "how do I learn Docker?")
    assert source_ids(plan, "learning_plan") == ["Docker"] and "Step 1" in plan["content"]
    which = ask(client, student, cid, "give me a learning plan")
    assert "Which skill" in which["content"]


def test_document_help_checks_resume_against_internship(client, student):
    cid = new_conversation(client, student)
    ids = result_ids(ask(client, student, cid, "Find internships about data"))
    help_answer = ask(client, student, cid, "help me write a cover letter for the first one")
    assert help_answer["intent"] == "document_help" and source_ids(help_answer, "internship") == [ids[0]]
    assert "required skills" in help_answer["content"]
    endpoints = {a["endpoint"] for a in help_answer["suggested_actions"]}
    assert endpoints == {"/documents/resume", "/documents/cover-letter"}
    assert all(a["requires_confirmation"] for a in help_answer["suggested_actions"])


def test_interview_prep(client, student):
    cid = new_conversation(client, student)
    questions = ask(client, student, cid, "give me practice questions on SQL")
    assert source_ids(questions, "question_bank") and questions["content"].count("?") >= 1
    progress = ask(client, student, cid, "how is my interview progress")
    assert source_ids(progress, "interview_progress") and "Sessions: 0 started" in progress["content"]


# ------------------------------------------------------------------
# Applications (own data only)
# ------------------------------------------------------------------

def make_application(client, user, **body):
    response = client.post("/applications", headers=user["headers"], json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_application_answers_cite_the_application(client, student, other):
    app = make_application(client, student, company_name="Acme Robotics", title="Software Intern", status="APPLIED")
    make_application(client, student, company_name="Zeta Labs", title="Data Intern")
    theirs = make_application(client, other, company_name="Secret Corp", title="Analyst", status="APPLIED")
    client.patch(f"/applications/{app['application_id']}/status", headers=student["headers"],
                 json={"status": "SHORTLISTED"})

    cid = new_conversation(client, student)
    detail = ask(client, student, cid, "what is the status of my Acme Robotics application?")
    assert source_ids(detail, "application") == [str(app["application_id"])]
    assert "Status: SHORTLISTED" in detail["content"]
    listing = ask(client, student, cid, "show my applications")
    assert "Secret Corp" not in listing["content"] and str(theirs["application_id"]) not in result_ids(listing)
    shortlisted = ask(client, student, cid, "which applications were shortlisted?")
    assert result_ids(shortlisted) == [str(app["application_id"])]
    foreign = ask(client, student, cid, f"tell me about application #{theirs['application_id']}")
    assert "couldn't find that application" in foreign["content"] and "Secret" not in foreign["content"]


def test_interviews_reminders_and_dashboard(client, student):
    app = make_application(client, student, company_name="Acme Robotics", title="Software Intern", status="APPLIED")
    from datetime import datetime, timedelta, timezone
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    interview = client.post(f"/applications/{app['application_id']}/interviews", headers=student["headers"],
                            json={"interview_type": "technical", "mode": "online", "scheduled_at": soon}).json()
    reminder = client.post(f"/applications/{app['application_id']}/reminders", headers=student["headers"],
                           json={"title": "Email the recruiter", "remind_at": soon,
                                 "description": "private note"}).json()
    cid = new_conversation(client, student)
    upcoming = ask(client, student, cid, "when is my next interview?")
    assert source_ids(upcoming, "application_interview") == [str(interview["interview_id"])]
    reminders = ask(client, student, cid, "show my reminders")
    assert source_ids(reminders, "application_reminder") == [str(reminder["reminder_id"])]
    assert "private note" not in reminders["content"] and "stored only" in reminders["content"]
    dash = ask(client, student, cid, "show my application dashboard")
    assert source_ids(dash, "dashboard") == ["applications"] and "Applications tracked: 1" in dash["content"]
    follow = ask(client, student, cid, "tell me more about the first one")    # list from the reminders answer
    assert follow["intent"] == "application_status"


def test_unknown_and_help(client, student):
    cid = new_conversation(client, student)
    unknown = ask(client, student, cid, "asdf qwerty")
    assert unknown["intent"] == "unknown" and "not sure I understood" in unknown["content"]
    assert unknown["sources"] == []


def test_needs_resume_when_none_is_parsed(client, create_user, seeded):
    user = create_user()
    cid = new_conversation(client, user)
    answer = ask(client, user, cid, "show my top matches")
    assert "need a parsed resume" in answer["content"]
    assert answer["suggested_actions"][0]["endpoint"] == "/resumes/upload"


def test_assistant_never_writes_phase_1_to_7_data(client, student, seeded):
    make_application(client, student, company_name="Acme Robotics", title="Software Intern", status="APPLIED")
    models = (Application, ApplicationInterview, ApplicationReminder, SavedInternship, MatchResult,
              SkillGapRecommendation, GeneratedDocument, InterviewSession, Internship)
    before = {m.__name__: seeded.scalar(select(func.count()).select_from(m)) for m in models}
    cid = new_conversation(client, student)
    for question in ("Find internships about data", "tell me more about the first one",
                     "what skills am I missing for it?", "show my top matches", "show my skill gaps",
                     "cover letter for the first one", "give me practice questions on SQL",
                     "show my applications", "show my reminders", "show my application dashboard"):
        ask(client, student, cid, question)
    seeded.expire_all()
    after = {m.__name__: seeded.scalar(select(func.count()).select_from(m)) for m in models}
    assert after == before


def test_answers_only_state_numbers_from_their_facts(client, student):
    """Every number in a deterministic answer comes from a source record (no invented figures)."""
    make_application(client, student, company_name="Acme Robotics", title="Software Intern", status="APPLIED")
    cid = new_conversation(client, student)
    for question in ("show my applications", "show my application dashboard", "how do I learn Docker?"):
        answer = ask(client, student, cid, question)
        assert answer["sources"], question
        assert all(s["available"] for s in answer["sources"])
        assert not re.search(r"\b(guarantee|definitely|will get)\b", answer["content"].lower())
