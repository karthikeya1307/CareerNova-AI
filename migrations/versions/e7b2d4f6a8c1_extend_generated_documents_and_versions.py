"""extend generated_documents and add generated_document_versions

Revision ID: e7b2d4f6a8c1
Revises: d5a1c7e3f9b2
Create Date: 2026-11-15

Additive only: new nullable or defaulted columns and named constraints on
generated_documents, plus a new version-history table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b2d4f6a8c1"
down_revision: Union[str, Sequence[str], None] = "d5a1c7e3f9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "generated_documents"

NULLABLE_COLUMNS = [
    ("content_json", sa.JSON()),
    ("generation_method", sa.String(length=20)),
    ("llm_provider", sa.String(length=50)),
    ("llm_model", sa.String(length=100)),
    ("fact_check", sa.JSON()),
    ("ats_report", sa.JSON()),
    ("options", sa.JSON()),
]


def upgrade() -> None:
    for name, column_type in NULLABLE_COLUMNS:
        op.add_column(TABLE, sa.Column(name, column_type, nullable=True))
    op.add_column(TABLE, sa.Column(
        "current_version", sa.Integer(), server_default=sa.text("1"), nullable=False))
    op.add_column(TABLE, sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))

    op.create_check_constraint(
        "ck_generated_documents_type", TABLE, "document_type IN ('resume', 'cover_letter')")
    op.create_check_constraint(
        "ck_generated_documents_method", TABLE,
        "generation_method IN ('deterministic', 'llm')")
    op.create_check_constraint(
        "ck_generated_documents_version_positive", TABLE, "current_version >= 1")

    op.create_table(
        "generated_document_versions",
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("fact_check", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('generated', 'edited', 'restored')",
                           name="ck_generated_document_versions_source"),
        sa.ForeignKeyConstraint(["document_id"], ["generated_documents.document_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint("document_id", "version", name="uq_generated_document_version"),
    )
    op.create_index(op.f("ix_generated_document_versions_document_id"),
                    "generated_document_versions", ["document_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_generated_document_versions_document_id"),
                  table_name="generated_document_versions")
    op.drop_table("generated_document_versions")

    for name in ("ck_generated_documents_version_positive", "ck_generated_documents_method",
                 "ck_generated_documents_type"):
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_column(TABLE, "updated_at")
    op.drop_column(TABLE, "current_version")
    for name, _ in reversed(NULLABLE_COLUMNS):
        op.drop_column(TABLE, name)
