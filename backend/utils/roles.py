"""Role names used for authorization.

The ``users.role`` column already exists (default ``'student'``).
Keep this list in sync with any role values written to the database
(the ``ck_users_role`` CHECK constraint lists the same values).

Roles:
    student      - the default for every registered account.
    admin        - manages internships, the search index, and student accounts.
    super_admin  - exactly one account at most (enforced by a partial unique
                   index); additionally changes roles and manages admins.
                   Created only with ``python -m backend.manage create-superadmin``,
                   never through the API, and cannot be demoted, deactivated or
                   deleted through the API.
"""

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"

VALID_ROLES = frozenset({ROLE_STUDENT, ROLE_ADMIN, ROLE_SUPER_ADMIN})

# Roles with access to the administration area.
ADMIN_ROLES = frozenset({ROLE_ADMIN, ROLE_SUPER_ADMIN})

# Roles an administrator may assign through the API (super_admin never).
ASSIGNABLE_ROLES = frozenset({ROLE_STUDENT, ROLE_ADMIN})


def is_admin_role(role: str | None) -> bool:
    return role in ADMIN_ROLES


def is_super_admin_role(role: str | None) -> bool:
    return role == ROLE_SUPER_ADMIN
