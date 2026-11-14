"""Command-line management tasks.

Usage:
    python -m backend.manage set-role <email> <role>
    python -m backend.manage backfill-skills            # dry run (default)
    python -m backend.manage backfill-skills --apply    # write changes

Example (bootstrap the first administrator):
    python -m backend.manage set-role admin@example.com admin
"""

import argparse
import sys

from sqlalchemy import func, select

from backend.database import SessionLocal
from backend.models import Resume, ResumeExtraction, ResumeSkill, Skill, User
from backend.services.resume_skills import sync_resume_skills
from backend.services.skill_normalizer import normalize_extracted_skills
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


def backfill_skills(apply: bool = False) -> int:
    """Link normalized skills to existing resumes.

    Uses each resume's latest successful extraction (no re-parsing).
    Dry run by default: prints the plan and rolls back. Safe to repeat.
    Output contains only IDs and skill names, no personal data.
    """

    mode = "APPLY" if apply else "DRY RUN (no changes written)"
    print(f"Backfill resume skills - {mode}")

    with SessionLocal() as db:
        existing_skill_keys = {
            name.casefold() for name in db.scalars(select(Skill.name))
        }
        new_skill_names: dict[str, str] = {}
        processed = skipped = 0

        resumes = db.scalars(select(Resume).order_by(Resume.resume_id)).all()

        for resume in resumes:
            extraction = db.scalar(
                select(ResumeExtraction)
                .where(
                    ResumeExtraction.resume_id == resume.resume_id,
                    ResumeExtraction.status == "completed",
                )
                .order_by(
                    ResumeExtraction.created_at.desc(),
                    ResumeExtraction.extraction_id.desc(),
                )
                .limit(1)
            )

            if extraction is None:
                print(f"- resume {resume.resume_id}: no completed extraction, skipped")
                skipped += 1
                continue

            normalized = normalize_extracted_skills(extraction.extracted_data)
            current_links = db.scalar(
                select(func.count()).select_from(ResumeSkill)
                .where(ResumeSkill.resume_id == resume.resume_id)
            )

            known = [s.name for s in normalized if s.is_known]
            unknown = [s.name for s in normalized if not s.is_known]
            changed = [
                f"{s.raw.strip()}->{s.name}"
                for s in normalized if s.raw.strip() != s.name
            ]

            for skill in normalized:
                key = skill.name.casefold()
                if key not in existing_skill_keys:
                    new_skill_names.setdefault(key, skill.name)

            print(
                f"- resume {resume.resume_id}: {len(normalized)} skills "
                f"(existing links: {current_links})"
            )
            print(f"    known:      {', '.join(known) or '-'}")
            print(f"    other:      {', '.join(unknown) or '-'}")
            print(f"    normalized: {', '.join(changed) or '-'}")

            if apply:
                sync_resume_skills(db, resume.resume_id, extraction.extracted_data)

            processed += 1

        print(
            f"Summary: {processed} resumes processed, {skipped} skipped, "
            f"{len(new_skill_names)} new skill rows "
            f"{'created' if apply else 'would be created'}."
        )

        if apply:
            db.commit()
        else:
            db.rollback()

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.manage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    role_parser = subparsers.add_parser("set-role", help="Change a user's role")
    role_parser.add_argument("email")
    role_parser.add_argument("role", choices=sorted(VALID_ROLES))

    backfill_parser = subparsers.add_parser(
        "backfill-skills",
        help="Link normalized skills to existing resumes (dry run by default)",
    )
    backfill_parser.add_argument(
        "--apply", action="store_true",
        help="Write changes. Without this flag nothing is saved.",
    )

    args = parser.parse_args(argv)

    if args.command == "set-role":
        return set_role(args.email, args.role)

    if args.command == "backfill-skills":
        return backfill_skills(apply=args.apply)

    return 1


if __name__ == "__main__":
    sys.exit(main())
