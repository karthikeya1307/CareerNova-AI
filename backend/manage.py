"""Command-line management tasks.

Usage:
    python -m backend.manage create-superadmin --email <email> --first-name <name> --last-name <name>
    python -m backend.manage create-superadmin --email <email> --promote-existing
    python -m backend.manage set-role <email> <student|admin>
    python -m backend.manage backfill-skills            # dry run (default)
    python -m backend.manage backfill-skills --apply    # write changes
    python -m backend.manage validate-internships       # no database access
    python -m backend.manage seed-internships [--apply]
    python -m backend.manage rebuild-index [--apply]
    python -m backend.manage index-status
    python -m backend.manage download-embedding-model   # one-time, network
    python -m backend.manage parse-resume <file.pdf|docx|odt> --parser regex|llm|hybrid   # prints JSON, saves nothing

Bootstrap (one protected super admin; see README "Administration"):
    python -m backend.manage create-superadmin --email owner@example.com --first-name Ada --last-name Admin
The password is asked for twice with hidden input; it is never an argument,
never printed and never logged. Running the command again for the same email
changes nothing; a different email is refused while a super admin exists.
"""

import argparse
import getpass
import re
import sys

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.database import SessionLocal
from backend.models import Resume, ResumeExtraction, ResumeSkill, Skill, User
from backend.services.resume_skills import sync_resume_skills
from backend.services.skill_normalizer import normalize_extracted_skills
from backend.utils.roles import ASSIGNABLE_ROLES, ROLE_SUPER_ADMIN, is_super_admin_role

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def set_role(email: str, role: str) -> int:
    from backend.services import audit

    role = role.strip().lower()

    if role not in ASSIGNABLE_ROLES:
        print(f"Invalid role. Choose one of: {', '.join(sorted(ASSIGNABLE_ROLES))}. "
              "Use create-superadmin for the super admin.")
        return 1

    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )

        if user is None:
            print("No user found with that email.")
            return 1

        if is_super_admin_role(user.role):
            print("That account is the protected super admin; its role cannot be changed.")
            return 1

        if user.role == role:
            print(f"User {user.user_id} already has role '{role}'. Nothing changed.")
            return 0

        previous = user.role
        user.role = role
        audit.record(db, "user.role_change", target=user,
                     details={"from": previous, "to": role, "via": "command line"})
        db.commit()
        print(f"User {user.user_id} role set to '{role}'.")

    return 0


def valid_password(password: str) -> str | None:
    """Same rules as the sign-up form. Returns a problem description, or None."""
    if not 8 <= len(password) <= 128:
        return "Password must be 8 to 128 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


def create_superadmin(
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    promote_existing: bool = False,
    ask_password=None,
) -> int:
    """Create (or promote) the single protected super admin. Idempotent.

    * Same email already super admin -> nothing changes, exit 0.
    * Another super admin exists     -> refused, exit 1.
    * Existing account               -> only with --promote-existing; it must be
                                        verified and active; password unchanged.
    * New account                    -> password asked twice with hidden input;
                                        created verified and active.
    The password is never printed, logged or passed as an argument.
    """
    from pwdlib import PasswordHash

    from backend.services import audit

    ask_password = ask_password or getpass.getpass
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 255:
        print("Enter a valid email address.")
        return 1

    with SessionLocal() as db:
        existing_super = db.scalar(select(User).where(User.role == ROLE_SUPER_ADMIN))
        if existing_super is not None:
            if existing_super.email.lower() == email:
                print(f"User {existing_super.user_id} is already the super admin. Nothing changed.")
                return 0
            print("A super admin already exists. Only one is allowed; nothing changed.")
            return 1

        user = db.scalar(select(User).where(func.lower(User.email) == email))

        if user is not None:
            if not promote_existing:
                print("An account with this email already exists. Re-run with --promote-existing "
                      "to make it the super admin (its password is not changed).")
                return 1
            if not user.is_verified or not user.is_active:
                print("That account must be verified and active before it can become the super admin. "
                      "Nothing changed.")
                return 1
            previous = user.role
            user.role = ROLE_SUPER_ADMIN
            audit.record(db, "superadmin.bootstrap", target=user,
                         details={"mode": "promoted_existing", "previous_role": previous})
        else:
            if promote_existing:
                print("No account with this email exists, so there is nothing to promote.")
                return 1
            first_name = (first_name or "").strip()
            last_name = (last_name or "").strip()
            if not first_name or not last_name or len(first_name) > 100 or len(last_name) > 100:
                print("--first-name and --last-name are required for a new account (1-100 characters).")
                return 1
            password = ask_password("New super admin password (hidden): ")
            problem = valid_password(password)
            if problem:
                print(problem + " Nothing changed.")
                return 1
            if ask_password("Repeat the password (hidden): ") != password:
                print("The passwords do not match. Nothing changed.")
                return 1
            user = User(first_name=first_name, last_name=last_name, email=email,
                        password_hash=PasswordHash.recommended().hash(password),
                        role=ROLE_SUPER_ADMIN, is_verified=True, is_active=True)
            db.add(user)
            db.flush()
            audit.record(db, "superadmin.bootstrap", target=user, details={"mode": "created"})

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print("A super admin was created at the same time by another process. Nothing changed.")
            return 1
        print(f"User {user.user_id} ({email}) is now the super admin.")
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


