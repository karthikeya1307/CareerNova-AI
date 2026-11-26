"""Account security (Phase 1): super admin protection, admin limits, deactivation,
user management, user isolation and the audit log.

All tests run against the *_test database (see conftest.py).
"""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models import AdminAuditEvent, AuthSession, User
from backend.services import audit
from conftest import DEFAULT_PASSWORD


def h(user):
    return user["headers"]


def audit_rows(db_session, action=None):
    db_session.expire_all()
    query = select(AdminAuditEvent).order_by(AdminAuditEvent.event_id)
    if action:
        query = query.where(AdminAuditEvent.action == action)
    return db_session.scalars(query).all()


@pytest.fixture
def super_admin(create_user):
    return create_user(role="super_admin")


@pytest.fixture
def admin(create_user):
    return create_user(role="admin")


@pytest.fixture
def student(create_user):
    return create_user()


# ------------------------------------------------------------------
# Deactivation is enforced on every request, including old tokens
# ------------------------------------------------------------------

STUDENT_ENDPOINTS = [("GET", "/auth/me"), ("GET", "/resumes/"), ("GET", "/profiles/me"),
                     ("GET", "/applications"), ("GET", "/assistant/conversations"),
                     ("GET", "/internships/"), ("GET", "/interviews/sessions")]


def test_deactivated_user_is_rejected_everywhere_including_old_tokens(client, admin, student, db_session):
    for method, path in STUDENT_ENDPOINTS:
        assert client.request(method, path, headers=h(student)).status_code != 403, path

    response = client.post(f"/admin/users/{student['user_id']}/deactivate", headers=h(admin))
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False and body["role"] == "student"

    # The access token issued before deactivation no longer works anywhere.
    for method, path in STUDENT_ENDPOINTS:
        r = client.request(method, path, headers=h(student))
        assert r.status_code in (401, 403), (path, r.status_code)
    # Refresh token is refused and every session was revoked.
    assert client.post("/auth/refresh", json={"refresh_token": student["refresh_token"]}).status_code == 401
    db_session.expire_all()
    sessions = db_session.scalars(select(AuthSession).where(AuthSession.user_id == student["user_id"])).all()
    assert sessions and all(s.revoked_at is not None for s in sessions)
    # Signing in again is refused (after the password check, so it reveals nothing to guessers).
    login = client.post("/auth/login", json={"email": student["email"], "password": DEFAULT_PASSWORD})
    assert login.status_code == 403 and "deactivated" in login.json()["detail"]
    # Forgot-password does nothing for a deactivated account (same generic answer).
    forgot = client.post("/auth/forgot-password", json={"email": student["email"]})
    assert forgot.status_code == 200


def test_deactivated_admin_token_cannot_use_admin_api(client, super_admin, admin):
    assert client.get("/admin/users", headers=h(admin)).status_code == 200
    assert client.post(f"/admin/users/{admin['user_id']}/deactivate", headers=h(super_admin)).status_code == 200
    assert client.get("/admin/users", headers=h(admin)).status_code in (401, 403)


def test_reactivation_restores_access_and_keeps_data(client, admin, student, db_session):
    before = db_session.get(User, student["user_id"])
    snapshot = (before.email, before.first_name, before.last_name, before.phone_number, before.is_verified)

    client.post(f"/admin/users/{student['user_id']}/deactivate", headers=h(admin))
    response = client.post(f"/admin/users/{student['user_id']}/reactivate", headers=h(admin))
    assert response.status_code == 200 and response.json()["is_active"] is True

    login = client.post("/auth/login", json={"email": student["email"], "password": DEFAULT_PASSWORD})
    assert login.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["last_login_at"] is not None

    db_session.expire_all()
    after = db_session.get(User, student["user_id"])
    assert (after.email, after.first_name, after.last_name, after.phone_number, after.is_verified) == snapshot
    assert after.deactivated_at is None


def test_deactivate_and_reactivate_are_idempotent(client, admin, student, db_session):
    for _ in range(2):
        assert client.post(f"/admin/users/{student['user_id']}/deactivate", headers=h(admin)).status_code == 200
    for _ in range(2):
        assert client.post(f"/admin/users/{student['user_id']}/reactivate", headers=h(admin)).status_code == 200
    assert [e.action for e in audit_rows(db_session)] == ["user.deactivate", "user.reactivate"]


def test_reset_token_issued_before_deactivation_cannot_be_used(client, admin, student, outbox):
    client.post("/auth/forgot-password", json={"email": student["email"]})
    token = outbox.last("reset", student["email"])["token"]
    client.post(f"/admin/users/{student['user_id']}/deactivate", headers=h(admin))
    response = client.post("/auth/reset-password", json={"token": token, "new_password": "NewPassw0rd!"})
    assert response.status_code == 400


# ------------------------------------------------------------------
# Admin limits
# ------------------------------------------------------------------

