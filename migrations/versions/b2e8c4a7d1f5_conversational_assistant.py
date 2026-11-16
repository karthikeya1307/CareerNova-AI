"""conversational assistant: extend conversations/messages, add rate limits

Revision ID: b2e8c4a7d1f5
Revises: a9d3f6b2c8e4
Create Date: 2026-11-15

Upgrade (additive; the original columns and constraints are unchanged):
* conversations: resume_id (FK resumes, ON DELETE SET NULL), context JSON
  (pointers only), message_count, last_message_at, index (user_id, updated_at);
* messages: resume_id (FK resumes, ON DELETE CASCADE - turns that used a
  deleted resume are removed with it), intent, entities, result_set,
  suggested_actions, generation_method (CHECK deterministic/llm),
  llm_provider, llm_model, fact_check, warnings, index
  (conversation_id, message_id);
* assistant_rate_limits: atomic per-user counters.

Downgrade refuses (and changes nothing) while any Phase 8 data exists,
unless run with ``-x phase8_allow_data_loss=true``. Even then it only drops
the Phase 8 columns and the rate-limit table: conversation titles, message
text and sources (the original columns) are kept, and no other table is
touched.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "b2e8c4a7d1f5"
down_revision: Union[str, Sequence[str], None] = "a9d3f6b2c8e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONVERSATION_COLUMNS = [
    ("context", sa.JSON()),
    ("last_message_at", sa.DateTime(timezone=True)),
]
MESSAGE_COLUMNS = [
    ("intent", sa.String(length=40)),
    ("entities", sa.JSON()),
    ("result_set", sa.JSON()),
    ("suggested_actions", sa.JSON()),
    ("generation_method", sa.String(length=20)),
    ("llm_provider", sa.String(length=50)),
    ("llm_model", sa.String(length=100)),
    ("fact_check", sa.JSON()),
    ("warnings", sa.JSON()),
]


def upgrade() -> None:
    op.add_column("conversations", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.create_foreign_key("conversations_resume_id_fkey", "conversations", "resumes",
                          ["resume_id"], ["resume_id"], ondelete="SET NULL")
    op.create_index(op.f("ix_conversations_resume_id"), "conversations", ["resume_id"])
    for name, column_type in CONVERSATION_COLUMNS:
        op.add_column("conversations", sa.Column(name, column_type, nullable=True))
    op.add_column("conversations", sa.Column("message_count", sa.Integer(), server_default="0", nullable=False))
    op.execute("UPDATE conversations c SET message_count = "
               "(SELECT count(*) FROM messages m WHERE m.conversation_id = c.conversation_id)")
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])

    op.add_column("messages", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.create_foreign_key("messages_resume_id_fkey", "messages", "resumes",
                          ["resume_id"], ["resume_id"], ondelete="CASCADE")
    op.create_index(op.f("ix_messages_resume_id"), "messages", ["resume_id"])
    for name, column_type in MESSAGE_COLUMNS:
        op.add_column("messages", sa.Column(name, column_type, nullable=True))
    op.create_check_constraint("ck_messages_generation_method", "messages",
                               "generation_method IN ('deterministic', 'llm')")
    op.create_index("ix_messages_conversation_message", "messages", ["conversation_id", "message_id"])

    op.create_table(
        "assistant_rate_limits",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("bucket", sa.String(length=20), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("user_id", "bucket", "window_start"),
        sa.CheckConstraint("bucket IN ('minute', 'day', 'llm_hour')", name="ck_assistant_rate_limits_bucket"),
        sa.CheckConstraint("count >= 0", name="ck_assistant_rate_limits_count"),
    )
    op.create_index("ix_assistant_rate_limits_window", "assistant_rate_limits", ["window_start"])


def phase8_data_counts(bind) -> dict[str, int]:
    """Phase 8 data a downgrade would drop (message text and titles always survive)."""
    queries = {
        "conversations with Phase 8 details":
            "SELECT count(*) FROM conversations WHERE resume_id IS NOT NULL OR context IS NOT NULL "
            "OR last_message_at IS NOT NULL",
        "messages with Phase 8 details":
            "SELECT count(*) FROM messages WHERE resume_id IS NOT NULL OR intent IS NOT NULL "
            "OR generation_method IS NOT NULL OR result_set IS NOT NULL",
    }
    return {label: bind.execute(sa.text(sql)).scalar() for label, sql in queries.items()}


def downgrade() -> None:
    bind = op.get_bind()
    allow = context.get_x_argument(as_dictionary=True).get("phase8_allow_data_loss", "").lower() == "true"
    counts = {k: v for k, v in phase8_data_counts(bind).items() if v}
    if counts and not allow:
        raise RuntimeError(
            "Refusing to downgrade Phase 8: it would drop Phase 8 data ("
            + ", ".join(f"{n} {label}" for label, n in counts.items())
            + "). Nothing was changed. Re-run with -x phase8_allow_data_loss=true to drop only the Phase 8 "
              "columns (message text and conversation titles are kept).")

    op.drop_index("ix_assistant_rate_limits_window", table_name="assistant_rate_limits")
    op.drop_table("assistant_rate_limits")

    op.drop_index("ix_messages_conversation_message", table_name="messages")
    op.drop_constraint("ck_messages_generation_method", "messages", type_="check")
    for name, _ in reversed(MESSAGE_COLUMNS):
        op.drop_column("messages", name)
    op.drop_index(op.f("ix_messages_resume_id"), table_name="messages")
    op.drop_constraint("messages_resume_id_fkey", "messages", type_="foreignkey")
    op.drop_column("messages", "resume_id")

    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_column("conversations", "message_count")
    for name, _ in reversed(CONVERSATION_COLUMNS):
        op.drop_column("conversations", name)
    op.drop_index(op.f("ix_conversations_resume_id"), table_name="conversations")
    op.drop_constraint("conversations_resume_id_fkey", "conversations", type_="foreignkey")
    op.drop_column("conversations", "resume_id")
