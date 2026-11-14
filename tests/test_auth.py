"""Authentication tests: existing flows (regression) and Phase 0 resend."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.models import EmailVerificationToken, User
from backend.utils.tokens import hash_token

REGISTER_BODY = {
    "first_name": "Asha",
    "last_name": "Rao",
    "phone_number": "+91 98765 43210",
    "email": "asha@example.com",
    "password": "Str0ngPass!word",
}


def register(client, **overrides):
    body = {**REGISTER_BODY, **overrides}
    return client.post("/auth/register", json=body)


def backdate_verification_tokens(db_session, email, seconds=120):
    user = db_session.scalar(select(User).where(User.email == email))
    for record in db_session.scalars(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.user_id
        )
    ):
        record.created_at = datetime.now(timezone.utc) - timedelta(
            seconds=seconds
        )
    db_session.commit()


# ------------------------------------------------------------------
# Existing flows (regression)
# ------------------------------------------------------------------

def test_register_returns_user_and_sends_verification(client, outbox):
    response = register(client)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "asha@example.com"
    assert data["role"] == "student"
    assert data["is_verified"] is False
    assert data["phone_number"] == "+919876543210"
    assert "password_hash" not in data
    assert outbox.count("verify", "asha@example.com") == 1


def test_duplicate_registration_is_rejected(client):
    assert register(client).status_code == 201
    assert register(client, email="ASHA@example.com").status_code == 409


def test_login_requires_verified_email(client, outbox):
    register(client)
    login = {"email": "asha@example.com", "password": "Str0ngPass!word"}

    assert client.post("/auth/login", json=login).status_code == 403

    token = outbox.last("verify", "asha@example.com")["token"]
    assert client.get(
        "/auth/verify-email", params={"token": token}
    ).status_code == 200

    response = client.post("/auth/login", json=login)
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_verification_link_is_single_use(client, outbox):
    register(client)
    token = outbox.last("verify", "asha@example.com")["token"]

    assert client.get(
        "/auth/verify-email", params={"token": token}
    ).status_code == 200
    second = client.get("/auth/verify-email", params={"token": token})
    assert second.status_code == 400


def test_wrong_password_is_rejected(client, create_user):
    user = create_user()
    response = client.post("/auth/login", json={
        "email": user["email"], "password": "wrong-password"
    })
    assert response.status_code == 401


def test_me_requires_token(client, create_user):
    assert client.get("/auth/me").status_code == 401

    user = create_user()
    response = client.get("/auth/me", headers=user["headers"])
    assert response.status_code == 200
    assert response.json()["is_verified"] is True


def test_refresh_rotates_token_and_logout_revokes(client, create_user):
    user = create_user()

    refreshed = client.post(
        "/auth/refresh", json={"refresh_token": user["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["refresh_token"]
    assert new_refresh != user["refresh_token"]

    # Old refresh token no longer works after rotation.
    assert client.post(
        "/auth/refresh", json={"refresh_token": user["refresh_token"]}
    ).status_code == 401

    assert client.post(
        "/auth/logout", json={"refresh_token": new_refresh}
    ).status_code == 200

    # Access tokens tied to the revoked session stop working.
    new_access = refreshed.json()["access_token"]
    assert client.get(
        "/auth/me", headers={"Authorization": f"Bearer {new_access}"}
    ).status_code == 401


def test_change_password_revokes_sessions(client, create_user):
    user = create_user()

    response = client.post("/auth/change-password", headers=user["headers"], json={
        "current_password": user["password"],
        "new_password": "An0therStrong!pw",
    })
    assert response.status_code == 200
    assert client.get("/auth/me", headers=user["headers"]).status_code == 401

    assert client.post("/auth/login", json={
        "email": user["email"], "password": "An0therStrong!pw"
    }).status_code == 200


def test_forgot_and_reset_password(client, create_user, outbox):
    user = create_user()

    unknown = client.post(
        "/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    known = client.post(
        "/auth/forgot-password", json={"email": user["email"]}
    )
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()

    token = outbox.last("reset", user["email"])["token"]
    response = client.post("/auth/reset-password", json={
        "token": token, "new_password": "Reset!Passw0rd",
    })
    assert response.status_code == 200

    assert client.post("/auth/reset-password", json={
        "token": token, "new_password": "Other!Passw0rd",
    }).status_code == 400

    assert client.post("/auth/login", json={
        "email": user["email"], "password": "Reset!Passw0rd"
    }).status_code == 200


def test_delete_account(client, create_user):
    user = create_user()

    assert client.request(
        "DELETE", "/auth/account", headers=user["headers"],
        json={"current_password": "wrong"},
    ).status_code == 400

    assert client.request(
        "DELETE", "/auth/account", headers=user["headers"],
        json={"current_password": user["password"]},
    ).status_code == 204


def test_unverified_user_token_is_rejected(client, create_user, db_session):
    user = create_user()
    record = db_session.get(User, user["user_id"])
    record.is_verified = False
    db_session.commit()

    response = client.get("/auth/me", headers=user["headers"])
    assert response.status_code == 403


# ------------------------------------------------------------------
# Phase 0: resend verification email
# ------------------------------------------------------------------

def test_resend_unknown_email_returns_generic_response(client, outbox):
    response = client.post(
        "/auth/resend-verification", json={"email": "ghost@example.com"}
    )
    assert response.status_code == 200
    assert "unverified account" in response.json()["message"]
    assert outbox.messages == []


def test_resend_for_verified_user_sends_nothing(client, create_user, outbox):
    user = create_user()
    before = outbox.count("verify", user["email"])

    response = client.post(
        "/auth/resend-verification", json={"email": user["email"]}
    )
    assert response.status_code == 200
    assert outbox.count("verify", user["email"]) == before


def test_resend_is_throttled(client, outbox):
    register(client)

    response = client.post(
        "/auth/resend-verification", json={"email": "asha@example.com"}
    )
    assert response.status_code == 200
    # Registration email only; resend within the cooldown is skipped.
    assert outbox.count("verify", "asha@example.com") == 1


def test_resend_issues_new_link_and_invalidates_old(client, outbox, db_session):
    register(client)
    old_token = outbox.last("verify", "asha@example.com")["token"]
    backdate_verification_tokens(db_session, "asha@example.com")

    response = client.post(
        "/auth/resend-verification", json={"email": "Asha@Example.com"}
    )
    assert response.status_code == 200
    assert outbox.count("verify", "asha@example.com") == 2

    new_token = outbox.last("verify", "asha@example.com")["token"]
    assert new_token != old_token

    old = client.get("/auth/verify-email", params={"token": old_token})
    assert old.status_code == 400

    new = client.get("/auth/verify-email", params={"token": new_token})
    assert new.status_code == 200


def test_resend_smtp_failure_disables_new_link(client, outbox, db_session):
    register(client)
    backdate_verification_tokens(db_session, "asha@example.com")

    outbox.fail = True
    response = client.post(
        "/auth/resend-verification", json={"email": "asha@example.com"}
    )
    assert response.status_code == 200

    db_session.expire_all()
    user = db_session.scalar(
        select(User).where(User.email == "asha@example.com")
    )
    active = db_session.scalars(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.user_id,
            EmailVerificationToken.used_at.is_(None),
        )
    ).all()
    assert active == []


def test_resend_tokens_are_stored_hashed(client, outbox, db_session):
    register(client)
    raw = outbox.last("verify", "asha@example.com")["token"]

    stored = db_session.scalar(select(EmailVerificationToken))
    assert stored.token_hash == hash_token(raw)
    assert stored.token_hash != raw
