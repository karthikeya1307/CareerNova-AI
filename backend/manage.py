"""Command-line management tasks.

Usage:
    python -m backend.manage set-role <email> <role>

Example (bootstrap the first administrator):
    python -m backend.manage set-role admin@example.com admin
"""

import argparse
import sys

from sqlalchemy import func, select

from backend.database import SessionLocal
from backend.models import User
from backend.utils.roles import VALID_ROLES


def set_role(email: str, role: str) -> int:
    role = role.strip().lower()

    if role not in VALID_ROLES:
        print(f"Invalid role. Choose one of: {', '.join(sorted(VALID_ROLES))}")
        return 1

    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )

        if user is None:
            print("No user found with that email.")
            return 1

        user.role = role
        db.commit()
        print(f"User {user.user_id} role set to '{role}'.")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.manage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    role_parser = subparsers.add_parser("set-role", help="Change a user's role")
    role_parser.add_argument("email")
    role_parser.add_argument("role", choices=sorted(VALID_ROLES))

    args = parser.parse_args(argv)

    if args.command == "set-role":
        return set_role(args.email, args.role)

    return 1


if __name__ == "__main__":
    sys.exit(main())
