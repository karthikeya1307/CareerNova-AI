"""Phase 7: dashboard statistics (own data only, empty-safe, documented formulas)."""

from datetime import timedelta

from sqlalchemy import select

from applications_support import (  # noqa: F401 (fixtures)
    add_reminder, add_round, external, in_days, internal, now_utc, other, seeded, set_status, student,
)
from backend.models import ApplicationReminder, MatchResult


def dashboard(client, user):
    response = client.get("/applications/dashboard", headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_dashboard(client, student):
    body = dashboard(client, student)
    assert body["total_applications"] == 0 and body["saved_internships"] == 0
    assert set(body["by_status"]) == {"SAVED", "APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED",
                                      "REJECTED", "WITHDRAWN"}
    assert all(v == 0 for v in body["by_status"].values())
    assert body["success_rate"] is None and body["decision_rate"] is None and body["interview_rate"] is None
    assert body["next_interviews"] == [] and body["recent_activity"] == []
    assert body["generated_at"].endswith("Z") and "SELECTED" in body["formulas"]["success_rate"]


def test_dashboard_counts_and_formulas(client, student, seeded):
    h = student["headers"]
    client.post(f"/applications/bookmarks/{student['internships'][0]}", headers=h)
    client.post(f"/applications/bookmarks/{student['internships'][1]}", headers=h)

    selected = internal(client, student, 0, status="APPLIED")
    add_round(client, student, selected["application_id"], scheduled_at=in_days(-5), outcome="passed")
    set_status(client, student, selected["application_id"], "SELECTED")

    rejected = external(client, student, title="Rejected role", status="APPLIED")
    set_status(client, student, rejected["application_id"], "REJECTED")

    interviewing = external(client, student, title="Interviewing", status="APPLIED")
    add_round(client, student, interviewing["application_id"], scheduled_at=in_days(2))
    cancelled = add_round(client, student, interviewing["application_id"], scheduled_at=in_days(4)).json()
    client.patch(f"/applications/interviews/{cancelled['interview_id']}", headers=h, json={"outcome": "cancelled"})

    external(client, student, title="Just saved")
    withdrawn_early = external(client, student, title="Withdrawn early")
    set_status(client, student, withdrawn_early["application_id"], "WITHDRAWN")

    r1 = add_reminder(client, student, interviewing["application_id"]).json()["reminder_id"]
    r2 = add_reminder(client, student, interviewing["application_id"]).json()["reminder_id"]
    add_reminder(client, student, rejected["application_id"])
    client.patch(f"/applications/reminders/{r2}", headers=h, json={"is_completed": True})
    seeded.get(ApplicationReminder, r1).remind_at = now_utc() - timedelta(hours=1)
    seeded.commit()

    trashed = external(client, student, title="Trashed", status="APPLIED")       # excluded everywhere
    set_status(client, student, trashed["application_id"], "SELECTED")
    client.delete(f"/applications/{trashed['application_id']}?confirm=true", headers=h)

    body = dashboard(client, student)
    assert body["saved_internships"] == 2
    assert body["total_applications"] == 5
    assert body["by_status"] == {"SAVED": 1, "APPLIED": 0, "SHORTLISTED": 0, "INTERVIEW_SCHEDULED": 1,
                                 "SELECTED": 1, "REJECTED": 1, "WITHDRAWN": 1}
    assert body["submitted_applications"] == 3          # selected, rejected, interviewing (withdrawn early never applied)
    assert body["selected"] == 1 and body["rejected"] == 1
    assert body["interviews_scheduled"] == 2            # cancelled rounds excluded
    assert body["upcoming_interviews"] == 1 and body["next_interviews"][0]["title"] == "Interviewing"
    assert body["next_interviews"][0]["scheduled_at"].endswith("Z")
    assert (body["pending_reminders"], body["overdue_reminders"], body["completed_reminders"]) == (2, 1, 1)
    assert body["success_rate"] == round(100 * 1 / 3, 1)
    assert body["decision_rate"] == 50.0
    assert body["interview_rate"] == round(100 * 2 / 3, 1)
    assert len(body["recent_activity"]) == 10
    assert all(a["title"] != "Trashed" for a in body["recent_activity"])


def test_dashboard_only_counts_own_records(client, student, other):
    external(client, student, status="APPLIED")
    client.post(f"/applications/bookmarks/{student['internships'][0]}", headers=student["headers"])
    body = dashboard(client, other)
    assert body["total_applications"] == 0 and body["saved_internships"] == 0 and body["recent_activity"] == []


def test_earlier_phases_are_untouched(client, student, seeded):
    """Phase 7 reads Phase 3/5/6 data but never changes it."""
    h = student["headers"]
    before = seeded.scalars(select(MatchResult)).all()
    app = internal(client, student, status="APPLIED")
    add_round(client, student, app["application_id"])
    set_status(client, student, app["application_id"], "SELECTED")
    assert seeded.scalars(select(MatchResult)).all() == before
    assert client.get("/interviews/sessions", headers=h).json() == []
    assert client.get("/documents", headers=h).status_code == 200
