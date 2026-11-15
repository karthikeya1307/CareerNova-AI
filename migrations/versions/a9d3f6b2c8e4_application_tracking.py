"""application tracking: extend applications and add Phase 7 tables

Revision ID: a9d3f6b2c8e4
Revises: f3c9e1a5b7d2
Create Date: 2026-11-15

Upgrade (additive, safe for existing rows):
* checks existing status values first and stops on any value it cannot map
  (it never guesses); maps legacy lowercase statuses to the new uppercase set;
* adds the new columns, copies company/title/listing details from each
  application's internship, then makes the required ones NOT NULL;
* makes internship_id nullable (external applications) and changes its
  foreign key from ON DELETE CASCADE to ON DELETE SET NULL;
* replaces the old (user_id, internship_id) unique constraint with partial
  unique indexes that ignore trashed applications;
* creates saved_internships, application_status_history,
  application_interviews, application_reminders and application_activity;
* records one 'migrated' status-history row per existing application;
* gives legacy rows already past SAVED (except WITHDRAWN) an application
  date (applied_at = updated_at, else created_at) when they had none. The
  original applied_at column is kept on downgrade, so this value remains.

Downgrade refuses (and changes nothing) while any Phase 7 data exists,
unless run with ``-x phase7_allow_data_loss=true``. Even then it only
removes Phase 7 data: the five new tables and application rows the old
schema cannot hold (external, trashed, or without an internship). It never
touches users, resumes, internships or any Phase 1-6 table.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "a9d3f6b2c8e4"
down_revision: Union[str, Sequence[str], None] = "f3c9e1a5b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = ("SAVED", "APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN")
STATUS_SQL = ", ".join(f"'{s}'" for s in STATUSES)

# Legacy value (trimmed, lower-cased) -> Phase 7 status.
LEGACY_STATUS_MAP = {
    "saved": "SAVED",
    "applied": "APPLIED",
    "shortlisted": "SHORTLISTED",
    "interview": "INTERVIEW_SCHEDULED",
    "interview_scheduled": "INTERVIEW_SCHEDULED",
    "interviewing": "INTERVIEW_SCHEDULED",
    "selected": "SELECTED",
    "offer": "SELECTED",
    "accepted": "SELECTED",
    "rejected": "REJECTED",
    "withdrawn": "WITHDRAWN",
}

NEW_COLUMNS = [
    ("source", sa.String(length=20)),
    ("company_name", sa.String(length=200)),
    ("company_key", sa.String(length=200)),
    ("title", sa.String(length=200)),
    ("application_url", sa.String(length=1000)),
    ("application_url_normalized", sa.String(length=1000)),
    ("external_reference", sa.String(length=100)),
    ("domain", sa.String(length=80)),
    ("location", sa.String(length=150)),
    ("work_mode", sa.String(length=20)),
    ("contact_name", sa.String(length=120)),
    ("contact_email", sa.String(length=255)),
    ("resume_document_id", sa.Integer()),
    ("cover_letter_document_id", sa.Integer()),
    ("status_changed_at", sa.DateTime(timezone=True)),
    ("deleted_at", sa.DateTime(timezone=True)),
]

NEW_TABLES = ("application_activity", "application_reminders", "application_interviews",
              "application_status_history", "saved_internships")


def _in_list(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Refuse unknown legacy statuses before changing anything.
    rows = bind.execute(sa.text(
        "SELECT lower(trim(status)) AS s, count(*) AS n FROM applications GROUP BY 1")).all()
    unknown = {r.s: r.n for r in rows if r.s not in LEGACY_STATUS_MAP and r.s.upper() not in STATUSES}
    if unknown:
        raise RuntimeError(
            "Cannot migrate applications: unrecognised status values "
            + ", ".join(f"{value!r} ({count} row(s))" for value, count in sorted(unknown.items()))
            + ". Fix or map them first; nothing was changed.")

    # 2. New columns (nullable first).
    for name, column_type in NEW_COLUMNS:
        op.add_column("applications", sa.Column(name, column_type, nullable=True))

    # 3. Backfill existing rows from their internships and map statuses.
    op.execute("""
        UPDATE applications AS a
           SET source = 'internal',
               company_name = i.company,
               title = i.title,
               domain = i.domain,
               location = i.location,
               work_mode = i.work_mode,
               application_url = i.application_url
          FROM internships AS i
         WHERE i.internship_id = a.internship_id
    """)
    op.execute("UPDATE applications SET source = 'internal' WHERE source IS NULL")
    op.execute("UPDATE applications SET company_name = 'Unknown company' WHERE company_name IS NULL")
    op.execute("UPDATE applications SET title = 'Untitled internship' WHERE title IS NULL")
    op.execute(r"UPDATE applications SET company_key = lower(regexp_replace(trim(company_name), '\s+', ' ', 'g'))")
    cases = " ".join(f"WHEN '{legacy}' THEN '{new}'" for legacy, new in LEGACY_STATUS_MAP.items())
    op.execute(f"UPDATE applications SET status = CASE lower(trim(status)) {cases} "
               f"ELSE upper(trim(status)) END")
    op.execute("UPDATE applications SET status_changed_at = updated_at WHERE status_changed_at IS NULL")
    # Legacy rows already past SAVED were submitted at some point: give them an application date so the
    # dashboard counts them as submitted (WITHDRAWN is ambiguous - it may never have been applied for).
    op.execute("UPDATE applications SET applied_at = COALESCE(updated_at, created_at) "
               "WHERE applied_at IS NULL AND status IN "
               "('APPLIED', 'SHORTLISTED', 'INTERVIEW_SCHEDULED', 'SELECTED', 'REJECTED')")

    for name in ("source", "company_name", "company_key", "title"):
        op.alter_column("applications", name, nullable=False)
    op.alter_column("applications", "source", server_default=sa.text("'internal'"))
    op.alter_column("applications", "status", server_default=sa.text("'SAVED'"))

    # 4. internship_id: nullable, ON DELETE SET NULL; old unique constraint -> partial unique indexes.
    op.drop_constraint("uq_application_user_internship", "applications", type_="unique")
    op.drop_constraint("applications_internship_id_fkey", "applications", type_="foreignkey")
    op.create_foreign_key("applications_internship_id_fkey", "applications", "internships",
                          ["internship_id"], ["internship_id"], ondelete="SET NULL")
    op.alter_column("applications", "internship_id", nullable=True)
    op.create_foreign_key("applications_resume_document_id_fkey", "applications", "generated_documents",
                          ["resume_document_id"], ["document_id"], ondelete="SET NULL")
    op.create_foreign_key("applications_cover_letter_document_id_fkey", "applications", "generated_documents",
                          ["cover_letter_document_id"], ["document_id"], ondelete="SET NULL")

    op.create_check_constraint("ck_applications_status", "applications", f"status IN ({STATUS_SQL})")
    op.create_check_constraint("ck_applications_source", "applications", "source IN ('internal', 'external')")
    op.create_check_constraint("ck_applications_external_no_internship", "applications",
                               "source = 'internal' OR internship_id IS NULL")
    op.create_check_constraint("ck_applications_work_mode", "applications",
                               "work_mode IN ('Onsite', 'Hybrid', 'Remote')")
    op.create_index("ix_applications_user_status", "applications", ["user_id", "status"])
    op.create_index("ix_applications_user_updated", "applications", ["user_id", "updated_at"])
    op.create_index("ix_applications_user_applied", "applications", ["user_id", "applied_at"])
    op.create_index("uq_applications_user_internship_active", "applications", ["user_id", "internship_id"],
                    unique=True, postgresql_where=sa.text("deleted_at IS NULL AND internship_id IS NOT NULL"))
    op.create_index("uq_applications_user_url_active", "applications",
                    ["user_id", "application_url_normalized"], unique=True,
                    postgresql_where=sa.text("deleted_at IS NULL AND source = 'external' "
                                             "AND application_url_normalized IS NOT NULL"))
    op.create_index("uq_applications_user_reference_active", "applications",
                    ["user_id", "company_key", "external_reference"], unique=True,
                    postgresql_where=sa.text("deleted_at IS NULL AND external_reference IS NOT NULL"))

    # 5. New tables.
    op.create_table(
        "saved_internships",
        sa.Column("bookmark_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("internship_id", sa.Integer(),
                  sa.ForeignKey("internships.internship_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "internship_id", name="uq_saved_internships_user_internship"),
    )
    op.create_index(op.f("ix_saved_internships_user_id"), "saved_internships", ["user_id"])
    op.create_index(op.f("ix_saved_internships_internship_id"), "saved_internships", ["internship_id"])

    op.create_table(
        "application_status_history",
        sa.Column("history_id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(),
                  sa.ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(length=30)),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"to_status IN ({STATUS_SQL})", name="ck_application_status_history_to"),
        sa.CheckConstraint(f"from_status IS NULL OR from_status IN ({STATUS_SQL})",
                           name="ck_application_status_history_from"),
        sa.CheckConstraint(_in_list("change_type", ("created", "manual", "correction", "interview_added",
                                                    "interview_cancelled", "migrated")),
                           name="ck_application_status_history_change_type"),
    )
    op.create_index("ix_application_status_history_app_time", "application_status_history",
                    ["application_id", "changed_at"])

    op.create_table(
        "application_interviews",
        sa.Column("interview_id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(),
                  sa.ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("interview_type", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("meeting_url", sa.String(length=500)),
        sa.Column("location", sa.String(length=200)),
        sa.Column("preparation_notes", sa.Text()),
        sa.Column("feedback", sa.Text()),
        sa.Column("outcome", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("interview_session_id", sa.Integer(),
                  sa.ForeignKey("interview_sessions.session_id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("application_id", "round_number", name="uq_application_interviews_round"),
        sa.CheckConstraint("round_number >= 1", name="ck_application_interviews_round_positive"),
        sa.CheckConstraint(_in_list("interview_type", ("technical", "hr", "behavioral", "managerial",
                                                       "case_study", "assignment", "group", "other")),
                           name="ck_application_interviews_type"),
        sa.CheckConstraint(_in_list("mode", ("online", "offline", "phone")), name="ck_application_interviews_mode"),
        sa.CheckConstraint(_in_list("outcome", ("pending", "passed", "failed", "cancelled", "no_show")),
                           name="ck_application_interviews_outcome"),
        sa.CheckConstraint("duration_minutes IS NULL OR (duration_minutes BETWEEN 5 AND 600)",
                           name="ck_application_interviews_duration"),
    )
    op.create_index("ix_application_interviews_app_time", "application_interviews",
                    ["application_id", "scheduled_at"])
    op.create_index(op.f("ix_application_interviews_interview_session_id"), "application_interviews",
                    ["interview_session_id"])

    op.create_table(
        "application_reminders",
        sa.Column("reminder_id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(),
                  sa.ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_application_reminders_app_time", "application_reminders", ["application_id", "remind_at"])
    op.create_index("ix_application_reminders_completed_time", "application_reminders",
                    ["is_completed", "remind_at"])

    op.create_table(
        "application_activity",
        sa.Column("activity_id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(),
                  sa.ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in_list("event_type", (
            "application_created", "details_updated", "status_changed", "interview_scheduled",
            "interview_updated", "interview_deleted", "reminder_created", "reminder_updated",
            "reminder_completed", "reminder_reopened", "reminder_deleted", "application_deleted",
            "application_restored")), name="ck_application_activity_event_type"),
    )
    op.create_index("ix_application_activity_app_time", "application_activity", ["application_id", "created_at"])

    # 6. One 'migrated' history row per existing application.
    op.execute("""
        INSERT INTO application_status_history (application_id, from_status, to_status, change_type, changed_at)
        SELECT application_id, NULL, status, 'migrated', COALESCE(status_changed_at, now()) FROM applications
    """)


def phase7_data_counts(bind) -> dict[str, int]:
    """Rows the pre-Phase 7 schema cannot represent (anything else survives a downgrade)."""
    queries = {
        "bookmarks": "SELECT count(*) FROM saved_internships",
        "interview rounds": "SELECT count(*) FROM application_interviews",
        "reminders": "SELECT count(*) FROM application_reminders",
        "activity entries": "SELECT count(*) FROM application_activity",
        "status history entries": "SELECT count(*) FROM application_status_history WHERE change_type <> 'migrated'",
        "external, trashed or unlinked applications":
            "SELECT count(*) FROM applications WHERE source = 'external' OR deleted_at IS NOT NULL "
            "OR internship_id IS NULL",
    }
    return {label: bind.execute(sa.text(sql)).scalar() for label, sql in queries.items()}


def downgrade() -> None:
    bind = op.get_bind()
    allow = context.get_x_argument(as_dictionary=True).get("phase7_allow_data_loss", "").lower() == "true"
    counts = {k: v for k, v in phase7_data_counts(bind).items() if v}
    if counts and not allow:
        raise RuntimeError(
            "Refusing to downgrade Phase 7: it would delete Phase 7 data ("
            + ", ".join(f"{n} {label}" for label, n in counts.items())
            + "). Nothing was changed. Re-run with -x phase7_allow_data_loss=true to remove only Phase 7 data.")

    # Only Phase 7 rows the old schema cannot hold. Children cascade; no other table references applications.
    op.execute("DELETE FROM applications WHERE source = 'external' OR deleted_at IS NOT NULL "
               "OR internship_id IS NULL")

    for table in NEW_TABLES:
        op.drop_table(table)

    for index in ("uq_applications_user_reference_active", "uq_applications_user_url_active",
                  "uq_applications_user_internship_active", "ix_applications_user_applied",
                  "ix_applications_user_updated", "ix_applications_user_status"):
        op.drop_index(index, table_name="applications")
    for check in ("ck_applications_work_mode", "ck_applications_external_no_internship",
                  "ck_applications_source", "ck_applications_status"):
        op.drop_constraint(check, "applications", type_="check")
    op.drop_constraint("applications_cover_letter_document_id_fkey", "applications", type_="foreignkey")
    op.drop_constraint("applications_resume_document_id_fkey", "applications", type_="foreignkey")

    op.alter_column("applications", "internship_id", nullable=False)
    op.drop_constraint("applications_internship_id_fkey", "applications", type_="foreignkey")
    op.create_foreign_key("applications_internship_id_fkey", "applications", "internships",
                          ["internship_id"], ["internship_id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_application_user_internship", "applications", ["user_id", "internship_id"])

    op.execute("UPDATE applications SET status = lower(status)")
    op.alter_column("applications", "status", server_default=None)
    for name, _ in reversed(NEW_COLUMNS):
        op.drop_column("applications", name)
