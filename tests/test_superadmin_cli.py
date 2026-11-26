"""Account security (Phase 1): the create-superadmin bootstrap command (test database only)."""

import json

import pytest
from pwdlib import PasswordHash
from sqlalchemy import select

from backend import manage
from backend.models import AdminAuditEvent, User
from conftest import DEFAULT_PASSWORD

PASSWORD = "Bootstr4p-Secret!"


def answers(*values):
    """A stand-in for getpass that records the prompts it was asked."""
    queue = list(values)
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return queue.pop(0)

    ask.prompts = prompts
    return ask


def super_admins(db_session):
    db_session.expire_all()
    return db_session.scalars(select(User).where(User.role == "super_admin")).all()


def audit_events(db_session):
    db_session.expire_all()
    return db_session.scalars(select(AdminAuditEvent)).all()


def test_creates_a_verified_active_super_admin_and_never_prints_the_password(db_session, capsys, client):
    ask = answers(PASSWORD, PASSWORD)
    assert manage.create_superadmin("Owner@Example.com", "Ada", "Admin", ask_password=ask) == 0
    assert all("hidden" in p for p in ask.prompts)

    [account] = super_admins(db_session)
    assert (account.email, account.is_verified, account.is_active) == ("owner@example.com", True, True)
    assert PasswordHash.recommended().verify(PASSWORD, account.password_hash)
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err and account.password_hash not in output.out
    [event] = audit_events(db_session)
    assert event.action == "superadmin.bootstrap" and event.details == {"mode": "created"}
    assert PASSWORD not in json.dumps(event.details)
    # The new account can sign in and reach the admin API.
    login = client.post("/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    token = login.json()["access_token"]
    assert client.get("/admin/audit-events", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_is_idempotent_for_the_same_email(db_session, capsys):
    manage.create_superadmin("owner@example.com", "Ada", "Admin", ask_password=answers(PASSWORD, PASSWORD))
    first = super_admins(db_session)[0]
    hash_before = first.password_hash

    ask = answers()                                   # must not be asked for a password again
    assert manage.create_superadmin("OWNER@example.com", "Other", "Name", ask_password=ask) == 0
    assert ask.prompts == []
    [again] = super_admins(db_session)
    assert (again.user_id, again.password_hash, again.first_name) == (first.user_id, hash_before, "Ada")
    assert len(audit_events(db_session)) == 1
    assert "already the super admin" in capsys.readouterr().out


def test_refuses_a_second_super_admin(db_session):
    manage.create_superadmin("owner@example.com", "Ada", "Admin", ask_password=answers(PASSWORD, PASSWORD))
    assert manage.create_superadmin("other@example.com", "Bo", "B", ask_password=answers(PASSWORD, PASSWORD)) == 1
    assert [u.email for u in super_admins(db_session)] == ["owner@example.com"]


@pytest.mark.parametrize("first, second", [("short1", "short1"), ("lettersonly", "lettersonly"),
                                           ("12345678", "12345678"), (PASSWORD, PASSWORD + "x")])
def test_rejects_weak_or_mismatched_passwords(db_session, capsys, first, second):
    assert manage.create_superadmin("owner@example.com", "Ada", "Admin", ask_password=answers(first, second)) == 1
    assert super_admins(db_session) == [] and audit_events(db_session) == []
    out = capsys.readouterr().out
    assert first not in out and second not in out


def test_promotes_an_existing_verified_account_without_touching_its_password(create_user, db_session):
    user = create_user()
    hash_before = db_session.get(User, user["user_id"]).password_hash
    assert manage.create_superadmin(user["email"], ask_password=answers()) == 1        # needs the flag
    assert manage.create_superadmin(user["email"], promote_existing=True, ask_password=answers()) == 0
    [account] = super_admins(db_session)
    assert account.user_id == user["user_id"] and account.password_hash == hash_before
    [event] = audit_events(db_session)
    assert event.details == {"mode": "promoted_existing", "previous_role": "student"}


def test_will_not_promote_an_unverified_or_deactivated_account(create_user, db_session):
    user = create_user()
    account = db_session.get(User, user["user_id"])
    account.is_active = False
    db_session.commit()
    assert manage.create_superadmin(user["email"], promote_existing=True, ask_password=answers()) == 1
    assert super_admins(db_session) == []


def test_requires_names_and_a_valid_email(db_session):
    assert manage.create_superadmin("owner@example.com", "", "Admin", ask_password=answers()) == 1
    assert manage.create_superadmin("not-an-email", "Ada", "Admin", ask_password=answers()) == 1
    assert manage.create_superadmin("new@example.com", promote_existing=True, ask_password=answers()) == 1
    assert super_admins(db_session) == []


def test_command_line_entry_point_reads_the_password_with_getpass(monkeypatch, db_session, capsys):
    ask = answers(PASSWORD, PASSWORD)
    monkeypatch.setattr(manage.getpass, "getpass", ask)
    assert manage.main(["create-superadmin", "--email", "cli@example.com",
                        "--first-name", "Cli", "--last-name", "Owner"]) == 0
    assert len(ask.prompts) == 2 and [u.email for u in super_admins(db_session)] == ["cli@example.com"]
    assert PASSWORD not in capsys.readouterr().out


def test_set_role_cannot_touch_or_grant_the_super_admin(create_user, db_session):
    manage.create_superadmin("owner@example.com", "Ada", "Admin", ask_password=answers(PASSWORD, PASSWORD))
    assert manage.set_role("owner@example.com", "student") == 1
    assert super_admins(db_session)[0].role == "super_admin"
    student = create_user()
    assert manage.set_role(student["email"], "super_admin") == 1
    with pytest.raises(SystemExit):
        manage.main(["set-role", student["email"], "super_admin"])
    assert db_session.get(User, student["user_id"]).role == "student"


def test_set_role_is_audited(create_user, db_session):
    student = create_user()
    assert manage.set_role(student["email"], "admin") == 0
    [event] = audit_events(db_session)
    assert event.action == "user.role_change" and event.actor_user_id is None
    assert event.details == {"from": "student", "to": "admin", "via": "command line"}
    assert DEFAULT_PASSWORD not in json.dumps(event.details)
