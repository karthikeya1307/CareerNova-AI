"""Initialise or upgrade the database at deploy time (used by Render's start command).

    python -m backend.deploy_db --check           # report what would happen; changes nothing
    python -m backend.deploy_db                   # initialise a fresh database, or upgrade an existing one
    python -m backend.deploy_db --seed-if-empty   # ... and load the 180 curated internships if there are none

Why this exists: the migration history starts from ``9c59adb5cc64`` (an empty "baseline" recorded on a
database whose tables already existed), so ``alembic upgrade head`` cannot build a database from nothing.
For an EMPTY database the current schema is created from the models and stamped at head - Alembic's own
recommendation for new databases. This was verified: the result matches a database migrated through the
full history (36 tables, 372 columns, 156 constraints, 114 indexes incl. partial/functional ones, 31
sequences); see tests/test_deploy_db.py. Every later deploy runs the normal migrations.

States:
  * fresh    - no application tables (a version row left by an earlier failed attempt is ignored):
               create_all + stamp head in ONE transaction; nothing is left half-built on failure.
  * managed  - alembic_version present with application tables: ``alembic upgrade head`` (no-op when current).
  * unmanaged- application tables but no alembic_version: STOP, change nothing (manual review needed).

Safety: never drops or alters existing tables; a PostgreSQL advisory lock stops two deploys running at
once; connection details and passwords are never printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from backend import database
from backend.models import Base

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_KEY = 7_340_211_905          # arbitrary constant: "CareerNova schema deploy"
VERSION_TABLE = "alembic_version"


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return config


def inspect_state(connection) -> dict:
    """Read-only description of the database."""
    tables = set(inspect(connection).get_table_names())
    app_tables = tables - {VERSION_TABLE}
    current = MigrationContext.configure(connection).get_current_revision() if VERSION_TABLE in tables else None
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if not app_tables:
        state = "fresh"
    elif VERSION_TABLE in tables and current:
        state = "managed"
    else:
        state = "unmanaged"
    return {"state": state, "app_tables": len(app_tables), "current": current, "head": head,
            "model_tables": len(Base.metadata.tables)}


def _internship_count(connection) -> int:
    return connection.execute(text("SELECT count(*) FROM internships")).scalar() or 0


def seed_if_empty() -> str:
    """Load the curated internship catalogue only when it is empty (never overwrites admin edits)."""
    from backend.services.internship_seed import load_dataset, seed_internships, validate_records

    with database.engine.connect() as connection:
        if _internship_count(connection):
            return "internships already present - seeding skipped"
    report = validate_records(load_dataset())
    if not report.ok:
        return "curated dataset failed validation - seeding skipped"
    with database.SessionLocal() as db:
        result = seed_internships(db, report.valid, apply=True)
        db.commit()
    return f"seeded {result.created} curated internships"


def run(check_only: bool = False, seed: bool = False) -> int:
    name = database.engine.url.database
    config = alembic_config()
    with database.engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
        connection.commit()
        try:
            info = inspect_state(connection)
            connection.rollback()
            print(f"Database '{name}': state={info['state']}, application tables={info['app_tables']}, "
                  f"revision={info['current'] or 'none'}, code head={info['head']}")

            if info["state"] == "unmanaged":
                print("STOP: the database has tables but no Alembic version. Nothing was changed. "
                      "Review the schema manually (see DEPLOYMENT_AND_HANDOVER_GUIDE.md).")
                return 1
            if check_only:
                action = {"fresh": f"create {info['model_tables']} tables and stamp {info['head']}",
                          "managed": ("do nothing (already at head)" if info["current"] == info["head"]
                                      else f"upgrade {info['current']} -> {info['head']}")}[info["state"]]
                print(f"CHECK ONLY - would {action}. Nothing was changed.")
                return 0

            config.attributes["connection"] = connection
            with connection.begin():
                if info["state"] == "fresh":
                    print("Fresh database: creating the current schema and recording the Alembic head...")
                    Base.metadata.create_all(bind=connection)
                    command.stamp(config, "head", purge=True)     # replaces a stale row from a failed attempt
                else:
                    print("Existing database: applying Alembic migrations (if any)...")
                    command.upgrade(config, "head")
            final = MigrationContext.configure(connection).get_current_revision()
            connection.rollback()
            print(f"Database ready at revision {final}.")
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
            connection.commit()

    if seed:
        print("Internship catalogue: " + seed_if_empty() + ".")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only; change nothing")
    parser.add_argument("--seed-if-empty", action="store_true",
                        help="load the curated internships when the catalogue is empty")
    args = parser.parse_args(argv)
    return run(check_only=args.check, seed=args.seed_if_empty)


if __name__ == "__main__":
    sys.exit(main())
