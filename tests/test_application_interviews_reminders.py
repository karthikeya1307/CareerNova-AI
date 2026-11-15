"""Phase 7: interview rounds (with status consistency) and stored reminders."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from applications_support import (  # noqa: F401 (fixtures)
    add_reminder, add_round, external, history, in_days, internal, now_utc, other, seeded, set_status, student,
)
from backend.models import InterviewSession


def rounds(client, user, aid):
    return client.get(f"/applications/{aid}/interviews", headers=user["headers"]).json()


def app_status(client, user, aid):
    return client.get(f"/applications/{aid}", headers=user["headers"]).json()["status"]


def patch_round(client, user, interview_id, **body):
    return client.patch(f"/applications/interviews/{interview_id}", headers=user["headers"], json=body)


# ------------------------------------------------------------------
# Interview rounds
# ------------------------------------------------------------------

def test_add_round_advances_applied_and_numbers_rounds(client, student):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    first = add_round(client, student, aid, scheduled_at="2026-12-01T10:00:00+05:30", duration_minutes=45,
                      meeting_url="https://meet.example/abc", preparation_notes="Revise SQL joins")
    assert first.status_code == 201
    body = first.json()
    assert body["round_number"] == 1 and body["scheduled_at"] == "2026-12-01T04:30:00Z"
    assert body["status_change"] == {"from_status": "APPLIED", "to_status": "INTERVIEW_SCHEDULED",
                                     "reason": "interview_added"}
    second = add_round(client, student, aid, interview_type="hr", mode="offline", location="Head office").json()
    assert second["round_number"] == 2 and second["status_change"] is None
    assert [r["round_number"] for r in rounds(client, student, aid)] == [1, 2]
    assert history(client, student, aid)["status_history"][-1]["change_type"] == "interview_added"


@pytest.mark.parametrize("start", ["SAVED", "WITHDRAWN"])
def test_rounds_need_a_submitted_application(client, student, start):
    app = external(client, student)
    if start == "WITHDRAWN":
        set_status(client, student, app["application_id"], "WITHDRAWN")
    assert add_round(client, student, app["application_id"]).status_code == 409


@pytest.mark.parametrize("final", ["SELECTED", "REJECTED"])
def test_recording_rounds_never_changes_final_statuses(client, student, final):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    set_status(client, student, aid, final)
    created = add_round(client, student, aid, scheduled_at=in_days(-3), outcome="passed").json()
    assert created["status_change"] is None
    patch_round(client, student, created["interview_id"], outcome="cancelled")
    client.delete(f"/applications/interviews/{created['interview_id']}", headers=student["headers"])
    assert app_status(client, student, aid) == final


def test_cancelling_the_only_round_reverts_the_status(client, student):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    set_status(client, student, aid, "SHORTLISTED")
    rid = add_round(client, student, aid).json()["interview_id"]
    assert app_status(client, student, aid) == "INTERVIEW_SCHEDULED"
    cancelled = patch_round(client, student, rid, outcome="cancelled").json()
    assert cancelled["status_change"] == {"from_status": "INTERVIEW_SCHEDULED", "to_status": "SHORTLISTED",
                                          "reason": "interview_cancelled"}
    assert app_status(client, student, aid) == "SHORTLISTED"
    reopened = patch_round(client, student, rid, outcome="pending").json()
    assert reopened["status_change"]["to_status"] == "INTERVIEW_SCHEDULED"


def test_deleting_the_last_round_reverts_but_not_while_others_remain(client, student):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    r1 = add_round(client, student, aid).json()["interview_id"]
    r2 = add_round(client, student, aid).json()["interview_id"]
    first = client.delete(f"/applications/interviews/{r1}", headers=student["headers"]).json()
    assert first == {"deleted": True, "status_change": None}
    assert app_status(client, student, aid) == "INTERVIEW_SCHEDULED"
    last = client.delete(f"/applications/interviews/{r2}", headers=student["headers"]).json()
    assert last["status_change"]["to_status"] == "APPLIED"
    assert app_status(client, student, aid) == "APPLIED"


def test_rounds_that_took_place_keep_the_interview_status(client, student):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    done = add_round(client, student, aid, scheduled_at=in_days(-2)).json()["interview_id"]
    patch_round(client, student, done, outcome="passed", feedback="Went well")
    upcoming = add_round(client, student, aid).json()["interview_id"]
    result = patch_round(client, student, upcoming, outcome="cancelled").json()
    assert result["status_change"] is None and app_status(client, student, aid) == "INTERVIEW_SCHEDULED"


def test_rescheduling_and_editing_never_change_status(client, student):
    app = external(client, student, status="APPLIED")
    rid = add_round(client, student, app["application_id"]).json()["interview_id"]
    moved = patch_round(client, student, rid, scheduled_at="2026-12-24T15:00:00+05:30", feedback="Panel of 3",
                        interview_type="managerial").json()
    assert moved["scheduled_at"] == "2026-12-24T09:30:00Z" and moved["status_change"] is None
    assert client.get(f"/applications/interviews/{rid}", headers=student["headers"]).json()["feedback"] == "Panel of 3"
    events = [a for a in history(client, student, app["application_id"])["activity"]
              if a["event_type"] == "interview_updated"]
    assert events[-1]["details"]["fields"] == ["feedback", "interview_type", "scheduled_at"]
    assert "Panel of 3" not in str(events)


@pytest.mark.parametrize("body", [
    {"interview_type": "tea", "mode": "online", "scheduled_at": "2026-12-01T10:00:00+05:30"},
    {"interview_type": "hr", "mode": "zoom", "scheduled_at": "2026-12-01T10:00:00+05:30"},
    {"interview_type": "hr", "mode": "online", "scheduled_at": "2026-12-01T10:00:00"},
    {"interview_type": "hr", "mode": "online", "scheduled_at": "2031-12-01T10:00:00+05:30"},
    {"interview_type": "hr", "mode": "online", "scheduled_at": "2026-12-01T10:00:00Z", "duration_minutes": 4},
    {"interview_type": "hr", "mode": "online", "scheduled_at": "2026-12-01T10:00:00Z",
     "meeting_url": "javascript:alert(1)"},
    {"interview_type": "hr", "mode": "online", "scheduled_at": "2026-12-01T10:00:00Z", "outcome": "won"},
])
def test_round_validation(client, student, body):
    app = external(client, student, status="APPLIED")
    response = client.post(f"/applications/{app['application_id']}/interviews", headers=student["headers"],
                           json=body)
    assert response.status_code == 422


def test_round_limit(client, student, monkeypatch):
    from backend.services import application_service as svc
    monkeypatch.setattr(svc, "MAX_ROUNDS", 2)
    app = external(client, student, status="APPLIED")
    add_round(client, student, app["application_id"])
    add_round(client, student, app["application_id"])
    assert add_round(client, student, app["application_id"]).status_code == 409


def test_link_to_phase6_practice_session(client, student, other, seeded):
    app = internal(client, student, status="APPLIED")
    own = InterviewSession(user_id=student["user_id"], internship_id=student["internships"][0], status="completed",
                           mode="practice", title="Practice")
    elsewhere = InterviewSession(user_id=student["user_id"], internship_id=student["internships"][1],
                                 status="completed", mode="practice")
    foreign = InterviewSession(user_id=other["user_id"], status="completed", mode="practice")
    seeded.add_all([own, elsewhere, foreign])
    seeded.commit()
    linked = add_round(client, student, app["application_id"], interview_session_id=own.session_id).json()
    assert linked["interview_session_id"] == own.session_id
    assert add_round(client, student, app["application_id"],
                     interview_session_id=foreign.session_id).status_code == 404
    assert add_round(client, student, app["application_id"],
                     interview_session_id=elsewhere.session_id).status_code == 422
    detail = client.get(f"/applications/{app['application_id']}", headers=student["headers"]).json()
    assert [s["session_id"] for s in detail["related"]["practice_sessions"]] == [own.session_id]

    seeded.delete(seeded.get(InterviewSession, own.session_id))      # deleting the Phase 6 session keeps the round
    seeded.commit()
    assert client.get(f"/applications/interviews/{linked['interview_id']}",
                      headers=student["headers"]).json()["interview_session_id"] is None


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------

def test_reminder_lifecycle(client, student):
    h = student["headers"]
    app = external(client, student)
    created = add_reminder(client, student, app["application_id"], remind_at="2026-12-01T09:00:00+05:30",
                           description="Ask about the timeline").json()
    assert created["remind_at"] == "2026-12-01T03:30:00Z" and created["delivery"] == "not_sent"
    assert created["is_completed"] is False and created["overdue"] is False
    rid = created["reminder_id"]

    done = client.patch(f"/applications/reminders/{rid}", headers=h, json={"is_completed": True}).json()
    assert done["is_completed"] is True and done["completed_at"].endswith("Z")
    reopened = client.patch(f"/applications/reminders/{rid}", headers=h, json={"is_completed": False}).json()
    assert reopened["completed_at"] is None
    edited = client.patch(f"/applications/reminders/{rid}", headers=h, json={"title": "Call HR"}).json()
    assert edited["title"] == "Call HR"
    events = [a["event_type"] for a in history(client, student, app["application_id"])["activity"]]
    assert {"reminder_created", "reminder_completed", "reminder_reopened", "reminder_updated"} <= set(events)
    assert "Ask about the timeline" not in str(history(client, student, app["application_id"]))

    assert client.delete(f"/applications/reminders/{rid}", headers=h).status_code == 204
    assert client.get("/applications/reminders?status=all", headers=h).json()["total"] == 0


def test_reminder_validation(client, student):
    app = external(client, student)
    aid = app["application_id"]
    assert add_reminder(client, student, aid, remind_at="2026-12-01T09:00:00").status_code == 422
    assert add_reminder(client, student, aid, remind_at=in_days(-1)).status_code == 422
    assert add_reminder(client, student, aid, remind_at=in_days(800)).status_code == 422
    assert add_reminder(client, student, aid, title="").status_code == 422
    assert add_reminder(client, student, aid, description="x" * 2001).status_code == 422
    rid = add_reminder(client, student, aid).json()["reminder_id"]
    assert client.patch(f"/applications/reminders/{rid}", headers=student["headers"],
                        json={"is_completed": None}).status_code == 422


def test_reminder_filters(client, student, seeded):
    from backend.models import ApplicationReminder
    h = student["headers"]
    a = external(client, student)
    b = external(client, student, title="Other role")
    r1 = add_reminder(client, student, a["application_id"], remind_at=in_days(1)).json()["reminder_id"]
    r2 = add_reminder(client, student, b["application_id"], remind_at=in_days(10)).json()["reminder_id"]
    r3 = add_reminder(client, student, b["application_id"], remind_at=in_days(5)).json()["reminder_id"]
    client.patch(f"/applications/reminders/{r3}", headers=h, json={"is_completed": True})
    overdue = seeded.get(ApplicationReminder, r1)            # make one overdue (cannot be created in the past)
    overdue.remind_at = now_utc() - timedelta(hours=2)
    seeded.commit()

    def ids(query):
        response = client.get(f"/applications/reminders{query}", headers=h)
        assert response.status_code == 200, response.text
        return [i["reminder_id"] for i in response.json()["items"]]

    assert ids("") == [r1, r2]                                   # pending by default, soonest first
    assert ids("?status=completed") == [r3]
    assert ids("?status=all") == [r1, r3, r2]
    assert ids(f"?application_id={b['application_id']}&status=all") == [r3, r2]
    assert ids("?overdue=true") == [r1]
    window = (now_utc() + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    assert ids(f"?status=all&due_from={window}") == [r2]
    assert client.get("/applications/reminders?due_from=2026-12-01T00:00:00", headers=h).status_code == 422
    item = client.get("/applications/reminders", headers=h).json()["items"][0]
    assert item["overdue"] is True and item["company_name"] == "Acme Robotics"
