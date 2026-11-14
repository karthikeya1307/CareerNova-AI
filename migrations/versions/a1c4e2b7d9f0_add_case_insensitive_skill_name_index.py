"""add case-insensitive unique index on skills.name

Revision ID: a1c4e2b7d9f0
Revises: 5d38d7da1031
Create Date: 2026-11-14

Prevents duplicate skills that differ only by case, e.g. "AWS" and "aws".
The upgrade fails safely (no partial change) if such duplicates already
exist; resolve them first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c4e2b7d9f0"
down_revision: Union[str, Sequence[str], None] = "5d38d7da1031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_skills_name_lower",
        "skills",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_skills_name_lower", table_name="skills")
