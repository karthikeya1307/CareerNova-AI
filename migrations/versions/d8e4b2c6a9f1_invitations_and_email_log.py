"""invitations and email delivery log

Revision ID: d8e4b2c6a9f1
Revises: c6d2a8f4b1e3
Create Date: 2026-11-19

Upgrade (additive; no existing row changes):
* user_invitations: single-use, expiring account-activation links (token stored as SHA-256 hash
  only), with the delivery status of the invitation email;
* email_deliveries: outcome of every email attempt (kind, recipient, status, error code) - no
  message body, links or tokens.

Downgrade refuses (and changes nothing) while either table has rows, unless run with
-x invitations_allow_data_loss=true. Pending accounts keep working either way; they just lose
their outstanding invitation links.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "d8e4b2c6a9f1"
down_revision: Union[str, Sequence[str], None] = "c6d2a8f4b1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_invitations",
        sa.Column("invitation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("delivery_error", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("invitation_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_user_invitations_user", "user_invitations", ["user_id"])
    op.create_index("ix_user_invitations_created_at", "user_invitations", ["created_at"])

    op.create_table(
        "email_deliveries",
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("invitation_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('sent', 'outboxed', 'skipped', 'failed')", name="ck_email_deliveries_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invitation_id"], ["user_invitations.invitation_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("delivery_id"),
    )
    op.create_index("ix_email_deliveries_created_at", "email_deliveries", ["created_at"])
    op.create_index("ix_email_deliveries_user", "email_deliveries", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    allow = context.get_x_argument(as_dictionary=True).get("invitations_allow_data_loss", "").lower() == "true"
    counts = {
        "invitations": bind.execute(sa.text("SELECT count(*) FROM user_invitations")).scalar(),
        "email delivery records": bind.execute(sa.text("SELECT count(*) FROM email_deliveries")).scalar(),
    }
    counts = {k: v for k, v in counts.items() if v}
    if counts and not allow:
        raise RuntimeError(
            "Refusing to downgrade the invitations migration: it would drop "
            + ", ".join(f"{n} {label}" for label, n in counts.items())
            + ". Nothing was changed. Re-run with -x invitations_allow_data_loss=true to proceed.")
    op.drop_index("ix_email_deliveries_user", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_created_at", table_name="email_deliveries")
    op.drop_table("email_deliveries")
    op.drop_index("ix_user_invitations_created_at", table_name="user_invitations")
    op.drop_index("ix_user_invitations_user", table_name="user_invitations")
    op.drop_table("user_invitations")
