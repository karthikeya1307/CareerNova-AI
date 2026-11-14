"""Role names used for authorization.

The ``users.role`` column already exists (default ``'student'``).
Keep this list in sync with any role values written to the database.
"""

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"

VALID_ROLES = frozenset({ROLE_STUDENT, ROLE_ADMIN})