def email_check(send_test_to: str | None = None) -> int:
    """Validate the email configuration (no secrets printed). Optionally send one test message
    in the configured EMAIL_MODE (in smtp mode this sends a real email)."""
    from backend.services import mailer

    report = mailer.validate_config()
    print(f"Email mode: {report['mode']}")
    if report["mode"] == "smtp":
        print(f"SMTP server: {report['host']}:{report['port']} ({report['security']}); "
              f"credentials configured: {report['credentials_configured']}; sender configured: {report['sender_configured']}")
    print(f"Links point to: {report['frontend_url']}")
    for problem in report["problems"]:
        print(f"PROBLEM: {problem}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    if not report["ok"]:
        return 1
    print("Configuration OK.")
    if send_test_to:
        result = mailer.deliver("test", send_test_to, mailer.render("test"))
        print(f"Test message: {result.status}" + (f" ({result.error_code}: {result.detail})" if result.error_code else ""))
        return 0 if result.accepted else 1
    return 0


def parse_resume_command(path: str, parser_name: str) -> int:
    """Print one parser's JSON for a local file. No database access; llm/hybrid use the configured LLM_PROVIDER."""
    import json
    from pathlib import Path

    from backend.services import resume_parsers
    from backend.services.resume_parsers import llm_parser

    file = Path(path)
    if not file.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    try:
        result = resume_parsers.run(parser_name, file.read_bytes(), file.name)
    except (resume_parsers.ResumeFileError, llm_parser.LLMParserUnavailable, llm_parser.LLMParserError) as exc:
        print(f"{parser_name} parser: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.manage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    role_parser = subparsers.add_parser("set-role", help="Change a user's role (student or admin)")
    role_parser.add_argument("email")
    role_parser.add_argument("role", choices=sorted(ASSIGNABLE_ROLES))

    super_parser = subparsers.add_parser(
        "create-superadmin",
        help="Create or promote the single protected super admin (password asked with hidden input)",
    )
    super_parser.add_argument("--email", required=True)
    super_parser.add_argument("--first-name")
    super_parser.add_argument("--last-name")
    super_parser.add_argument(
        "--promote-existing", action="store_true",
        help="Make an existing verified, active account the super admin (password unchanged).",
    )

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
        "rebuild-index", help="Rebuild the vector index from PostgreSQL (dry run by default)"
    )
    rebuild_parser.add_argument("--apply", action="store_true")

    subparsers.add_parser("index-status", help="Show search index status")
    email_parser = subparsers.add_parser("email-check", help="Validate the email configuration (no secrets shown)")
    email_parser.add_argument("--send-test", metavar="EMAIL",
                              help="Also send one test message in the configured EMAIL_MODE (smtp mode sends for real)")
    subparsers.add_parser(
        "download-embedding-model", help="One-time download of the pinned model"
    )
    parse_cmd = subparsers.add_parser(
        "parse-resume", help="Run the regex, LLM or hybrid parser on a PDF/DOCX/ODT file and print JSON (nothing saved)"
    )
    parse_cmd.add_argument("file")
    parse_cmd.add_argument("--parser", choices=["regex", "llm", "hybrid"], default="regex")

    args = parser.parse_args(argv)

    if args.command == "parse-resume":
        return parse_resume_command(args.file, args.parser)

    if args.command == "validate-internships":
        return validate_internships(args.file)

    if args.command == "seed-internships":
        return seed_internships_command(apply=args.apply, path=args.file)

    if args.command == "rebuild-index":
        return rebuild_index_command(apply=args.apply)

    if args.command == "index-status":
        return index_status_command()

    if args.command == "email-check":
        return email_check(args.send_test)

    if args.command == "download-embedding-model":
        return download_embedding_model_command()

    if args.command == "set-role":
        return set_role(args.email, args.role)

    if args.command == "create-superadmin":
        return create_superadmin(args.email, args.first_name, args.last_name, args.promote_existing)

    if args.command == "backfill-skills":
        return backfill_skills(apply=args.apply)

    return 1


if __name__ == "__main__":
    sys.exit(main())
