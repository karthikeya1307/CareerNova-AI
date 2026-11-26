"""skill progress and job-source tracking

Revision ID: e1f3a5c7b9d2
Revises: d8e4b2c6a9f1
Create Date: 2026-11-24

Upgrade (additive):
* skill_progress: one row per (student, skill) with status not_started | learning | practiced |
  completed;
* internships: source_url, posted_at, last_verified_at (all NULL = unknown; nothing is guessed) and
  dedup_key (sha256 of the normalised "title|company|location"), backfilled for existing rows.

No existing value is changed. Downgrade refuses while skill progress exists or any listing has a
source URL / posted date / verification date, unless -x jobs_allow_data_loss=true.
"""
import hashlib
import re
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "e1f3a5c7b9d2"
down_revision: Union[str, Sequence[str], None] = "d8e4b2c6a9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def dedup_key(title: str | None, company: str | None, location: str | None) -> str:
    """Same rule as backend/services/job_sources.dedup_key (kept here so the migration is self-contained)."""
    def norm(value):
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return hashlib.sha256(f"{norm(title)}|{norm(company)}|{norm(location)}".encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.create_table(
        "skill_progress",
        sa.Column("progress_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="not_started", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('not_started', 'learning', 'practiced', 'completed')",
                           name="ck_skill_progress_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("progress_id"),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_skill_progress_user_skill"),
    )
    op.create_index(op.f("ix_skill_progress_user_id"), "skill_progress", ["user_id"])

    op.add_column("internships", sa.Column("source_url", sa.String(length=1000), nullable=True))
    op.add_column("internships", sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("internships", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("internships", sa.Column("dedup_key", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_internships_dedup_key"), "internships", ["dedup_key"])

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT internship_id, title, company, location FROM internships")).all()
    for row in rows:
        bind.execute(sa.text("UPDATE internships SET dedup_key = :key WHERE internship_id = :id"),
                     {"key": dedup_key(row.title, row.company, row.location), "id": row.internship_id})


def downgrade() -> None:
    bind = op.get_bind()
    allow = context.get_x_argument(as_dictionary=True).get("jobs_allow_data_loss", "").lower() == "true"
    counts = {
        "skill progress rows": bind.execute(sa.text("SELECT count(*) FROM skill_progress")).scalar(),
        "listings with source details": bind.execute(sa.text(
            "SELECT count(*) FROM internships WHERE source_url IS NOT NULL OR posted_at IS NOT NULL "
            "OR last_verified_at IS NOT NULL")).scalar(),
    }
    counts = {k: v for k, v in counts.items() if v}
    if counts and not allow:
        raise RuntimeError(
            "Refusing to downgrade the skill-progress/job-source migration: it would drop "
            + ", ".join(f"{n} {label}" for label, n in counts.items())
            + ". Nothing was changed. Re-run with -x jobs_allow_data_loss=true to proceed.")
    op.drop_index(op.f("ix_internships_dedup_key"), table_name="internships")
    for column in ("dedup_key", "last_verified_at", "posted_at", "source_url"):
        op.drop_column("internships", column)
    op.drop_index(op.f("ix_skill_progress_user_id"), table_name="skill_progress")
    op.drop_table("skill_progress")
