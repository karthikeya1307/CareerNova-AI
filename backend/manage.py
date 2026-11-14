"""Command-line management tasks.

Usage:
    python -m backend.manage set-role <email> <role>
    python -m backend.manage backfill-skills            # dry run (default)
    python -m backend.manage backfill-skills --apply    # write changes
    python -m backend.manage validate-internships       # no database access
    python -m backend.manage seed-internships [--apply]
    python -m backend.manage rebuild-index [--apply]
    python -m backend.manage index-status
    python -m backend.manage download-embedding-model   # one-time, network

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


def _print_validation(report) -> None:
    print(
        f"Records: {report.total} | valid: {len(report.valid)} | "
        f"errors: {len(report.errors)} | duplicate ids: {len(report.duplicate_ids)}"
    )
    print(f"Distinct canonical skills: {report.skill_count}")
    print(f"Unmapped skills: {report.unmapped_skills or 'none'}")
    print(f"Stipend range (INR/month): {report.stipend_range}")
    for error in report.errors[:20]:
        print(f"  ERROR {error}")
    for duplicate in report.duplicate_ids[:20]:
        print(f"  DUPLICATE id {duplicate}")


def validate_internships(path: str | None = None) -> int:
    from pathlib import Path

    from backend.services.internship_seed import (
        DEFAULT_DATASET_PATH, load_dataset, validate_records,
    )

    report = validate_records(load_dataset(Path(path) if path else DEFAULT_DATASET_PATH))
    _print_validation(report)
    print("Dataset is valid." if report.ok else "Dataset is NOT valid.")
    return 0 if report.ok else 1


def seed_internships_command(apply: bool = False, path: str | None = None) -> int:
    from pathlib import Path

    from backend.services.internship_seed import (
        DEFAULT_DATASET_PATH, load_dataset, seed_internships, validate_records,
    )

    report = validate_records(load_dataset(Path(path) if path else DEFAULT_DATASET_PATH))
    _print_validation(report)
    if not report.ok:
        print("Aborted: fix the dataset errors above first. Nothing was written.")
        return 1

    mode = "APPLY" if apply else "DRY RUN (no changes written)"
    print(f"Seed internships - {mode} - database: {SessionLocal.kw['bind'].url.database}")

    with SessionLocal() as db:
        result = seed_internships(db, report.valid, apply=apply)
        if apply:
            db.commit()
        else:
            db.rollback()

    verb = "" if apply else "would be "
    print(
        f"Summary: {result.created} {verb}created, {result.updated} {verb}updated, "
        f"{result.unchanged} unchanged."
    )
    return 0


def rebuild_index_command(apply: bool = False) -> int:
    from backend.services import embeddings, vector_index

    database_name = SessionLocal.kw["bind"].url.database
    if not apply:
        with SessionLocal() as db:
            plan = vector_index.plan_rebuild(db)
        print(f"Rebuild index - DRY RUN - database: {database_name}")
        print(
            f"Would index {plan['active_internships']} active internships "
            f"({plan['new_or_changed']} new or changed) into {vector_index.index_dir()}"
        )
        return 0

    print(f"Rebuild index - APPLY - database: {database_name}")
    try:
        result = vector_index.rebuild_index(embeddings.get_embedder())
    except vector_index.IndexBusyError as exc:
        print(f"Not started: {exc}")
        return 1
    print(
        f"Indexed {result.indexed} internships with {result.model_name} "
        f"(dim {result.dimension}); {result.deactivated_documents} removed; "
        f"built at {result.built_at}"
    )
    return 0


def index_status_command() -> int:
    import json

    from backend.services import vector_index

    with SessionLocal() as db:
        print(json.dumps(vector_index.index_status(db), indent=2))
    return 0


def download_embedding_model_command() -> int:
    from backend.services import embeddings

    path = embeddings.download_model()
    print(f"Embedding model ready (safetensors only) in: {path}")
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

    validate_parser = subparsers.add_parser(
        "validate-internships", help="Validate the internship dataset (no database)"
    )
    validate_parser.add_argument("--file")

    seed_parser = subparsers.add_parser(
        "seed-internships", help="Import internships (dry run by default)"
    )
    seed_parser.add_argument("--file")
    seed_parser.add_argument("--apply", action="store_true")

    rebuild_parser = subparsers.add_parser(
        "rebuild-index", help="Rebuild the FAISS index from PostgreSQL (dry run by default)"
    )
    rebuild_parser.add_argument("--apply", action="store_true")

    subparsers.add_parser("index-status", help="Show search index status")
    subparsers.add_parser(
        "download-embedding-model", help="One-time download of the pinned model"
    )

    args = parser.parse_args(argv)

    if args.command == "validate-internships":
        return validate_internships(args.file)

    if args.command == "seed-internships":
        return seed_internships_command(apply=args.apply, path=args.file)

    if args.command == "rebuild-index":
        return rebuild_index_command(apply=args.apply)

    if args.command == "index-status":
        return index_status_command()

    if args.command == "download-embedding-model":
        return download_embedding_model_command()

    if args.command == "set-role":
        return set_role(args.email, args.role)

    if args.command == "backfill-skills":
        return backfill_skills(apply=args.apply)

    return 1


if __name__ == "__main__":
    sys.exit(main())
