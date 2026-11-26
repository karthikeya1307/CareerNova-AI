"""Phase 2: admin invitations -> activation with the user's own password (test database only).

Emails are captured by the test outbox (conftest); nothing reaches a mail server.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from backend.models import AdminAuditEvent, EmailDelivery, User, UserInvitation
from backend.services import invitations

NEW_PASSWORD = "Activ8-MyAccount"


def h(user):
    return user["headers"]


@pytest.fixture
def admin(create_user):
    return create_user(role="admin")


@pytest.fixture
def super_admin(create_user):
    return create_user(role="super_admin")


def invite(client, actor, email="anu@example.com", **extra):
    response = client.post("/admin/users", headers=h(actor), json={
        "first_name": "Anu", "last_name": "Menon", "email": email, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def age_invitations(db_session, user_id, minutes):
    db_session.execute(update(UserInvitation).where(UserInvitation.user_id == user_id).values(
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes)))
    db_session.commit()


def test_full_onboarding_flow_admin_never_handles_a_password(client, admin, outbox, db_session):
    created = invite(client, admin)
    assert created["is_verified"] is False
    assert created["invitation"]["status"] == "pending" and created["invitation"]["delivery_status"] == "sent"
    mail = outbox.last("invite", "anu@example.com")
    assert mail["first_name"] == "Anu" and mail["invited_by"] == "Test User1"

    # The pending account cannot sign in yet.
    assert client.post("/auth/login", json={"email": "anu@example.com", "password": NEW_PASSWORD}).status_code == 401

    check = client.post("/auth/invitation/check", json={"token": mail["token"]})
    assert check.status_code == 200
    assert check.json()["email"] == "anu@example.com" and check.json()["first_name"] == "Anu"

    weak = client.post("/auth/invitation/accept", json={"token": mail["token"], "password": "lettersonly"})
    assert weak.status_code == 422
    accepted = client.post("/auth/invitation/accept", json={"token": mail["token"], "password": NEW_PASSWORD})
    assert accepted.status_code == 200 and accepted.json()["email"] == "anu@example.com"
    assert outbox.count("activated", "anu@example.com") == 1

    login = client.post("/auth/login", json={"email": "anu@example.com", "password": NEW_PASSWORD})
    assert login.status_code == 200
    db_session.expire_all()
    user = db_session.get(User, created["user_id"])
    assert user.is_verified and user.role == "student"
    activation = db_session.scalars(select(AdminAuditEvent).where(AdminAuditEvent.action == "user.activate")).one()
    assert activation.actor_user_id == user.user_id and activation.details == {"via": "invitation"}

    # Single use.
    again = client.post("/auth/invitation/accept", json={"token": mail["token"], "password": "An0ther-Pass"})
    assert again.status_code == 410 and again.json()["detail"]["code"] == "used"
    assert client.post("/auth/invitation/check", json={"token": mail["token"]}).status_code == 410


def test_tokens_are_stored_only_as_hashes_and_never_logged(client, admin, outbox, db_session):
    created = invite(client, admin)
    token = outbox.last("invite", "anu@example.com")["token"]
    client.post("/auth/invitation/accept", json={"token": token, "password": NEW_PASSWORD})
    db_session.expire_all()
    stored = db_session.scalars(select(UserInvitation)).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64
    rows = db_session.scalars(select(AdminAuditEvent)).all()
    dumped = json.dumps([[str(getattr(r, c.name)) for c in r.__table__.columns] for r in rows])
    assert token not in dumped and NEW_PASSWORD not in dumped
    assert created["invitation"]["invitation_id"] == stored.invitation_id


def test_expired_and_invalid_links(client, admin, outbox, db_session):
    created = invite(client, admin)
    token = outbox.last("invite", "anu@example.com")["token"]
    db_session.execute(update(UserInvitation).values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    db_session.commit()
    expired = client.post("/auth/invitation/accept", json={"token": token, "password": NEW_PASSWORD})
    assert expired.status_code == 410 and expired.json()["detail"]["code"] == "expired"
    bogus = client.post("/auth/invitation/check", json={"token": "x" * 43})
    assert bogus.status_code == 400 and bogus.json()["detail"]["code"] == "invalid"
    listed = client.get("/admin/users", headers=h(admin), params={"q": "anu"}).json()[0]
    assert listed["user_id"] == created["user_id"] and listed["invitation"]["status"] == "expired"


def test_resend_revokes_the_old_link_and_is_rate_limited(client, admin, outbox, db_session):
    created = invite(client, admin)
    uid = created["user_id"]
    first = outbox.last("invite", "anu@example.com")["token"]

    too_soon = client.post(f"/admin/users/{uid}/invitation", headers=h(admin))
    assert too_soon.status_code == 429 and too_soon.json()["detail"]["code"] == "cooldown"
    assert 0 < int(too_soon.headers["Retry-After"]) <= 60

    age_invitations(db_session, uid, 2)
    resent = client.post(f"/admin/users/{uid}/invitation", headers=h(admin))
    assert resent.status_code == 200 and resent.json()["invitation"]["status"] == "pending"
    second = outbox.last("invite", "anu@example.com")["token"]
    assert second != first
    old = client.post("/auth/invitation/check", json={"token": first})
    assert old.status_code == 410 and old.json()["detail"]["code"] == "revoked"
    assert client.post("/auth/invitation/check", json={"token": second}).status_code == 200

    # Daily limit (5 per account per 24 h).
    for _ in range(invitations.MAX_PER_DAY - 2):
        age_invitations(db_session, uid, 2)
        assert client.post(f"/admin/users/{uid}/invitation", headers=h(admin)).status_code == 200
    age_invitations(db_session, uid, 2)
    limited = client.post(f"/admin/users/{uid}/invitation", headers=h(admin))
    assert limited.status_code == 429 and limited.json()["detail"]["code"] == "daily_limit"


def test_revoke_invitation(client, admin, outbox, db_session):
    created = invite(client, admin)
    token = outbox.last("invite", "anu@example.com")["token"]
    revoked = client.post(f"/admin/users/{created['user_id']}/invitation/revoke", headers=h(admin))
    assert revoked.status_code == 200 and revoked.json()["invitation"]["status"] == "revoked"
    response = client.post("/auth/invitation/accept", json={"token": token, "password": NEW_PASSWORD})
    assert response.status_code == 410 and response.json()["detail"]["code"] == "revoked"
    assert db_session.scalars(select(AdminAuditEvent).where(AdminAuditEvent.action == "user.invite_revoke")).one()


def test_deactivated_or_active_accounts_cannot_be_invited_or_activated(client, admin, create_user, outbox, db_session):
    created = invite(client, admin)
    uid = created["user_id"]
    token = outbox.last("invite", "anu@example.com")["token"]
    client.post(f"/admin/users/{uid}/deactivate", headers=h(admin))
    blocked = client.post("/auth/invitation/accept", json={"token": token, "password": NEW_PASSWORD})
    assert blocked.status_code == 400 and blocked.json()["detail"]["code"] == "inactive"
    age_invitations(db_session, uid, 2)
    resend = client.post(f"/admin/users/{uid}/invitation", headers=h(admin))
    assert resend.status_code == 409 and resend.json()["detail"]["code"] == "inactive"

    active = create_user()
    not_pending = client.post(f"/admin/users/{active['user_id']}/invitation", headers=h(admin))
    assert not_pending.status_code == 409 and not_pending.json()["detail"]["code"] == "not_pending"


def test_admin_invitation_permissions(client, admin, super_admin, create_user):
    student = create_user()
    assert client.post("/admin/users", headers=h(student), json={
        "first_name": "X", "last_name": "Y", "email": "x@example.com"}).status_code == 403
    pending_admin = invite(client, super_admin, email="ops@example.com", role="admin")
    assert pending_admin["invitation"]["status"] == "pending"
    # A regular admin cannot re-send or revoke an administrator's invitation.
    assert client.post(f"/admin/users/{pending_admin['user_id']}/invitation", headers=h(admin)).status_code == 403
    assert client.post(f"/admin/users/{pending_admin['user_id']}/invitation/revoke",
                       headers=h(admin)).status_code == 403
    for path in ("/admin/invitations", "/admin/email/status", "/admin/email/deliveries"):
        assert client.get(path, headers=h(student)).status_code == 403


def test_failed_delivery_is_reported_not_hidden_and_can_be_resent(client, admin, outbox, db_session):
    outbox.fail = True
    created = invite(client, admin)
    assert created["invitation"]["delivery_status"] == "failed"
    assert created["invitation"]["delivery_error"] == "connect_failed"
    outbox.fail = False
    age_invitations(db_session, created["user_id"], 2)
    resent = client.post(f"/admin/users/{created['user_id']}/invitation", headers=h(admin)).json()
    assert resent["invitation"]["delivery_status"] == "sent"
    listing = client.get("/admin/invitations", headers=h(admin)).json()
    assert [(i["status"], i["delivery_status"]) for i in listing] == [("pending", "sent"), ("revoked", "failed")]


def test_creating_without_an_invitation(client, admin, outbox):
    created = invite(client, admin, send_invitation=False)
    assert created["invitation"] is None and outbox.count("invite", "anu@example.com") == 0


def test_password_reset_emails_are_rate_limited(client, create_user, outbox):
    user = create_user()
    for _ in range(3):
        assert client.post("/auth/forgot-password", json={"email": user["email"]}).status_code == 200
    assert outbox.count("reset", user["email"]) == 1


def test_email_status_endpoint_never_exposes_secrets(client, admin, monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.net")
    monkeypatch.setenv("SMTP_USERNAME", "mailer@example.net")
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret-app-password")
    monkeypatch.setenv("MAIL_FROM", "your_actual_gmail@gmail.com")
    body = client.get("/admin/email/status", headers=h(admin)).json()
    assert body["mode"] == "smtp" and body["ok"] is False
    assert any("placeholder" in p for p in body["problems"])
    assert "super-secret-app-password" not in json.dumps(body) and "mailer@example.net" not in json.dumps(body)


def test_delivery_log_is_listed_for_admins(client, admin, db_session):
    db_session.add(EmailDelivery(kind="invitation", recipient="a@example.com", status="failed", error_code="timeout"))
    db_session.commit()
    items = client.get("/admin/email/deliveries", headers=h(admin), params={"status": "failed"}).json()
    assert [(i["kind"], i["status"], i["error_code"]) for i in items] == [("invitation", "failed", "timeout")]
