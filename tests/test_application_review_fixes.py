"""Phase 7 review fixes (M1, M2, minor 1-7) and the missing tests identified in the review."""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from applications_support import (  # noqa: F401 (fixtures)
    add_reminder, add_round, create, external, in_days, internal, now_utc, other, seeded, set_status, student,
)
from backend import database
from backend.models import Application, ApplicationActivity, Internship
from backend.services import application_service as svc


def status_of(client, user, aid):
    return client.get(f"/applications/{aid}", headers=user["headers"]).json()["status"]


# ------------------------------------------------------------------
# M1: creating a round never moves the status back
# ------------------------------------------------------------------

def test_recording_an_already_cancelled_round_keeps_a_manual_interview_status(client, student):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    set_status(client, student, aid, "SHORTLISTED")
    set_status(client, student, aid, "INTERVIEW_SCHEDULED")
    created = add_round(client, student, aid, outcome="cancelled").json()
    assert created["status_change"] is None
    assert status_of(client, student, aid) == "INTERVIEW_SCHEDULED"


def test_recording_a_cancelled_round_does_not_advance_either(client, student):
    app = external(client, student, status="APPLIED")
    created = add_round(client, student, app["application_id"], outcome="cancelled").json()
    assert created["status_change"] is None and status_of(client, student, app["application_id"]) == "APPLIED"


# ------------------------------------------------------------------
# M2: success rate only counts submitted applications
# ------------------------------------------------------------------

def test_success_rate_never_exceeds_100_percent(client, student, seeded):
    submitted = external(client, student, title="Submitted", status="APPLIED")
    for title in ("Legacy 1", "Legacy 2"):
        legacy = external(client, student, title=title)
        seeded.execute(text("UPDATE applications SET status = 'SELECTED', applied_at = NULL "
                            "WHERE application_id = :i"), {"i": legacy["application_id"]})
    seeded.commit()
    body = client.get("/applications/dashboard", headers=student["headers"]).json()
    assert body["selected"] == 2 and body["submitted_applications"] == 1
    assert body["success_rate"] == 0.0                     # neither selected application was submitted
    set_status(client, student, submitted["application_id"], "SELECTED")
    body = client.get("/applications/dashboard", headers=student["headers"]).json()
    assert body["success_rate"] == 100.0 and "submitted" in body["formulas"]["success_rate"]


# ------------------------------------------------------------------
# Minor 1: warning when pending rounds remain outside the interview stage
# ------------------------------------------------------------------

def test_correction_that_leaves_pending_rounds_warns(client, student):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    add_round(client, student, aid)
    undo = set_status(client, student, aid, "APPLIED", correction=True).json()
    assert undo["to_status"] == "APPLIED"
    assert undo["warnings"] and "1 pending interview round" in undo["warnings"][0]
    plain = external(client, student, title="No rounds")
    assert set_status(client, student, plain["application_id"], "APPLIED").json()["warnings"] == []


# ------------------------------------------------------------------
# Minor 2: revert target walks back past corrections
# ------------------------------------------------------------------

def test_cancel_after_correction_returns_to_shortlisted(client, student):
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    set_status(client, student, aid, "SHORTLISTED")
    rid = add_round(client, student, aid).json()["interview_id"]
    set_status(client, student, aid, "SELECTED")
    set_status(client, student, aid, "INTERVIEW_SCHEDULED", correction=True)
    result = client.patch(f"/applications/interviews/{rid}", headers=student["headers"],
                          json={"outcome": "cancelled"}).json()
    assert result["status_change"]["to_status"] == "SHORTLISTED"


# ------------------------------------------------------------------
# Minor 3: deadline_passed is independent of is_active
# ------------------------------------------------------------------

