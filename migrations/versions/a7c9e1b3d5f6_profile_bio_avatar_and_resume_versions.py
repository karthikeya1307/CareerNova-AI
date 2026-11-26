"""profile bio and picture, resume version names and preferred resume

Revision ID: a7c9e1b3d5f6
Revises: f2b4d6a8c0e1
Create Date: 2026-11-25

Upgrade (additive - every existing row keeps its values; new columns are empty / false):
* student_profiles: bio, avatar_path, avatar_content_type, avatar_updated_at (all NULL);
* resumes: label (NULL) and is_preferred (false), plus a partial unique index so a student has at most
  one preferred resume. Without a preferred resume the app keeps using the latest parsed one (as before).

Downgrade refuses while any bio, picture, resume name or preferred resume exists, unless
-x profile_allow_data_loss=true (uploaded picture files are never deleted by a migration).
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "a7c9e1b3d5f6"
down_revision: Union[str, Sequence[str], None] = "f2b4d6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student_profiles", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("student_profiles", sa.Column("avatar_path", sa.String(length=500), nullable=True))
    op.add_column("student_profiles", sa.Column("avatar_content_type", sa.String(length=30), nullable=True))
    op.add_column("student_profiles", sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("resumes", sa.Column("label", sa.String(length=120), nullable=True))
    op.add_column("resumes", sa.Column("is_preferred", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_index("uq_resumes_one_preferred_per_user", "resumes", ["user_id"], unique=True,
                    postgresql_where=sa.text("is_preferred"))


def downgrade() -> None:
    allow = context.get_x_argument(as_dictionary=True).get("profile_allow_data_loss", "").lower() == "true"
    bind = op.get_bind()
    used = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM student_profiles WHERE bio IS NOT NULL OR avatar_path IS NOT NULL) + "
        "(SELECT count(*) FROM resumes WHERE label IS NOT NULL OR is_preferred)")).scalar()
    if used and not allow:
        raise RuntimeError(f"Refusing to downgrade the profile/resume-version migration: {used} row(s) have a bio, "
                           "picture, resume name or preferred resume. Re-run with -x profile_allow_data_loss=true.")
    op.drop_index("uq_resumes_one_preferred_per_user", table_name="resumes")
    op.drop_column("resumes", "is_preferred")
    op.drop_column("resumes", "label")
    op.drop_column("student_profiles", "avatar_updated_at")
    op.drop_column("student_profiles", "avatar_content_type")
    op.drop_column("student_profiles", "avatar_path")
    op.drop_column("student_profiles", "bio")
