"""add user email verification status

Revision ID: f8af9f909ce1
Revises: 7ecb46a3b7a7
Create Date: 2026-11-03 14:03:14.066821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8af9f909ce1'
down_revision: Union[str, Sequence[str], None] = '7ecb46a3b7a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:

    op.add_column(
        "users",
        sa.Column(
            "is_verified",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False
        )
    )

    op.alter_column(
        "users",
        "is_verified",
        existing_type=sa.Boolean(),
        server_default=sa.false(),
        existing_nullable=False
    )


def downgrade() -> None:
    op.drop_column("users", "is_verified")
