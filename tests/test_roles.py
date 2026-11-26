"""Role-based authorization tests."""

import pytest

from backend import manage
from backend.models import User
from backend.utils.dependencies import require_roles


def test_admin_endpoints_require_authentication(client):
    assert client.get("/admin/users").status_code == 401


def test_student_cannot_access_admin_endpoints(client, create_user):
    student = create_user()

    assert client.get(
        "/admin/users", headers=student["headers"]
    ).status_code == 403

    assert client.patch(
        f"/admin/users/{student['user_id']}/role",
        headers=student["headers"],
        json={"role": "admin"},
    ).status_code == 403


def test_admin_can_list_users(client, create_user):
    admin = create_user(role="admin")
    create_user()

    response = client.get("/admin/users", headers=admin["headers"])
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 2
    assert {u["role"] for u in users} == {"admin", "student"}


def test_super_admin_can_change_role(client, create_user):
    # Account security: role changes are reserved for the super admin.
    super_admin = create_user(role="super_admin")
    student = create_user()

    response = client.patch(
        f"/admin/users/{student['user_id']}/role",
        headers=super_admin["headers"],
        json={"role": "ADMIN"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    # Promoted user can now reach admin endpoints.
    assert client.get(
        "/admin/users", headers=student["headers"]
    ).status_code == 200


def test_admin_can_no_longer_change_roles(client, create_user):
    admin = create_user(role="admin")
    student = create_user()

    response = client.patch(
        f"/admin/users/{student['user_id']}/role",
        headers=admin["headers"],
        json={"role": "admin"},
    )
    assert response.status_code == 403


def test_invalid_role_is_rejected(client, create_user):
    super_admin = create_user(role="super_admin")
    student = create_user()

    response = client.patch(
        f"/admin/users/{student['user_id']}/role",
        headers=super_admin["headers"],
        json={"role": "superuser"},
    )
    assert response.status_code == 422


def test_admin_cannot_demote_self(client, create_user):
    admin = create_user(role="admin")

    response = client.patch(
        f"/admin/users/{admin['user_id']}/role",
        headers=admin["headers"],
        json={"role": "student"},
    )
    assert response.status_code == 403          # admins cannot change roles at all


def test_super_admin_cannot_demote_self(client, create_user):
    super_admin = create_user(role="super_admin")

    response = client.patch(
        f"/admin/users/{super_admin['user_id']}/role",
        headers=super_admin["headers"],
        json={"role": "student"},
    )
    assert response.status_code == 403          # the super admin account is protected


def test_role_change_for_missing_user(client, create_user):
    super_admin = create_user(role="super_admin")

    response = client.patch(
        "/admin/users/9999/role",
        headers=super_admin["headers"],
        json={"role": "student"},
    )
    assert response.status_code == 404


def test_require_roles_rejects_unknown_roles():
    with pytest.raises(ValueError):
        require_roles("superuser")

    with pytest.raises(ValueError):
        require_roles()


def test_manage_set_role_command(create_user, db_session):
    student = create_user()

    assert manage.main(["set-role", student["email"].upper(), "admin"]) == 0

    db_session.expire_all()
    assert db_session.get(User, student["user_id"]).role == "admin"

    assert manage.set_role("missing@example.com", "admin") == 1
