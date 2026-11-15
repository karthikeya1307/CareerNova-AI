"""extend skill_gap_recommendations for skill-gap analysis

Revision ID: d5a1c7e3f9b2
Revises: c4f8a9e2b6d1
Create Date: 2026-11-15

Additive only: new nullable or defaulted columns, named constraints and
indexes. Existing columns are unchanged. The check constraints accept the
values already used by the original schema ('pending', 'identified').
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5a1c7e3f9b2"
down_revision: Union[str, Sequence[str], None] = "c4f8a9e2b6d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "skill_gap_recommendations"

NULLABLE_COLUMNS = [
    ("importance", sa.String(length=20)),
    ("priority_score", sa.Float()),
    ("demand_count", sa.Integer()),
    ("internship_ids", sa.JSON()),
    ("related_skills", sa.JSON()),
    ("learning_plan", sa.JSON()),
    ("learning_plan_version", sa.String(length=20)),
    ("source", sa.String(length=30)),
    ("source_run_id", sa.Uuid()),
    ("completed_via", sa.String(length=20)),
    ("started_at", sa.DateTime(timezone=True)),
    ("completed_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("resume_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "skill_gap_recommendations_resume_id_fkey", TABLE, "resumes",
        ["resume_id"], ["resume_id"], ondelete="CASCADE",
    )
    op.create_index(op.f("ix_skill_gap_recommendations_resume_id"), TABLE, ["resume_id"])

    for name, column_type in NULLABLE_COLUMNS:
        op.add_column(TABLE, sa.Column(name, column_type, nullable=True))

    op.add_column(TABLE, sa.Column(
        "is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column(TABLE, sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))

    op.create_check_constraint(
        "ck_skill_gap_status", TABLE,
        "status IN ('pending', 'in_progress', 'completed', 'dismissed')")
    op.create_check_constraint(
        "ck_skill_gap_level", TABLE,
        "gap_level IN ('identified', 'missing', 'partial')")
    op.create_check_constraint(
        "ck_skill_gap_importance", TABLE, "importance IN ('required', 'preferred')")
    op.create_check_constraint(
        "ck_skill_gap_priority_range", TABLE,
        "priority_score >= 0 AND priority_score <= 100")
    op.create_check_constraint(
        "ck_skill_gap_completed_via", TABLE, "completed_via IN ('user', 'resume')")
    op.create_unique_constraint(
        "uq_skill_gap_user_resume_skill", TABLE, ["user_id", "resume_id", "skill_id"])
    op.create_index("ix_skill_gap_user_status", TABLE, ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_skill_gap_user_status", table_name=TABLE)
    op.drop_constraint("uq_skill_gap_user_resume_skill", TABLE, type_="unique")
    for name in ("ck_skill_gap_completed_via", "ck_skill_gap_priority_range",
                 "ck_skill_gap_importance", "ck_skill_gap_level", "ck_skill_gap_status"):
        op.drop_constraint(name, TABLE, type_="check")

    op.drop_column(TABLE, "updated_at")
    op.drop_column(TABLE, "is_current")
    for name, _ in reversed(NULLABLE_COLUMNS):
        op.drop_column(TABLE, name)

    op.drop_index(op.f("ix_skill_gap_recommendations_resume_id"), table_name=TABLE)
    op.drop_constraint("skill_gap_recommendations_resume_id_fkey", TABLE, type_="foreignkey")
    op.drop_column(TABLE, "resume_id")