def test_deadline_passed_for_inactive_internship(client, student, seeded):
    h, iid = student["headers"], student["internships"][0]
    client.post(f"/applications/bookmarks/{iid}", headers=h)
    app = internal(client, student)
    internship = seeded.get(Internship, iid)
    internship.is_active = False
    internship.deadline = now_utc() - timedelta(days=1)
    seeded.commit()
    detail = client.get(f"/applications/{app['application_id']}", headers=h).json()
    assert detail["internship_active"] is False and detail["deadline_passed"] is True
    summary = client.get("/applications/bookmarks", headers=h).json()["items"][0]["internship"]
    assert summary["is_active"] is False and summary["deadline_passed"] is True


# ------------------------------------------------------------------
# Minor 4: the locked read refreshes a stale object
# ------------------------------------------------------------------

def test_locked_read_sees_changes_made_by_another_session(client, student):
    app = external(client, student)
    aid, uid = app["application_id"], student["user_id"]
    stale = database.SessionLocal()
    fresh = database.SessionLocal()
    try:
        assert stale.get(Application, aid).status == "SAVED"           # held in the identity map
        svc.change_status(fresh, uid, aid, "APPLIED")                   # committed elsewhere
        # Without populate_existing the stale SAVED would make SAVED -> SHORTLISTED look invalid.
        _, changed, previous = svc.change_status(stale, uid, aid, "SHORTLISTED")
        assert changed and previous == "APPLIED"
    finally:
        stale.close()
        fresh.close()


# ------------------------------------------------------------------
# Minor 5: concurrent reminder completion is recorded once
# ------------------------------------------------------------------

def test_concurrent_reminder_completion_records_one_event(client, student, seeded):
    app = external(client, student)
    rid = add_reminder(client, student, app["application_id"]).json()["reminder_id"]
    barrier, errors = threading.Barrier(2), []

    def complete():
        db = database.SessionLocal()
        try:
            barrier.wait()
            svc.update_reminder(db, student["user_id"], rid, {"is_completed": True}, {"is_completed"})
        except Exception as exc:          # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=complete) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert seeded.scalar(select(func.count()).select_from(ApplicationActivity).where(
        ApplicationActivity.event_type == "reminder_completed")) == 1


# ------------------------------------------------------------------
# Minor 6: database errors are classified
# ------------------------------------------------------------------

def test_concurrent_duplicate_is_still_reported_as_duplicate(client, student, monkeypatch):
    internal(client, student)
    monkeypatch.setattr(svc, "_conflicting", lambda *args, **kwargs: None)     # simulate losing a race
    response = create(client, student, internship_id=student["internships"][0])
    assert response.status_code == 409 and "already have" in response.json()["detail"]


def test_other_database_errors_get_a_generic_message(client, student, monkeypatch):
    monkeypatch.setattr(svc, "check_documents", lambda *args, **kwargs: None)  # document vanished meanwhile
    response = create(client, student, company_name="Acme", title="Intern", resume_document_id=999999)
    assert response.status_code == 409 and response.json()["detail"] == svc.GENERIC_CONFLICT


def test_bookmark_saved_concurrently_returns_the_existing_one(client, student, monkeypatch):
    iid = student["internships"][0]
    first = client.post(f"/applications/bookmarks/{iid}", headers=student["headers"]).json()
    monkeypatch.setattr(svc, "get_bookmark", lambda *args, **kwargs: None)     # the other request won
    again = client.post(f"/applications/bookmarks/{iid}", headers=student["headers"])
    assert again.status_code == 200 and again.json()["bookmark_id"] == first["bookmark_id"]


# ------------------------------------------------------------------
# Minor 7: query validation and batched bookmark lookups
# ------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "/applications?applied_from=2026-11-10T00:00:00Z&applied_to=2026-11-01T00:00:00Z",
    "/applications?created_from=2026-11-10T00:00:00Z&created_to=2026-11-01T00:00:00Z",
    "/applications/reminders?due_from=2026-11-10T00:00:00Z&due_to=2026-11-01T00:00:00Z",
    "/applications?q=%20%20%20", "/applications?company=%20", "/applications?domain=%20",
])
def test_invalid_query_values(client, student, query):
    assert client.get(query, headers=student["headers"]).status_code == 422