def test_admin_cannot_promote_or_manage_other_admins_or_the_super_admin(client, super_admin, admin, create_user):
    other_admin = create_user(role="admin")
    student = create_user()

    for target, role in [(student, "admin"), (other_admin, "student"), (super_admin, "student")]:
        assert client.patch(f"/admin/users/{target['user_id']}/role", headers=h(admin),
                            json={"role": role}).status_code == 403
    for target in (other_admin, super_admin):
        for action in ("deactivate", "reactivate"):
            assert client.post(f"/admin/users/{target['user_id']}/{action}", headers=h(admin)).status_code == 403
    assert client.post("/admin/users", headers=h(admin), json={
        "first_name": "New", "last_name": "Admin", "email": "new-admin@example.com", "role": "admin"
    }).status_code == 403
    # Admins still manage students.
    assert client.post(f"/admin/users/{student['user_id']}/deactivate", headers=h(admin)).status_code == 200


def test_admin_cannot_change_own_status(client, admin):
    assert client.post(f"/admin/users/{admin['user_id']}/deactivate", headers=h(admin)).status_code == 400


# ------------------------------------------------------------------
# The super admin is protected
# ------------------------------------------------------------------

def test_super_admin_cannot_be_deactivated_demoted_or_deleted_through_the_api(client, super_admin, db_session):
    sid = super_admin["user_id"]
    assert client.post(f"/admin/users/{sid}/deactivate", headers=h(super_admin)).status_code == 403
    assert client.patch(f"/admin/users/{sid}/role", headers=h(super_admin),
                        json={"role": "admin"}).status_code == 403
    deleted = client.request("DELETE", "/auth/account", headers=h(super_admin),
                             json={"current_password": DEFAULT_PASSWORD})
    assert deleted.status_code == 403
    db_session.expire_all()
    account = db_session.get(User, sid)
    assert account is not None and account.role == "super_admin" and account.is_active


def test_super_admin_role_cannot_be_granted_through_the_api(client, super_admin, student):
    response = client.patch(f"/admin/users/{student['user_id']}/role", headers=h(super_admin),
                            json={"role": "super_admin"})
    assert response.status_code == 403 and "create-superadmin" in response.json()["detail"]
    created = client.post("/admin/users", headers=h(super_admin), json={
        "first_name": "X", "last_name": "Y", "email": "x@example.com", "role": "super_admin"})
    assert created.status_code == 422


def test_super_admin_manages_admins(client, super_admin, admin, db_session):
    aid = admin["user_id"]
    assert client.post(f"/admin/users/{aid}/deactivate", headers=h(super_admin)).status_code == 200
    assert client.post(f"/admin/users/{aid}/reactivate", headers=h(super_admin)).status_code == 200
    demoted = client.patch(f"/admin/users/{aid}/role", headers=h(super_admin), json={"role": "student"})
    assert demoted.status_code == 200 and demoted.json()["role"] == "student"
    change = audit_rows(db_session, "user.role_change")[0]
    assert change.details == {"from": "admin", "to": "student"}
    assert change.actor_user_id == super_admin["user_id"] and change.actor_role == "super_admin"


def test_only_one_super_admin_can_exist(db_session, super_admin, student):
    user = db_session.get(User, student["user_id"])
    user.role = "super_admin"
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_registration_cannot_choose_a_role(client):
    response = client.post("/auth/register", json={
        "first_name": "Eve", "last_name": "Attacker", "phone_number": "+919876543210",
        "email": "eve@example.com", "password": "Str0ngPass!word", "role": "super_admin", "is_active": True,
    })
    assert response.status_code == 201
    assert response.json()["role"] == "student"


def test_students_cannot_use_any_admin_endpoint(client, student, create_user):
    other = create_user()
    for method, path in [("GET", "/admin/users"), ("GET", f"/admin/users/{other['user_id']}"),
                         ("POST", "/admin/users"), ("POST", f"/admin/users/{other['user_id']}/deactivate"),
                         ("POST", f"/admin/users/{other['user_id']}/reactivate"),
                         ("PATCH", f"/admin/users/{other['user_id']}/role"), ("GET", "/admin/audit-events"),
                         ("GET", "/admin/index/status"), ("POST", "/admin/index/rebuild")]:
        assert client.request(method, path, headers=h(student), json={}).status_code == 403, path


# ------------------------------------------------------------------
# Listing, searching and creating users
# ------------------------------------------------------------------

def test_list_users_search_and_filters(client, admin, create_user):
    create_user(email="priya.sharma@example.com")
    deactivated = create_user(email="rahul_k@example.com")
    client.post(f"/admin/users/{deactivated['user_id']}/deactivate", headers=h(admin))

    def emails(**params):
        response = client.get("/admin/users", headers=h(admin), params=params)
        assert response.status_code == 200
        return sorted(u["email"] for u in response.json())

    assert emails(q="PRIYA") == ["priya.sharma@example.com"]
    assert emails(q="rahul_") == ["rahul_k@example.com"]            # "_" is literal, not a wildcard
    assert emails(q="%") == []                                       # "%" is literal too
    assert emails(role="admin") == [admin["email"]]
    assert emails(is_active="false") == ["rahul_k@example.com"]
    assert len(emails()) == 3
    assert client.get("/admin/users", headers=h(admin), params={"role": "owner"}).status_code == 422
    # The list response keeps its original shape (a JSON list) with additive fields.
    first = client.get("/admin/users", headers=h(admin)).json()[0]
    assert {"user_id", "email", "role", "is_verified", "created_at", "is_active", "last_login_at"} <= first.keys()


