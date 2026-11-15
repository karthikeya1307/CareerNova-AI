"""extend match_results for compatibility scoring runs

Revision ID: c4f8a9e2b6d1
Revises: b7e3d1f4a2c8
Create Date: 2026-11-15

Additive only: nullable columns, named constraints and indexes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f8a9e2b6d1"
down_revision: Union[str, Sequence[str], None] = "b7e3d1f4a2c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = [
    ("run_id", sa.Uuid()),
    ("rank", sa.Integer()),
    ("label", sa.String(length=20)),
    ("algorithm_version", sa.String(length=20)),
    ("skill_score", sa.Float()),
    ("semantic_score", sa.Float()),
    ("education_score", sa.Float()),
    ("location_score", sa.Float()),
    ("required_skill_coverage", sa.Float()),
    ("data_completeness", sa.Float()),
    ("breakdown", sa.JSON()),
]


def upgrade() -> None:
    for name, column_type in NEW_COLUMNS:
        op.add_column("match_results", sa.Column(name, column_type, nullable=True))

    op.create_index(
        op.f("ix_match_results_run_id"), "match_results", ["run_id"], unique=False
    )
    op.create_index(
        "ix_match_results_resume_created", "match_results",
        ["resume_id", "created_at"], unique=False,
    )
    op.create_unique_constraint(
        "uq_match_results_run_internship", "match_results",
        ["run_id", "internship_id"],
    )
    op.create_check_constraint(
        "ck_match_results_score_range", "match_results",
        "score >= 0 AND score <= 100",
    )
    op.create_check_constraint(
        "ck_match_results_label", "match_results",
        "label IN ('Excellent', 'Strong', 'Fair', 'Weak')",
    )
    op.create_check_constraint(
        "ck_match_results_completeness_range", "match_results",
        "data_completeness >= 0 AND data_completeness <= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_match_results_completeness_range", "match_results", type_="check")
    op.drop_constraint("ck_match_results_label", "match_results", type_="check")
    op.drop_constraint("ck_match_results_score_range", "match_results", type_="check")
    op.drop_constraint("uq_match_results_run_internship", "match_results", type_="unique")
    op.drop_index("ix_match_results_resume_created", table_name="match_results")
    op.drop_index(op.f("ix_match_results_run_id"), table_name="match_results")

    for name, _ in reversed(NEW_COLUMNS):
        op.drop_column("match_results", name)
