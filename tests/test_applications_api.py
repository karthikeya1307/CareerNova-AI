"""Phase 7: application CRUD, validation, duplicates, trash, filters, ownership and time zones."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from applications_support import (  # noqa: F401 (fixtures)
    IST, add_reminder, add_round, create, external, in_days, internal, now_utc, other, seeded, set_status, student,
)
from backend.models import (
    Application, ApplicationActivity, ApplicationInterview, ApplicationReminder, ApplicationStatusHistory,
    GeneratedDocument, Internship, User,
)


# ------------------------------------------------------------------
# Authentication and ownership
# ------------------------------------------------------------------

ENDPOINTS = [
    ("GET", "/applications/dashboard"), ("GET", "/applications/bookmarks"),
    ("POST", "/applications/bookmarks/1"), ("GET", "/applications/bookmarks/1"),
    ("DELETE", "/applications/bookmarks/1"), ("GET", "/applications/reminders"),
    ("PATCH", "/applications/reminders/1"), ("DELETE", "/applications/reminders/1"),
    ("GET", "/applications/interviews/1"), ("PATCH", "/applications/interviews/1"),
    ("DELETE", "/applications/interviews/1"), ("GET", "/applications/trash"), ("POST", "/applications"),
    ("GET", "/applications"), ("GET", "/applications/1"), ("PATCH", "/applications/1"),
    ("DELETE", "/applications/1"), ("POST", "/applications/1/restore"), ("DELETE", "/applications/1/permanent"),
    ("PATCH", "/applications/1/status"), ("GET", "/applications/1/history"),
    ("POST", "/applications/1/interviews"), ("GET", "/applications/1/interviews"),
    ("POST", "/applications/1/reminders"),
]


@pytest.mark.parametrize("method, path", ENDPOINTS)
def test_login_required(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_other_students_records_are_invisible(client, student, other):
    app = internal(client, student, status="APPLIED")
    rid = add_reminder(client, student, app["application_id"]).json()["reminder_id"]
    iid = add_round(client, student, app["application_id"]).json()["interview_id"]
    aid, h = app["application_id"], other["headers"]
    for method, path, body in [
        ("GET", f"/applications/{aid}", None), ("PATCH", f"/applications/{aid}", {"notes": "x"}),
        ("DELETE", f"/applications/{aid}?confirm=true", None), ("POST", f"/applications/{aid}/restore", None),
        ("DELETE", f"/applications/{aid}/permanent?confirm=true", None),
        ("PATCH", f"/applications/{aid}/status", {"status": "WITHDRAWN"}),
        ("GET", f"/applications/{aid}/history", None), ("GET", f"/applications/{aid}/interviews", None),
        ("POST", f"/applications/{aid}/interviews", {"interview_type": "hr", "mode": "online",
                                                     "scheduled_at": in_days(1)}),
        ("POST", f"/applications/{aid}/reminders", {"title": "x", "remind_at": in_days(1)}),
        ("GET", f"/applications/interviews/{iid}", None), ("PATCH", f"/applications/interviews/{iid}",
                                                           {"feedback": "x"}),
        ("DELETE", f"/applications/interviews/{iid}", None),
        ("PATCH", f"/applications/reminders/{rid}", {"is_completed": True}),
        ("DELETE", f"/applications/reminders/{rid}", None),
    ]:
        assert client.request(method, path, headers=h, json=body).status_code == 404, (method, path)
    assert client.get("/applications", headers=h).json()["total"] == 0
    assert client.get("/applications/reminders?status=all", headers=h).json()["total"] == 0
    assert client.get("/applications/dashboard", headers=h).json()["total_applications"] == 0
    # Untouched for the owner.
    mine = client.get(f"/applications/{aid}", headers=student["headers"]).json()
    assert mine["status"] == "INTERVIEW_SCHEDULED" and mine["notes"] is None and mine["deleted_at"] is None


def test_user_id_in_body_is_rejected(client, student, other):
    response = create(client, student, company_name="Acme", title="Intern", user_id=other["user_id"])
    assert response.status_code == 422
    app = external(client, student)
    assert client.patch(f"/applications/{app['application_id']}", headers=student["headers"],
                        json={"user_id": other["user_id"]}).status_code == 422
    assert client.patch(f"/applications/{app['application_id']}", headers=student["headers"],
                        json={"status": "APPLIED"}).status_code == 422      # status has its own endpoint


# ------------------------------------------------------------------
# Create: internal and external
# ------------------------------------------------------------------

def test_internal_application_copies_internship_details(client, student, seeded):
    internship = seeded.get(Internship, student["internships"][0])
    app = internal(client, student)
    assert app["source"] == "internal" and app["status"] == "SAVED" and app["applied_at"] is None
    assert (app["company_name"], app["title"], app["domain"], app["location"], app["work_mode"]) == (
        internship.company, internship.title, internship.domain, internship.location, internship.work_mode)
    assert app["internship_active"] is True and app["deadline_passed"] is False
    assert app["related"]["prepare_with"]["endpoint"] == "/interviews/sessions"
    entries = seeded.scalars(select(ApplicationStatusHistory)).all()
    assert [(e.from_status, e.to_status, e.change_type) for e in entries] == [(None, "SAVED", "created")]


def test_internal_application_rejects_copied_fields(client, student):
    response = create(client, student, internship_id=student["internships"][0], company_name="Other")
    assert response.status_code == 422 and "come from the internship" in response.json()["detail"]


def test_external_application(client, student):
    app = external(client, student, application_url="https://jobs.acme.example/123", status="APPLIED",
                   location="Pune", work_mode="Hybrid", domain="Robotics", contact_name="Hiring Team",
                   contact_email="careers@acme.example", notes="Referred by a senior")
    assert app["source"] == "external" and app["internship_id"] is None
    assert app["status"] == "APPLIED" and app["applied_at"].endswith("Z")
    assert app["internship_active"] is None and app["possible_duplicates"] == []


def test_external_requires_company_and_title(client, student):
    assert create(client, student, company_name="Acme").status_code == 422
    assert create(client, student).status_code == 422
    assert create(client, student, company_name="  ", title="Intern").status_code == 422


@pytest.mark.parametrize("field, value", [
    ("application_url", "javascript:alert(1)"), ("application_url", "ftp://acme.example/job"),
    ("application_url", "acme.example/job"), ("application_url", "https://acme.example/a b"),
    ("contact_email", "not-an-email"), ("title", "x" * 201), ("notes", "x" * 5001),
    ("work_mode", "Office"), ("status", "SHORTLISTED"), ("status", "applied"),
])
def test_validation(client, student, field, value):
    body = {"company_name": "Beta", "title": "Analyst", field: value}
    assert create(client, student, **body).status_code == 422


def test_dates_need_a_timezone_and_sensible_range(client, student):
    naive = create(client, student, company_name="A", title="B", status="APPLIED", applied_at="2026-11-01T10:00:00")
    assert naive.status_code == 422 and "timezone offset" in str(naive.json())
    future = create(client, student, company_name="A", title="B", status="APPLIED", applied_at=in_days(3))
    assert future.status_code == 422
    ancient = create(client, student, company_name="A", title="B", status="APPLIED",
                     applied_at="1999-12-31T10:00:00+05:30")
    assert ancient.status_code == 422
    saved_with_date = create(client, student, company_name="A", title="B", applied_at=in_days(-1))
    assert saved_with_date.status_code == 422


def test_ist_input_is_stored_and_returned_in_utc(client, student):
    app = external(client, student, status="APPLIED", applied_at="2026-11-01T10:30:00+05:30")
    assert app["applied_at"] == "2026-11-01T05:00:00Z"
    other_zone = external(client, student, title="Data Intern", status="APPLIED",
                          applied_at="2026-11-01T00:30:00-05:00")
    assert other_zone["applied_at"] == "2026-11-01T05:30:00Z"
    for key in ("created_at", "updated_at", "status_changed_at"):
        assert app[key].endswith("Z")


def test_missing_inactive_and_past_deadline_internships(client, student, seeded):
    assert create(client, student, internship_id=999999).status_code == 404
    seeded.get(Internship, student["internships"][1]).is_active = False
    seeded.get(Internship, student["internships"][2]).deadline = now_utc() - timedelta(days=2)
    seeded.commit()
    assert create(client, student, internship_id=student["internships"][1]).status_code == 404
    late = internal(client, student, index=2, status="APPLIED", applied_at=in_days(-5))
    assert late["deadline_passed"] is True


def test_deactivated_or_removed_internship_keeps_the_application(client, student, seeded):
    app = internal(client, student)
    internship = seeded.get(Internship, student["internships"][0])
    internship.is_active = False
    seeded.commit()
    shown = client.get(f"/applications/{app['application_id']}", headers=student["headers"]).json()
    assert shown["internship_active"] is False and shown["company_name"] == app["company_name"]

    seeded.delete(internship)             # a hard delete (not exposed by the API) sets internship_id to NULL
    seeded.commit()
    shown = client.get(f"/applications/{app['application_id']}", headers=student["headers"]).json()
    assert shown["internship_id"] is None and shown["title"] == app["title"] and shown["source"] == "internal"


def test_phase5_documents_link_and_ownership(client, student, other, seeded):
    def document(owner, kind):
        doc = GeneratedDocument(user_id=owner["user_id"], document_type=kind, title=f"My {kind}", content="x")
        seeded.add(doc)
        seeded.commit()
        return doc.document_id

    resume_doc, letter_doc = document(student, "resume"), document(student, "cover_letter")
    foreign = document(other, "resume")
    app = internal(client, student, resume_document_id=resume_doc, cover_letter_document_id=letter_doc)
    assert {d["document_type"] for d in app["related"]["documents"]} == {"resume", "cover_letter"}
    assert create(client, student, company_name="A", title="B", resume_document_id=foreign).status_code == 404
    assert create(client, student, company_name="A", title="B", resume_document_id=letter_doc).status_code == 422


# ------------------------------------------------------------------
# Duplicates
# ------------------------------------------------------------------

def test_one_active_application_per_internship(client, student):
    first = internal(client, student)
    again = create(client, student, internship_id=student["internships"][0])
    assert again.status_code == 409 and again.json()["detail"]["application_id"] == first["application_id"]


def test_external_duplicates_by_normalised_url(client, student):
    first = external(client, student, application_url="https://www.Acme.example/jobs/42/?utm_source=x#apply")
    same = create(client, student, company_name="ACME robotics", title="Another title",
                  application_url="http://acme.example/jobs/42?ref=linkedin")
    assert same.status_code == 409 and same.json()["detail"]["application_id"] == first["application_id"]
    different = create(client, student, company_name="Acme Robotics", title="Software Intern",
                       application_url="https://acme.example/jobs/43")
    assert different.status_code == 201


def test_external_duplicates_by_reference(client, student):
    external(client, student, external_reference="REQ-1001")
    clash = create(client, student, company_name="  acme   ROBOTICS ", title="Other", external_reference="REQ-1001")
    assert clash.status_code == 409
    assert create(client, student, company_name="Acme Robotics", title="Software Intern",
                  external_reference="REQ-1002").status_code == 201
    assert create(client, student, company_name="Beta Labs", title="Software Intern",
                  external_reference="REQ-1001").status_code == 201


def test_same_company_and_title_without_identifier_is_allowed_with_warning(client, student):
    first = external(client, student)
    second = external(client, student)
    assert second["possible_duplicates"] == [first["application_id"]]


def test_editing_into_a_duplicate_is_rejected(client, student):
    external(client, student, application_url="https://acme.example/jobs/1")
    second = external(client, student, application_url="https://acme.example/jobs/2")
    response = client.patch(f"/applications/{second['application_id']}", headers=student["headers"],
                            json={"application_url": "https://ACME.example/jobs/1/"})
    assert response.status_code == 409


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------

def test_update_details_records_field_names_only(client, student):
    app = external(client, student)
    h, aid = student["headers"], app["application_id"]
    updated = client.patch(f"/applications/{aid}", headers=h, json={
        "notes": "Spoke to Priya about the role", "contact_name": "Priya", "contact_email": "priya@acme.example",
        "location": "Bengaluru"})
    assert updated.status_code == 200 and updated.json()["contact_name"] == "Priya"
    activity = client.get(f"/applications/{aid}/history", headers=h).json()["activity"]
    entry = next(a for a in activity if a["event_type"] == "details_updated")
    assert entry["details"] == {"fields": ["contact_email", "contact_name", "location", "notes"]}
    text = str(activity)
    for secret in ("Priya", "priya@acme.example", "Bengaluru"):
        assert secret not in text

    same = client.patch(f"/applications/{aid}", headers=h, json={"location": "Bengaluru"})
    assert same.status_code == 200
    assert len([a for a in client.get(f"/applications/{aid}/history", headers=h).json()["activity"]
                if a["event_type"] == "details_updated"]) == 1          # no-op edits are not recorded


def test_update_rules(client, student):
    h = student["headers"]
    internal_app = internal(client, student)
    assert client.patch(f"/applications/{internal_app['application_id']}", headers=h,
                        json={"title": "Changed"}).status_code == 422
    assert client.patch(f"/applications/{internal_app['application_id']}", headers=h,
                        json={"applied_at": in_days(-1)}).status_code == 422      # still SAVED
    ext = external(client, student, status="APPLIED")
    assert client.patch(f"/applications/{ext['application_id']}", headers=h,
                        json={"company_name": None}).status_code == 422
    assert client.patch(f"/applications/{ext['application_id']}", headers=h,
                        json={"applied_at": None}).status_code == 422
    moved = client.patch(f"/applications/{ext['application_id']}", headers=h,
                         json={"applied_at": "2026-10-01T09:00:00+05:30"}).json()
    assert moved["applied_at"] == "2026-10-01T03:30:00Z"


# ------------------------------------------------------------------
# Trash, restore and permanent deletion
# ------------------------------------------------------------------

def test_delete_requires_confirmation_and_moves_to_trash(client, student, seeded):
    app = internal(client, student, status="APPLIED")
    aid, h = app["application_id"], student["headers"]
    add_round(client, student, aid)
    add_reminder(client, student, aid)
    assert client.delete(f"/applications/{aid}", headers=h).status_code == 422
    assert client.delete(f"/applications/{aid}?confirm=true", headers=h).status_code == 204

    assert client.get(f"/applications/{aid}", headers=h).status_code == 404
    assert client.get("/applications", headers=h).json()["total"] == 0
    assert client.get("/applications/reminders?status=all", headers=h).json()["total"] == 0
    assert client.get("/applications/dashboard", headers=h).json()["total_applications"] == 0
    trash = client.get("/applications/trash", headers=h).json()
    assert trash["total"] == 1 and trash["items"][0]["deleted_at"].endswith("Z")
    # Related records are preserved while in the trash.
    assert seeded.scalar(select(func.count()).select_from(ApplicationInterview)) == 1
    assert seeded.scalar(select(func.count()).select_from(ApplicationReminder)) == 1

    restored = client.post(f"/applications/{aid}/restore", headers=h)
    assert restored.status_code == 200 and restored.json()["interview_count"] == 1
    events = [a["event_type"] for a in client.get(f"/applications/{aid}/history", headers=h).json()["activity"]]
    assert events[-2:] == ["application_deleted", "application_restored"]
    assert client.post(f"/applications/{aid}/restore", headers=h).status_code == 409


def test_reapply_after_trash_then_restore_conflict(client, student):
    h = student["headers"]
    first = internal(client, student)
    client.delete(f"/applications/{first['application_id']}?confirm=true", headers=h)
    second = internal(client, student)                         # allowed: the first one is in the trash
    clash = client.post(f"/applications/{first['application_id']}/restore", headers=h)
    assert clash.status_code == 409 and clash.json()["detail"]["application_id"] == second["application_id"]


def test_permanent_delete_removes_everything(client, student, seeded):
    app = internal(client, student, status="APPLIED")
    aid, h = app["application_id"], student["headers"]
    add_round(client, student, aid)
    add_reminder(client, student, aid)
    set_status(client, student, aid, "SELECTED")
    assert client.delete(f"/applications/{aid}/permanent?confirm=true", headers=h).status_code == 409   # not trashed
    client.delete(f"/applications/{aid}?confirm=true", headers=h)
    assert client.delete(f"/applications/{aid}/permanent", headers=h).status_code == 422               # no confirm
    assert client.delete(f"/applications/{aid}/permanent?confirm=true", headers=h).status_code == 204
    for model in (Application, ApplicationStatusHistory, ApplicationInterview, ApplicationReminder,
                  ApplicationActivity):
        assert seeded.scalar(select(func.count()).select_from(model)) == 0, model.__name__
    assert client.get("/applications/trash", headers=h).json()["total"] == 0
    assert seeded.get(Internship, student["internships"][0]) is not None        # the internship is untouched


def test_user_deletion_cascades(client, student, seeded):
    app = internal(client, student, status="APPLIED")
    add_round(client, student, app["application_id"])
    add_reminder(client, student, app["application_id"])
    seeded.delete(seeded.get(User, student["user_id"]))
    seeded.commit()
    for model in (Application, ApplicationStatusHistory, ApplicationInterview, ApplicationReminder,
                  ApplicationActivity):
        assert seeded.scalar(select(func.count()).select_from(model)) == 0


# ------------------------------------------------------------------
# Listing: filters, search, sorting and pagination
# ------------------------------------------------------------------

@pytest.fixture
def portfolio(client, student):
    h = student["headers"]
    a = internal(client, student, 0, status="APPLIED", applied_at="2026-10-01T10:00:00+05:30")
    b = internal(client, student, 1)
    c = external(client, student, company_name="Zeta_Works", title="Data Analyst 100% remote", domain="Data",
                 status="APPLIED", applied_at="2026-11-05T10:00:00+05:30")
    d = external(client, student, company_name="Acme Robotics", title="Firmware Intern")
    set_status(client, student, d["application_id"], "WITHDRAWN")
    return {"h": h, "ids": [x["application_id"] for x in (a, b, c, d)]}


def listing(client, h, query=""):
    response = client.get(f"/applications{query}", headers=h)
    assert response.status_code == 200, response.text
    return response.json()


def test_filters(client, student, portfolio):
    h, (a, b, c, d) = portfolio["h"], portfolio["ids"]
    assert listing(client, h)["total"] == 4
    assert {i["application_id"] for i in listing(client, h, "?status=APPLIED")["items"]} == {a, c}
    assert {i["application_id"] for i in listing(client, h, "?status=APPLIED&status=WITHDRAWN")["items"]} == {a, c, d}
    assert {i["application_id"] for i in listing(client, h, "?source=external")["items"]} == {c, d}
    assert {i["application_id"] for i in listing(client, h, "?company=acme")["items"]} == {d}
    assert {i["application_id"] for i in listing(client, h, "?domain=data")["items"]} == {c}
    window = "?applied_from=2026-11-01T00:00:00%2B05:30&applied_to=2026-11-30T23:59:59%2B05:30"
    assert {i["application_id"] for i in listing(client, h, window)["items"]} == {c}
    assert client.get("/applications?applied_from=2026-11-01T00:00:00", headers=h).status_code == 422
    assert client.get("/applications?status=applied", headers=h).status_code == 422


def test_search_escapes_wildcards(client, student, portfolio):
    h, (a, b, c, d) = portfolio["h"], portfolio["ids"]
    assert {i["application_id"] for i in listing(client, h, "?q=firmware")["items"]} == {d}
    assert {i["application_id"] for i in listing(client, h, "?q=100%25")["items"]} == {c}      # literal %
    assert {i["application_id"] for i in listing(client, h, "?q=Zeta_")["items"]} == {c}       # literal _
    assert listing(client, h, "?q=%25%25%25")["total"] == 0
    assert client.get("/applications?q=" + "x" * 101, headers=h).status_code == 422


def test_sorting_and_pagination(client, student, portfolio):
    h = portfolio["h"]
    names = [i["company_name"].lower() for i in listing(client, h, "?sort=company_name&order=asc")["items"]]
    assert names == sorted(names)
    applied = listing(client, h, "?sort=applied_at&order=desc")["items"]
    assert [i["applied_at"] is None for i in applied] == [False, False, True, True]          # nulls last
    page = listing(client, h, "?sort=created_at&order=asc&skip=1&limit=2")
    assert page["total"] == 4 and [i["application_id"] for i in page["items"]] == portfolio["ids"][1:3]
    assert client.get("/applications?sort=notes", headers=h).status_code == 422
    assert client.get("/applications?limit=0", headers=h).status_code == 422


def test_empty_listing(client, student):
    body = listing(client, student["headers"])
    assert body == {"total": 0, "skip": 0, "limit": 20, "items": []}
