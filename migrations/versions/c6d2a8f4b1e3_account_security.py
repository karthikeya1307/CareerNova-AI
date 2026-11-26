"""account security: super admin role, deactivation, audit log, login throttling

Revision ID: c6d2a8f4b1e3
Revises: b2e8c4a7d1f5
Create Date: 2026-11-19

Upgrade (additive; no existing row is changed except that every user gets
is_active = true):
* users: is_active (NOT NULL, default true), deactivated_at, last_login_at;
  CHECK ck_users_role (student, admin, super_admin) - the upgrade first
  verifies the existing values and refuses, changing nothing, if any other
  role is stored; partial unique index uq_users_single_super_admin so at most
  one super admin can exist;
* admin_audit_events: append-only audit log (actor and target set to NULL
  if the user is deleted, so the record survives);
* auth_rate_limits: atomic failed-sign-in counters (email keys hashed).

Downgrade refuses (and changes nothing) while it would lose security state:
audit events, a super admin, or deactivated accounts (dropping is_active
would silently re-enable them). With -x accounts_allow_data_loss=true it drops
the Phase 1 tables/columns, turns a super admin back into an admin, and
leaves every other table untouched.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "c6d2a8f4b1e3"
down_revision: Union[str, Sequence[str], None] = "b2e8c4a7d1f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALLOWED_ROLES = ("student", "admin", "super_admin")


def upgrade() -> None:
    bind = op.get_bind()
    unknown = bind.execute(sa.text(
        "SELECT DISTINCT role FROM users WHERE role NOT IN ('student', 'admin', 'super_admin')"
    )).scalars().all()
    if unknown:
        raise RuntimeError(
            "Refusing to upgrade: users.role contains values outside "
            f"{ALLOWED_ROLES}: {sorted(unknown)}. Nothing was changed. Fix those rows first.")

    op.add_column("users", sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_users_role", "users", "role IN ('student', 'admin', 'super_admin')")
    op.create_index("uq_users_single_super_admin", "users", ["role"], unique=True,
                    postgresql_where=sa.text("role = 'super_admin'"))

    op.create_table(
        "admin_audit_events",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=30), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("target_label", sa.String(length=300), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"])
    op.create_index("ix_admin_audit_events_actor", "admin_audit_events", ["actor_user_id"])
    op.create_index("ix_admin_audit_events_target", "admin_audit_events", ["target_user_id"])
    op.create_index("ix_admin_audit_events_action", "admin_audit_events", ["action"])

    op.create_table(
        "auth_rate_limits",
        sa.Column("bucket", sa.String(length=20), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("bucket IN ('login_email', 'login_ip')", name="ck_auth_rate_limits_bucket"),
        sa.CheckConstraint("count >= 0", name="ck_auth_rate_limits_count"),
        sa.PrimaryKeyConstraint("bucket", "key_hash", "window_start"),
    )
    op.create_index("ix_auth_rate_limits_window", "auth_rate_limits", ["window_start"])


def security_state_counts(bind) -> dict[str, int]:
    return {
        "audit events": bind.execute(sa.text("SELECT count(*) FROM admin_audit_events")).scalar(),
        "super admin accounts": bind.execute(sa.text(
            "SELECT count(*) FROM users WHERE role = 'super_admin'")).scalar(),
        "deactivated accounts": bind.execute(sa.text(
            "SELECT count(*) FROM users WHERE is_active = false")).scalar(),
    }


def downgrade() -> None:
    bind = op.get_bind()
    allow = context.get_x_argument(as_dictionary=True).get("accounts_allow_data_loss", "").lower() == "true"
    counts = {k: v for k, v in security_state_counts(bind).items() if v}
    if counts and not allow:
        raise RuntimeError(
            "Refusing to downgrade the account-security migration: it would lose security state ("
            + ", ".join(f"{n} {label}" for label, n in counts.items())
            + "). Deactivated accounts would become usable again. Nothing was changed. Re-run with "
              "-x accounts_allow_data_loss=true to proceed (a super admin becomes an admin).")

    op.drop_index("ix_auth_rate_limits_window", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
    for name in ("ix_admin_audit_events_action", "ix_admin_audit_events_target",
                 "ix_admin_audit_events_actor", "ix_admin_audit_events_created_at"):
        op.drop_index(name, table_name="admin_audit_events")
    op.drop_table("admin_audit_events")

    op.drop_index("uq_users_single_super_admin", table_name="users")
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'super_admin'")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "is_active")
