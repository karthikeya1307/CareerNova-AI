
"""add user uuid phone and role

Revision ID: 5d38d7da1031
Revises: f8af9f909ce1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5d38d7da1031'
down_revision: Union[str, Sequence[str], None] = 'f8af9f909ce1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # 1. Add UUID column temporarily nullable.
    op.add_column(
        "users",
        sa.Column("user_uuid", sa.Uuid(), nullable=True)
    )

    # 2. Generate a different UUID for every existing user.
    op.execute(
        "UPDATE users SET user_uuid = gen_random_uuid() "
        "WHERE user_uuid IS NULL"
    )

    # 3. Make UUID mandatory and generate one for future users.
    op.alter_column(
        "users",
        "user_uuid",
        existing_type=sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()")
    )

    # 4. Add optional phone number.
    op.add_column(
        "users",
        sa.Column("phone_number", sa.String(length=20), nullable=True)
    )

    # 5. Existing and future users receive the student default role.
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=30),
            server_default=sa.text("'student'"),
            nullable=False
        )
    )

    # 6. Add a named unique constraint.
    op.create_unique_constraint(
        "uq_users_user_uuid",
        "users",
        ["user_uuid"]
    )


def downgrade() -> None:

    op.drop_constraint(
        "uq_users_user_uuid",
        "users",
        type_="unique"
    )

    op.drop_column("users", "role")
    op.drop_column("users", "phone_number")
    op.drop_column("users", "user_uuid")