def test_admin_creates_a_pending_student_account_without_handling_a_password(client, admin, db_session):
    response = client.post("/admin/users", headers=h(admin), json={
        "first_name": " Anu ", "last_name": "Menon", "email": "Anu.Menon@Example.com"})
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "anu.menon@example.com" and body["role"] == "student"
    assert body["is_verified"] is False and body["is_active"] is True
    assert "password" not in json.dumps(body).lower()
    # Nobody knows the password, so the account cannot sign in until activated (Phase 2).
    login = client.post("/auth/login", json={"email": "anu.menon@example.com", "password": DEFAULT_PASSWORD})
    assert login.status_code == 401
    assert client.post("/admin/users", headers=h(admin), json={
        "first_name": "A", "last_name": "M", "email": "ANU.MENON@example.com"}).status_code == 409
    event = audit_rows(db_session, "user.create")[0]
    assert event.target_user_id == body["user_id"] and event.details == {"role": "student", "pending_activation": True}


def test_super_admin_can_create_an_admin_account(client, super_admin):
    response = client.post("/admin/users", headers=h(super_admin), json={
        "first_name": "Ops", "last_name": "Admin", "email": "ops@example.com", "role": "admin"})
    assert response.status_code == 201 and response.json()["role"] == "admin"


# ------------------------------------------------------------------
# Audit log
# ------------------------------------------------------------------

def test_admin_actions_are_audited_and_listed(client, super_admin, admin, student, db_session):
    client.post(f"/admin/users/{student['user_id']}/deactivate", headers=h(admin))
    client.post(f"/admin/users/{student['user_id']}/reactivate", headers=h(admin))
    client.patch(f"/admin/users/{student['user_id']}/role", headers=h(super_admin), json={"role": "admin"})
    created = client.post("/internships/", headers=h(admin), json={
        "title": "Audit Intern", "company": "Ledger Co", "required_skills": ["Python"]}).json()
    client.patch(f"/internships/{created['internship_id']}", headers=h(admin), json={"title": "Audit Intern II"})
    client.delete(f"/internships/{created['internship_id']}", headers=h(admin))

    page = client.get("/admin/audit-events", headers=h(admin)).json()
    actions = [e["action"] for e in page["items"]]
    assert page["total"] == 6
    assert actions == ["internship.deactivate", "internship.update", "internship.create",
                       "user.role_change", "user.reactivate", "user.deactivate"]          # newest first
    update = page["items"][1]
    assert update["details"] == {"internship_id": created["internship_id"], "fields": ["title"]}
    filtered = client.get("/admin/audit-events", headers=h(admin),
                          params={"target_user_id": student["user_id"]}).json()
    assert [e["action"] for e in filtered["items"]] == ["user.role_change", "user.reactivate", "user.deactivate"]
    assert all(e["ip_address"] for e in filtered["items"])


def test_audit_log_never_contains_secrets(client, super_admin, admin, student, db_session, outbox):
    # Exercise every audited action plus token-producing flows.
    client.post(f"/admin/users/{student['user_id']}/deactivate", headers=h(admin))
    client.post(f"/admin/users/{student['user_id']}/reactivate", headers=h(admin))
    client.patch(f"/admin/users/{student['user_id']}/role", headers=h(super_admin), json={"role": "admin"})
    client.post("/admin/users", headers=h(admin), json={"first_name": "P", "last_name": "Q", "email": "pq@example.com"})
    for _ in range(6):
        client.post("/auth/login", json={"email": student["email"], "password": "WrongPassw0rd"})
    client.post("/auth/forgot-password", json={"email": admin["email"]})
    reset_token = outbox.last("reset", admin["email"])["token"]

    rows = audit_rows(db_session)
    assert {r.action for r in rows} >= {"user.deactivate", "user.reactivate", "user.role_change",
                                        "user.create", "auth.login_locked"}
    dumped = json.dumps([{c.name: str(getattr(r, c.name)) for c in r.__table__.columns} for r in rows]).lower()
    hashes = [u.password_hash.lower() for u in db_session.scalars(select(User))]
    secrets = [DEFAULT_PASSWORD.lower(), "wrongpassw0rd", "$argon2", reset_token.lower(),
               *[t.lower() for u in (super_admin, admin, student) for t in (u["access_token"], u["refresh_token"])],
               *hashes]
    for secret in secrets:
        assert secret not in dumped
    assert "password" not in dumped and "token" not in dumped


@pytest.mark.parametrize("details", [
    {"password": "x"}, {"new_password_hash": "x"}, {"reset_token": "x"}, {"smtp_user": "x"},
    {"api_key": "x"}, {"Secret": "x"}, {"jwt": "x"}, {"nested": {"a": 1}},
])
def test_audit_refuses_secret_looking_details(details):
    with pytest.raises(ValueError):
        audit.safe_details(details)


def test_audit_refuses_unknown_actions(db_session):
    with pytest.raises(ValueError):
        audit.record(db_session, "user.delete_everything")