def test_bookmark_list_shows_each_application(client, student):
    h = student["headers"]
    ids = student["internships"][:3]
    for iid in ids:
        client.post(f"/applications/bookmarks/{iid}", headers=h)
    a0 = internal(client, student, 0)
    a2 = internal(client, student, 2)
    items = {i["internship_id"]: i["application_id"]
             for i in client.get("/applications/bookmarks", headers=h).json()["items"]}
    assert items == {ids[0]: a0["application_id"], ids[1]: None, ids[2]: a2["application_id"]}


# ------------------------------------------------------------------
# Missing tests: caps, trash isolation, restore conflicts, trashed children
# ------------------------------------------------------------------

def test_per_student_caps(client, student, monkeypatch):
    monkeypatch.setattr(svc, "MAX_APPLICATIONS", 2)
    monkeypatch.setattr(svc, "MAX_BOOKMARKS", 1)
    monkeypatch.setattr(svc, "MAX_REMINDERS", 1)
    h = student["headers"]
    a = external(client, student, title="One")
    external(client, student, title="Two")
    assert create(client, student, company_name="Acme", title="Three").status_code == 409
    assert client.post(f"/applications/bookmarks/{student['internships'][0]}", headers=h).status_code == 201
    assert client.post(f"/applications/bookmarks/{student['internships'][0]}", headers=h).status_code == 200
    assert client.post(f"/applications/bookmarks/{student['internships'][1]}", headers=h).status_code == 409
    assert add_reminder(client, student, a["application_id"]).status_code == 201
    assert add_reminder(client, student, a["application_id"]).status_code == 409


def test_trash_is_private(client, student, other):
    app = external(client, student)
    client.delete(f"/applications/{app['application_id']}?confirm=true", headers=student["headers"])
    assert client.get("/applications/trash", headers=other["headers"]).json()["total"] == 0
    assert client.get("/applications/trash", headers=student["headers"]).json()["total"] == 1


def test_restore_conflicts_with_same_url_or_reference(client, student):
    h = student["headers"]
    by_url = external(client, student, application_url="https://jobs.acme.example/7")
    client.delete(f"/applications/{by_url['application_id']}?confirm=true", headers=h)
    newer = external(client, student, application_url="https://jobs.acme.example/7/?utm_source=mail")
    clash = client.post(f"/applications/{by_url['application_id']}/restore", headers=h)
    assert clash.status_code == 409 and clash.json()["detail"]["application_id"] == newer["application_id"]

    by_ref = external(client, student, title="Ref", external_reference="R-9")
    client.delete(f"/applications/{by_ref['application_id']}?confirm=true", headers=h)
    external(client, student, title="Ref again", external_reference="R-9")
    assert client.post(f"/applications/{by_ref['application_id']}/restore", headers=h).status_code == 409


def test_children_of_trashed_applications_are_hidden_until_restored(client, student):
    h = student["headers"]
    app = external(client, student, status="APPLIED")
    aid = app["application_id"]
    iid = add_round(client, student, aid).json()["interview_id"]
    rid = add_reminder(client, student, aid).json()["reminder_id"]
    client.delete(f"/applications/{aid}?confirm=true", headers=h)
    for method, path, body in [
        ("GET", f"/applications/interviews/{iid}", None), ("PATCH", f"/applications/interviews/{iid}",
                                                           {"feedback": "x"}),
        ("DELETE", f"/applications/interviews/{iid}", None),
        ("PATCH", f"/applications/reminders/{rid}", {"is_completed": True}),
        ("DELETE", f"/applications/reminders/{rid}", None),
        ("GET", f"/applications/{aid}/history", None), ("GET", f"/applications/{aid}/interviews", None),
        ("POST", f"/applications/{aid}/reminders", {"title": "x", "remind_at": in_days(1)}),
    ]:
        assert client.request(method, path, headers=h, json=body).status_code == 404, (method, path)
    client.post(f"/applications/{aid}/restore", headers=h)
    assert client.get(f"/applications/interviews/{iid}", headers=h).status_code == 200
    assert client.patch(f"/applications/reminders/{rid}", headers=h, json={"is_completed": True}).status_code == 200
