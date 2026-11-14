"""add internship metadata and knowledge-document index tracking

Revision ID: b7e3d1f4a2c8
Revises: a1c4e2b7d9f0
Create Date: 2026-11-15

Additive only: new nullable/defaulted columns and named constraints.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e3d1f4a2c8"
down_revision: Union[str, Sequence[str], None] = "a1c4e2b7d9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- internships ----------------
    op.add_column("internships", sa.Column("external_id", sa.String(length=64), nullable=True))
    op.add_column("internships", sa.Column("domain", sa.String(length=80), nullable=True))
    op.add_column("internships", sa.Column("work_mode", sa.String(length=20), nullable=True))
    op.add_column("internships", sa.Column("duration_weeks", sa.Integer(), nullable=True))
    op.add_column("internships", sa.Column("stipend_per_month", sa.Integer(), nullable=True))
    op.add_column(
        "internships",
        sa.Column("stipend_currency", sa.String(length=3),
                  server_default=sa.text("'INR'"), nullable=False),
    )
    op.add_column("internships", sa.Column("min_education", sa.String(length=200), nullable=True))
    op.add_column(
        "internships",
        sa.Column("source", sa.String(length=30),
                  server_default=sa.text("'manual'"), nullable=False),
    )

    op.create_unique_constraint(
        "internships_external_id_key", "internships", ["external_id"]
    )
    op.create_index(
        op.f("ix_internships_domain"), "internships", ["domain"], unique=False
    )
    op.create_check_constraint(
        "ck_internships_work_mode", "internships",
        "work_mode IN ('Onsite', 'Hybrid', 'Remote')",
    )
    op.create_check_constraint(
        "ck_internships_duration_positive", "internships", "duration_weeks > 0"
    )
    op.create_check_constraint(
        "ck_internships_stipend_non_negative", "internships",
        "stipend_per_month >= 0",
    )
    op.create_check_constraint(
        "ck_internships_source", "internships",
        "source IN ('dataset', 'admin', 'manual')",
    )

    # ---------------- internship_skills ----------------
    op.create_check_constraint(
        "ck_internship_skills_importance", "internship_skills",
        "importance IN ('required', 'preferred')",
    )

    # ---------------- knowledge_documents ----------------
    op.add_column("knowledge_documents", sa.Column("content", sa.Text(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("embedding_model", sa.String(length=200), nullable=True))
    op.add_column("knowledge_documents", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_knowledge_document_internship_source",
        "knowledge_documents",
        ["internship_id", "source_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_knowledge_document_internship_source", "knowledge_documents", type_="unique"
    )
    op.drop_column("knowledge_documents", "error_message")
    op.drop_column("knowledge_documents", "embedding_model")
    op.drop_column("knowledge_documents", "content")

    op.drop_constraint("ck_internship_skills_importance", "internship_skills", type_="check")

    op.drop_constraint("ck_internships_source", "internships", type_="check")
    op.drop_constraint("ck_internships_stipend_non_negative", "internships", type_="check")
    op.drop_constraint("ck_internships_duration_positive", "internships", type_="check")
    op.drop_constraint("ck_internships_work_mode", "internships", type_="check")
    op.drop_index(op.f("ix_internships_domain"), table_name="internships")
    op.drop_constraint("internships_external_id_key", "internships", type_="unique")

    op.drop_column("internships", "source")
    op.drop_column("internships", "min_education")
    op.drop_column("internships", "stipend_currency")
    op.drop_column("internships", "stipend_per_month")
    op.drop_column("internships", "duration_weeks")
    op.drop_column("internships", "work_mode")
    op.drop_column("internships", "domain")
    op.drop_column("internships", "external_id")
