"""study documents for document-based Q&A (HR assignment)

Revision ID: f2b4d6a8c0e1
Revises: e1f3a5c7b9d2
Create Date: 2026-11-24

Upgrade (additive - no existing table or row changes):
* study_documents: one row per PDF/DOCX a student uploads for Q&A (owner, file name, type, size,
  sha256, page/section/char/chunk counts, extraction warnings). The original file is not stored.
* study_document_chunks: the extracted text in passages with page number (PDF) or section (DOCX).

Downgrade refuses while any study document exists, unless -x study_allow_data_loss=true.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "f2b4d6a8c0e1"
down_revision: Union[str, Sequence[str], None] = "e1f3a5c7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "study_documents",
        sa.Column("document_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("section_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "sha256", name="uq_study_documents_user_sha256"),
        sa.CheckConstraint("file_type IN ('pdf', 'docx')", name="ck_study_documents_file_type"),
    )
    op.create_index("ix_study_documents_user_id", "study_documents", ["user_id"])
    op.create_table(
        "study_document_chunks",
        sa.Column("chunk_id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("study_documents.document_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("document_id", "position", name="uq_study_document_chunks_position"),
    )
    op.create_index("ix_study_document_chunks_document_id", "study_document_chunks", ["document_id"])


def downgrade() -> None:
    allow = context.get_x_argument(as_dictionary=True).get("study_allow_data_loss", "").lower() == "true"
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM study_documents")).scalar()
    if count and not allow:
        raise RuntimeError(f"Refusing to drop study_documents: {count} uploaded document(s) would be lost. "
                           "Re-run with -x study_allow_data_loss=true to drop them.")
    op.drop_index("ix_study_document_chunks_document_id", table_name="study_document_chunks")
    op.drop_table("study_document_chunks")
    op.drop_index("ix_study_documents_user_id", table_name="study_documents")
    op.drop_table("study_documents")
