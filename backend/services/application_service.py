"""Application tracking (Phase 7): ownership, status rules, history and activity.

Every public function takes the authenticated ``user_id`` and only ever
touches that student's rows; anything else raises ``NotFound`` (404), so the
existence of other students' records is never revealed.

Each change that touches several rows (status + history + activity, an
interview round + an automatic status change, trash/restore) is written in
ONE transaction with a single commit; status-affecting operations lock the
application row (SELECT ... FOR UPDATE) so concurrent requests are applied
one after the other. On any error nothing is committed.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    Application,
    ApplicationActivity,
    ApplicationInterview,
    ApplicationReminder,
    ApplicationStatusHistory,
    GeneratedDocument,
    Internship,
    InterviewSession,
    MatchResult,
    SavedInternship,
)
from backend.services.matching_agent import is_eligible

# ------------------------------------------------------------------
# Rules and limits
# ------------------------------------------------------------------

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "SAVED": ("APPLIED", "WITHDRAWN"),
    "APPLIED": ("SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"),
    "SHORTLISTED": ("INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"),
    "INTERVIEW_SCHEDULED": ("SHORTLISTED", "SELECTED", "REJECTED", "WITHDRAWN"),
    "SELECTED": ("WITHDRAWN",),
    "REJECTED": (),
    "WITHDRAWN": (),
}
INTERVIEW_ALLOWED_STATUSES = ("APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED")
AUTO_ADVANCE_FROM = ("APPLIED", "SHORTLISTED")

MAX_APPLICATIONS = 1000
MAX_BOOKMARKS = 1000
MAX_ROUNDS = 20
MAX_REMINDERS = 100

CLOCK_SKEW = timedelta(minutes=5)
EARLIEST_APPLIED_AT = datetime(2000, 1, 1, tzinfo=timezone.utc)
SCHEDULE_WINDOW = timedelta(days=730)

EXTERNAL_ONLY_FIELDS = ("company_name", "title", "application_url", "external_reference")
INTERNAL_COPIED_FIELDS = ("company_name", "title", "application_url", "external_reference", "domain", "location",
                          "work_mode")
TRACKING_PARAMS = {"ref", "source", "gclid", "fbclid", "trk", "referrer", "src"}


class ApplicationError(Exception):
    status_code = 400

    def __init__(self, detail: Any):
        super().__init__(str(detail))
        self.detail = detail


class NotFound(ApplicationError):
    status_code = 404


class Conflict(ApplicationError):
    status_code = 409


class Invalid(ApplicationError):
    status_code = 422


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_company(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()[:200]


def normalize_url(url: str | None) -> str | None:
    """Stable identifier for a posting URL (scheme/host case, www., fragment, trailing slash, tracking)."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")))
    path = parts.path.rstrip("/")
    return urlunsplit(("https", netloc, path, query, ""))[:1000]


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


DUPLICATE_CONSTRAINTS = {
    "uq_applications_user_internship_active", "uq_applications_user_url_active",
    "uq_applications_user_reference_active", "uq_application_interviews_round", "uq_saved_internships_user_internship",
}
GENERIC_CONFLICT = "The change could not be saved because related data changed at the same time. Reload and try again."


def integrity_conflict(exc: IntegrityError, duplicate_message: str) -> Conflict:
    """A duplicate-rule violation keeps its specific message; anything else gets a generic one."""
    constraint = getattr(getattr(getattr(exc, "orig", None), "diag", None), "constraint_name", None)
    return Conflict(duplicate_message if constraint in DUPLICATE_CONSTRAINTS else GENERIC_CONFLICT)


def commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise integrity_conflict(exc, message) from None


def check_applied_at(value: datetime | None, now: datetime) -> None:
    if value is not None and not (EARLIEST_APPLIED_AT <= value <= now + CLOCK_SKEW):
        raise Invalid("applied_at must be between 2000-01-01 and now.")


def check_schedule(value: datetime, now: datetime, label: str) -> None:
    if not (now - SCHEDULE_WINDOW <= value <= now + SCHEDULE_WINDOW):
        raise Invalid(f"{label} must be within two years of today.")


def check_reminder_time(value: datetime, now: datetime) -> None:
    if value < now - CLOCK_SKEW:
        raise Invalid("remind_at cannot be in the past.")
    if value > now + SCHEDULE_WINDOW:
        raise Invalid("remind_at must be within two years.")


# ------------------------------------------------------------------
# Ownership
# ------------------------------------------------------------------

def owned_application(db: Session, user_id: int, application_id: int, *, lock: bool = False,
                      include_deleted: bool = False) -> Application:
    query = select(Application).where(Application.application_id == application_id,
                                      Application.user_id == user_id)
    if not include_deleted:
        query = query.where(Application.deleted_at.is_(None))
    if lock:
        # populate_existing: refresh an object this session already holds with the locked row's values.
        query = query.with_for_update().execution_options(populate_existing=True)
    application = db.scalar(query)
    if application is None:
        raise NotFound("Application not found")
    return application


def owned_interview(db: Session, user_id: int, interview_id: int) -> ApplicationInterview:
    interview = db.scalar(
        select(ApplicationInterview).join(Application)
        .where(ApplicationInterview.interview_id == interview_id, Application.user_id == user_id,
               Application.deleted_at.is_(None)))
    if interview is None:
        raise NotFound("Interview not found")
    return interview


def owned_reminder(db: Session, user_id: int, reminder_id: int) -> ApplicationReminder:
    reminder = db.scalar(
        select(ApplicationReminder).join(Application)
        .where(ApplicationReminder.reminder_id == reminder_id, Application.user_id == user_id,
               Application.deleted_at.is_(None)))
    if reminder is None:
        raise NotFound("Reminder not found")
    return reminder


def deadline_passed(internship: Internship, now: datetime | None = None) -> bool:
    """True when the internship's deadline is in the past, whether or not it is still active."""
    deadline = as_utc(internship.deadline)
    return deadline is not None and deadline < (now or utcnow())


def pending_round_warnings(db: Session, application: Application) -> list[str]:
    """Warn when pending interview rounds remain outside the interview stage (e.g. after a correction)."""
    if application.status == "INTERVIEW_SCHEDULED":
        return []
    pending = db.scalar(select(func.count()).select_from(ApplicationInterview).where(
        ApplicationInterview.application_id == application.application_id,
        ApplicationInterview.outcome == "pending"))
    if not pending:
        return []
    return [f"{pending} pending interview round(s) remain on this application. Update their outcome "
            "or cancel them if they will not take place."]


def available_internship(db: Session, internship_id: int, *, require_open_deadline: bool) -> Internship:
    internship = db.get(Internship, internship_id)
    if internship is None or not internship.is_active or (require_open_deadline and not is_eligible(internship)):
        raise NotFound("Internship not found")
    return internship


def check_documents(db: Session, user_id: int, resume_document_id: int | None,
                    cover_letter_document_id: int | None) -> None:
    for document_id, kind in ((resume_document_id, "resume"), (cover_letter_document_id, "cover_letter")):
        if document_id is None:
            continue
        document = db.scalar(select(GeneratedDocument).where(GeneratedDocument.document_id == document_id,
                                                             GeneratedDocument.user_id == user_id))
        if document is None:
            raise NotFound("Document not found")
        if document.document_type != kind:
            raise Invalid(f"Document {document_id} is not a {kind.replace('_', ' ')}.")


# ------------------------------------------------------------------
# History and activity
# ------------------------------------------------------------------

def record_activity(db: Session, application: Application, event_type: str, **details: Any) -> None:
    """Non-sensitive activity: statuses, field NAMES, round numbers and ids only."""
    db.add(ApplicationActivity(application_id=application.application_id, event_type=event_type,
                               details=details or None))


def set_status(db: Session, application: Application, new_status: str, change_type: str, now: datetime) -> str:
    old = application.status
    application.status = new_status
    application.status_changed_at = now
    if new_status == "SAVED":
        application.applied_at = None
    elif application.applied_at is None and not (old == "SAVED" and new_status == "WITHDRAWN"):
        application.applied_at = now
    db.add(ApplicationStatusHistory(application_id=application.application_id, from_status=old,
                                    to_status=new_status, change_type=change_type, changed_at=now))
    record_activity(db, application, "status_changed", from_status=old, to_status=new_status,
                    change_type=change_type)
    return old


def last_change_into(db: Session, application: Application, status: str) -> ApplicationStatusHistory | None:
    return db.scalar(
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == application.application_id,
               ApplicationStatusHistory.to_status == status)
        .order_by(ApplicationStatusHistory.history_id.desc()).limit(1))


def change_status(db: Session, user_id: int, application_id: int, status: str, *, correction: bool = False,
                  expected_status: str | None = None) -> tuple[Application, bool, str]:
    application = owned_application(db, user_id, application_id, lock=True)
    old = application.status
    if expected_status is not None and expected_status != old:
        raise Conflict(f"The application status is now {old}. Reload and try again.")
    if status == old:
        return application, False, old

    now = utcnow()
    if correction:
        entry = last_change_into(db, application, old)
        previous = entry.from_status if entry else None
        if previous is None:
            raise Conflict("There is no earlier status to go back to.")
        if status != previous:
            raise Conflict(f"A correction can only undo the last status change (back to {previous}).")
        set_status(db, application, status, "correction", now)
    else:
        allowed = TRANSITIONS[old]
        if status not in allowed:
            raise Conflict(f"Cannot change status from {old} to {status}. Allowed: "
                           + (", ".join(allowed) if allowed else "none (use a correction to undo)") + ".")
        set_status(db, application, status, "manual", now)
    db.commit()
    db.refresh(application)
    return application, True, old


# ------------------------------------------------------------------
# Applications
# ------------------------------------------------------------------

def active_applications(user_id: int) -> Select:
    return select(Application).where(Application.user_id == user_id, Application.deleted_at.is_(None))


def _conflicting(db: Session, user_id: int, *, internship_id: int | None = None, url_key: str | None = None,
                 company_key: str | None = None, reference: str | None = None,
                 exclude: int | None = None) -> Application | None:
    query = active_applications(user_id)
    if exclude is not None:
        query = query.where(Application.application_id != exclude)
    if internship_id is not None:
        found = db.scalar(query.where(Application.internship_id == internship_id))
        if found:
            return found
    if url_key is not None:
        found = db.scalar(query.where(Application.source == "external",
                                      Application.application_url_normalized == url_key))
        if found:
            return found
    if reference is not None and company_key is not None:
        found = db.scalar(query.where(Application.company_key == company_key,
                                      Application.external_reference == reference))
        if found:
            return found
    return None


def _duplicate_error(existing: Application) -> Conflict:
    return Conflict({"message": "You already have an application for this opening.",
                     "application_id": existing.application_id})


def possible_duplicates(db: Session, application: Application) -> list[int]:
    if application.source != "external":
        return []
    return list(db.scalars(
        active_applications(application.user_id)
        .where(Application.application_id != application.application_id,
               Application.company_key == application.company_key,
               func.lower(Application.title) == application.title.lower())
        .with_only_columns(Application.application_id).order_by(Application.application_id)))


def create_application(db: Session, user_id: int, data: dict[str, Any], provided: set[str]) -> Application:
    now = utcnow()
    count = db.scalar(select(func.count()).select_from(Application).where(Application.user_id == user_id))
    if count >= MAX_APPLICATIONS:
        raise Conflict(f"You can track at most {MAX_APPLICATIONS} applications.")

    status = data.get("status") or "SAVED"
    applied_at = data.get("applied_at")
    if status == "SAVED" and applied_at is not None:
        raise Invalid("applied_at can only be set when the status is APPLIED.")
    check_applied_at(applied_at, now)
    check_documents(db, user_id, data.get("resume_document_id"), data.get("cover_letter_document_id"))

    internship_id = data.get("internship_id")
    if internship_id is not None:
        copied = sorted(provided & set(INTERNAL_COPIED_FIELDS))
        if copied:
            raise Invalid(f"These details come from the internship and cannot be set: {', '.join(copied)}.")
        internship = available_internship(db, internship_id, require_open_deadline=False)
        existing = _conflicting(db, user_id, internship_id=internship_id)
        if existing:
            raise _duplicate_error(existing)
        application = Application(
            user_id=user_id, internship_id=internship_id, source="internal",
            company_name=internship.company[:200], company_key=normalize_company(internship.company),
            title=internship.title[:200], application_url=internship.application_url,
            application_url_normalized=normalize_url(internship.application_url),
            domain=internship.domain, location=internship.location, work_mode=internship.work_mode)
    else:
        if not data.get("company_name") or not data.get("title"):
            raise Invalid("company_name and title are required for an external application "
                          "(or pass internship_id for an internship from the knowledge base).")
        company_key = normalize_company(data["company_name"])
        url_key = normalize_url(data.get("application_url"))
        existing = _conflicting(db, user_id, url_key=url_key, company_key=company_key,
                                reference=data.get("external_reference"))
        if existing:
            raise _duplicate_error(existing)
        application = Application(
            user_id=user_id, source="external", company_name=data["company_name"], company_key=company_key,
            title=data["title"], application_url=data.get("application_url"), application_url_normalized=url_key,
            external_reference=data.get("external_reference"), domain=data.get("domain"),
            location=data.get("location"), work_mode=data.get("work_mode"))

    for field in ("notes", "contact_name", "contact_email", "resume_document_id", "cover_letter_document_id"):
        setattr(application, field, data.get(field))
    application.status = status
    application.status_changed_at = now
    application.applied_at = (applied_at or now) if status == "APPLIED" else None
    db.add(application)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise integrity_conflict(exc, "You already have an application for this opening.") from None
    db.add(ApplicationStatusHistory(application_id=application.application_id, from_status=None,
                                    to_status=status, change_type="created", changed_at=now))
    record_activity(db, application, "application_created", source=application.source, status=status)
    commit_or_conflict(db, "You already have an application for this opening.")
    db.refresh(application)
    return application


def update_application(db: Session, user_id: int, application_id: int, data: dict[str, Any],
                       provided: set[str]) -> Application:
    application = owned_application(db, user_id, application_id, lock=True)
    now = utcnow()
    if application.source == "internal":
        locked = sorted(provided & set(EXTERNAL_ONLY_FIELDS))
        if locked:
            raise Invalid(f"These details come from the internship and cannot be edited: {', '.join(locked)}.")
    for field in ("company_name", "title"):
        if field in provided and data.get(field) is None:
            raise Invalid(f"{field} cannot be empty.")
    if "applied_at" in provided:
        if application.status == "SAVED" and data.get("applied_at") is not None:
            raise Invalid("applied_at can only be set after the application is submitted.")
        if application.status != "SAVED" and data.get("applied_at") is None:
            raise Invalid("applied_at cannot be cleared for a submitted application.")
        check_applied_at(data.get("applied_at"), now)
    check_documents(db, user_id, data.get("resume_document_id") if "resume_document_id" in provided else None,
                    data.get("cover_letter_document_id") if "cover_letter_document_id" in provided else None)

    changed = []
    for field in sorted(provided):
        value = data.get(field)
        current = getattr(application, field)
        if isinstance(current, datetime) and isinstance(value, datetime):
            same = as_utc(current) == value
        else:
            same = current == value
        if not same:
            setattr(application, field, value)
            changed.append(field)
    if not changed:
        return application

    if "company_name" in changed:
        application.company_key = normalize_company(application.company_name)
    if "application_url" in changed:
        application.application_url_normalized = normalize_url(application.application_url)
    if application.source == "external" and {"company_name", "application_url", "external_reference"} & set(changed):
        existing = _conflicting(db, user_id, url_key=application.application_url_normalized,
                                company_key=application.company_key, reference=application.external_reference,
                                exclude=application.application_id)
        if existing:
            raise _duplicate_error(existing)
    record_activity(db, application, "details_updated", fields=changed)
    commit_or_conflict(db, "You already have an application for this opening.")
    db.refresh(application)
    return application


def move_to_trash(db: Session, user_id: int, application_id: int) -> None:
    application = owned_application(db, user_id, application_id, lock=True)
    application.deleted_at = utcnow()
    record_activity(db, application, "application_deleted")
    db.commit()


def restore_application(db: Session, user_id: int, application_id: int) -> Application:
    application = owned_application(db, user_id, application_id, lock=True, include_deleted=True)
    if application.deleted_at is None:
        raise Conflict("This application is not in the trash.")
    existing = _conflicting(
        db, user_id, internship_id=application.internship_id,
        url_key=application.application_url_normalized if application.source == "external" else None,
        company_key=application.company_key, reference=application.external_reference,
        exclude=application.application_id)
    if existing:
        raise _duplicate_error(existing)
    application.deleted_at = None
    record_activity(db, application, "application_restored")
    commit_or_conflict(db, "You already have an application for this opening.")
    db.refresh(application)
    return application


def delete_permanently(db: Session, user_id: int, application_id: int) -> None:
    """Remove a trashed application and ALL its history, interviews, reminders and activity."""
    application = owned_application(db, user_id, application_id, lock=True, include_deleted=True)
    if application.deleted_at is None:
        raise Conflict("Move the application to the trash before deleting it permanently.")
    db.delete(application)          # database ON DELETE CASCADE removes every child row
    db.commit()


# ------------------------------------------------------------------
# Interviews
# ------------------------------------------------------------------

def _status_before_interview(db: Session, application: Application) -> str:
    """The last APPLIED/SHORTLISTED status before the current interview stage.

    Walks back through the history from the latest change into
    INTERVIEW_SCHEDULED, skipping corrections and other detours (for example
    SHORTLISTED -> INTERVIEW_SCHEDULED -> SELECTED -> correction back to
    INTERVIEW_SCHEDULED returns SHORTLISTED, not APPLIED).
    """
    entries = db.scalars(
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == application.application_id)
        .order_by(ApplicationStatusHistory.history_id.desc())).all()
    start = next((i for i, e in enumerate(entries) if e.to_status == "INTERVIEW_SCHEDULED"), None)
    if start is not None:
        for entry in entries[start:]:
            if entry.from_status in AUTO_ADVANCE_FROM:
                return entry.from_status
    return "APPLIED"


def sync_after_interview_change(db: Session, application: Application, *, round_active: bool,
                                now: datetime) -> dict[str, str] | None:
    """Keep the status consistent with the rounds (never touches SELECTED/REJECTED/WITHDRAWN)."""
    db.flush()
    if round_active and application.status in AUTO_ADVANCE_FROM:
        old = set_status(db, application, "INTERVIEW_SCHEDULED", "interview_added", now)
        return {"from_status": old, "to_status": "INTERVIEW_SCHEDULED", "reason": "interview_added"}
    if not round_active and application.status == "INTERVIEW_SCHEDULED":
        remaining = db.scalar(select(func.count()).select_from(ApplicationInterview).where(
            ApplicationInterview.application_id == application.application_id,
            ApplicationInterview.outcome != "cancelled"))
        if remaining == 0:
            target = _status_before_interview(db, application)
            old = set_status(db, application, target, "interview_cancelled", now)
            return {"from_status": old, "to_status": target, "reason": "interview_cancelled"}
    return None


def _check_practice_session(db: Session, user_id: int, application: Application, session_id: int | None) -> None:
    if session_id is None:
        return
    session = db.scalar(select(InterviewSession).where(InterviewSession.session_id == session_id,
                                                       InterviewSession.user_id == user_id))
    if session is None:
        raise NotFound("Interview practice session not found")
    if session.internship_id and application.internship_id and session.internship_id != application.internship_id:
        raise Invalid("That practice session was created for a different internship.")


def add_interview(db: Session, user_id: int, application_id: int,
                  data: dict[str, Any]) -> tuple[ApplicationInterview, dict | None]:
    application = owned_application(db, user_id, application_id, lock=True)
    if application.status not in INTERVIEW_ALLOWED_STATUSES:
        raise Conflict(f"Interviews can be added once the application is submitted (status is {application.status}).")
    now = utcnow()
    check_schedule(data["scheduled_at"], now, "scheduled_at")
    _check_practice_session(db, user_id, application, data.get("interview_session_id"))
    rounds = db.scalar(select(func.count()).select_from(ApplicationInterview)
                       .where(ApplicationInterview.application_id == application.application_id))
    if rounds >= MAX_ROUNDS:
        raise Conflict(f"An application can have at most {MAX_ROUNDS} interview rounds.")
    next_round = (db.scalar(select(func.max(ApplicationInterview.round_number))
                            .where(ApplicationInterview.application_id == application.application_id)) or 0) + 1
    interview = ApplicationInterview(application_id=application.application_id, round_number=next_round, **data)
    db.add(interview)
    db.flush()
    record_activity(db, application, "interview_scheduled", interview_id=interview.interview_id,
                    round_number=next_round, interview_type=interview.interview_type)
    # Creating a round only ever moves the status forward; recording a round that was
    # already cancelled never moves it back (M1).
    change = (sync_after_interview_change(db, application, round_active=True, now=now)
              if interview.outcome != "cancelled" else None)
    commit_or_conflict(db, "That interview round already exists.")
    db.refresh(interview)
    return interview, change


def update_interview(db: Session, user_id: int, interview_id: int, data: dict[str, Any],
                     provided: set[str]) -> tuple[ApplicationInterview, dict | None]:
    interview = owned_interview(db, user_id, interview_id)
    application = owned_application(db, user_id, interview.application_id, lock=True)
    now = utcnow()
    for field in ("interview_type", "mode", "scheduled_at", "outcome"):
        if field in provided and data.get(field) is None:
            raise Invalid(f"{field} cannot be empty.")
    if "scheduled_at" in provided:
        check_schedule(data["scheduled_at"], now, "scheduled_at")
    if "interview_session_id" in provided:
        _check_practice_session(db, user_id, application, data.get("interview_session_id"))

    before = interview.outcome
    changed = []
    for field in sorted(provided):
        value = data.get(field)
        current = getattr(interview, field)
        same = (as_utc(current) == value) if isinstance(current, datetime) else current == value
        if not same:
            setattr(interview, field, value)
            changed.append(field)
    change = None
    if changed:
        record_activity(db, application, "interview_updated", interview_id=interview.interview_id,
                        round_number=interview.round_number, fields=changed)
        if before != interview.outcome and "cancelled" in (before, interview.outcome):
            change = sync_after_interview_change(db, application, round_active=interview.outcome != "cancelled",
                                                 now=now)
        db.commit()
        db.refresh(interview)
    return interview, change


def delete_interview(db: Session, user_id: int, interview_id: int) -> dict | None:
    interview = owned_interview(db, user_id, interview_id)
    application = owned_application(db, user_id, interview.application_id, lock=True)
    record_activity(db, application, "interview_deleted", interview_id=interview.interview_id,
                    round_number=interview.round_number)
    db.delete(interview)
    change = sync_after_interview_change(db, application, round_active=False, now=utcnow())
    db.commit()
    return change


# ------------------------------------------------------------------
# Reminders (stored only; nothing is delivered)
# ------------------------------------------------------------------

def add_reminder(db: Session, user_id: int, application_id: int, data: dict[str, Any]) -> ApplicationReminder:
    application = owned_application(db, user_id, application_id, lock=True)
    check_reminder_time(data["remind_at"], utcnow())
    count = db.scalar(select(func.count()).select_from(ApplicationReminder)
                      .where(ApplicationReminder.application_id == application.application_id))
    if count >= MAX_REMINDERS:
        raise Conflict(f"An application can have at most {MAX_REMINDERS} reminders.")
    reminder = ApplicationReminder(application_id=application.application_id, **data)
    db.add(reminder)
    db.flush()
    record_activity(db, application, "reminder_created", reminder_id=reminder.reminder_id)
    db.commit()
    db.refresh(reminder)
    return reminder


def _locked_reminder(db: Session, user_id: int, reminder_id: int) -> tuple[ApplicationReminder, Application]:
    """Lock the parent application (like every other write), then re-read the reminder under the lock."""
    reminder = owned_reminder(db, user_id, reminder_id)
    application = owned_application(db, user_id, reminder.application_id, lock=True)
    reminder = db.scalar(select(ApplicationReminder).where(ApplicationReminder.reminder_id == reminder_id)
                         .execution_options(populate_existing=True))
    return reminder, application


def update_reminder(db: Session, user_id: int, reminder_id: int, data: dict[str, Any],
                    provided: set[str]) -> ApplicationReminder:
    reminder, application = _locked_reminder(db, user_id, reminder_id)
    now = utcnow()
    for field in ("title", "remind_at", "is_completed"):
        if field in provided and data.get(field) is None:
            raise Invalid(f"{field} cannot be empty.")
    if "remind_at" in provided and as_utc(reminder.remind_at) != data["remind_at"]:
        check_reminder_time(data["remind_at"], now)

    changed = []
    for field in ("title", "description", "remind_at"):
        if field in provided:
            current = getattr(reminder, field)
            value = data.get(field)
            same = (as_utc(current) == value) if isinstance(current, datetime) else current == value
            if not same:
                setattr(reminder, field, value)
                changed.append(field)
    if changed:
        record_activity(db, application, "reminder_updated", reminder_id=reminder.reminder_id, fields=changed)
    if "is_completed" in provided and data["is_completed"] != reminder.is_completed:
        reminder.is_completed = data["is_completed"]
        reminder.completed_at = now if reminder.is_completed else None
        record_activity(db, application, "reminder_completed" if reminder.is_completed else "reminder_reopened",
                        reminder_id=reminder.reminder_id)
        changed.append("is_completed")
    if changed:
        db.commit()
        db.refresh(reminder)
    return reminder


def delete_reminder(db: Session, user_id: int, reminder_id: int) -> None:
    reminder, application = _locked_reminder(db, user_id, reminder_id)
    record_activity(db, application, "reminder_deleted", reminder_id=reminder.reminder_id)
    db.delete(reminder)
    db.commit()


# ------------------------------------------------------------------
# Bookmarks
# ------------------------------------------------------------------

def save_bookmark(db: Session, user_id: int, internship_id: int) -> tuple[SavedInternship, bool]:
    existing = get_bookmark(db, user_id, internship_id)
    if existing:
        return existing, False
    available_internship(db, internship_id, require_open_deadline=True)
    count = db.scalar(select(func.count()).select_from(SavedInternship).where(SavedInternship.user_id == user_id))
    if count >= MAX_BOOKMARKS:
        raise Conflict(f"You can save at most {MAX_BOOKMARKS} internships.")
    bookmark = SavedInternship(user_id=user_id, internship_id=internship_id)
    db.add(bookmark)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        saved = db.scalar(select(SavedInternship).where(SavedInternship.user_id == user_id,
                                                        SavedInternship.internship_id == internship_id))
        if saved is None:           # not a concurrent duplicate (for example the internship was removed)
            raise integrity_conflict(exc, GENERIC_CONFLICT) from None
        return saved, False         # saved concurrently by another request: return that one
    db.refresh(bookmark)
    return bookmark, True


def get_bookmark(db: Session, user_id: int, internship_id: int) -> SavedInternship | None:
    return db.scalar(select(SavedInternship).where(SavedInternship.user_id == user_id,
                                                   SavedInternship.internship_id == internship_id))


def delete_bookmark(db: Session, user_id: int, internship_id: int) -> None:
    bookmark = get_bookmark(db, user_id, internship_id)
    if bookmark is None:
        raise NotFound("Bookmark not found")
    db.delete(bookmark)
    db.commit()


# ------------------------------------------------------------------
# Read models
# ------------------------------------------------------------------

def summaries(db: Session, applications: list[Application], now: datetime) -> dict[int, dict[str, Any]]:
    """Batched per-application counts and next items (a fixed number of queries per page)."""
    ids = [a.application_id for a in applications]
    result: dict[int, dict[str, Any]] = {
        i: {"interview_count": 0, "next_interview": None, "pending_reminders": 0, "next_reminder": None,
            "internship": None} for i in ids}
    if not ids:
        return result
    for app_id, count in db.execute(
            select(ApplicationInterview.application_id, func.count())
            .where(ApplicationInterview.application_id.in_(ids)).group_by(ApplicationInterview.application_id)):
        result[app_id]["interview_count"] = count
    for interview in db.scalars(
            select(ApplicationInterview)
            .where(ApplicationInterview.application_id.in_(ids), ApplicationInterview.outcome == "pending",
                   ApplicationInterview.scheduled_at >= now)
            .order_by(ApplicationInterview.scheduled_at, ApplicationInterview.interview_id)):
        result[interview.application_id]["next_interview"] = (
            result[interview.application_id]["next_interview"] or interview)
    for app_id, count in db.execute(
            select(ApplicationReminder.application_id, func.count())
            .where(ApplicationReminder.application_id.in_(ids), ApplicationReminder.is_completed.is_(False))
            .group_by(ApplicationReminder.application_id)):
        result[app_id]["pending_reminders"] = count
    for reminder in db.scalars(
            select(ApplicationReminder)
            .where(ApplicationReminder.application_id.in_(ids), ApplicationReminder.is_completed.is_(False))
            .order_by(ApplicationReminder.remind_at, ApplicationReminder.reminder_id)):
        result[reminder.application_id]["next_reminder"] = (
            result[reminder.application_id]["next_reminder"] or reminder)
    internship_ids = {a.internship_id for a in applications if a.internship_id}
    if internship_ids:
        internships = {i.internship_id: i for i in db.scalars(
            select(Internship).where(Internship.internship_id.in_(internship_ids)))}
        for application in applications:
            if application.internship_id:
                result[application.application_id]["internship"] = internships.get(application.internship_id)
    return result


def related_links(db: Session, application: Application) -> dict[str, Any]:
    """Read-only links to Phase 3 (match), Phase 5 (documents) and Phase 6 (practice sessions)."""
    from backend.schemas.application_schema import to_utc_iso

    latest_match = None
    if application.internship_id:
        match = db.scalar(select(MatchResult).where(MatchResult.user_id == application.user_id,
                                                    MatchResult.internship_id == application.internship_id)
                          .order_by(MatchResult.created_at.desc(), MatchResult.match_id.desc()).limit(1))
        if match:
            latest_match = {"match_id": match.match_id, "run_id": str(match.run_id) if match.run_id else None,
                            "score": match.score, "label": match.label, "created_at": to_utc_iso(match.created_at)}
    documents = []
    for document_id in (application.resume_document_id, application.cover_letter_document_id):
        if document_id:
            document = db.scalar(select(GeneratedDocument).where(GeneratedDocument.document_id == document_id,
                                                                 GeneratedDocument.user_id == application.user_id))
            if document:
                documents.append({"document_id": document.document_id, "document_type": document.document_type,
                                  "title": document.title, "current_version": document.current_version})
    sessions = []
    if application.internship_id:
        for session in db.scalars(
                select(InterviewSession).where(InterviewSession.user_id == application.user_id,
                                               InterviewSession.internship_id == application.internship_id)
                .order_by(InterviewSession.started_at.desc(), InterviewSession.session_id.desc()).limit(5)):
            sessions.append({"session_id": session.session_id, "title": session.title, "mode": session.mode,
                             "status": session.status, "score": session.score,
                             "started_at": to_utc_iso(session.started_at)})
    return {
        "latest_match": latest_match,
        "documents": documents,
        "practice_sessions": sessions,
        "prepare_with": ({"method": "POST", "endpoint": "/interviews/sessions",
                          "body": {"internship_id": application.internship_id}}
                         if application.internship_id else None),
    }


def list_applications(db: Session, user_id: int, *, statuses: list[str] | None, source: str | None,
                      company: str | None, domain: str | None, q: str | None,
                      applied_from: datetime | None, applied_to: datetime | None,
                      created_from: datetime | None, created_to: datetime | None,
                      sort: str, order: str, skip: int, limit: int,
                      trash: bool = False) -> tuple[int, list[Application]]:
    query = select(Application).where(Application.user_id == user_id)
    query = query.where(Application.deleted_at.is_not(None) if trash else Application.deleted_at.is_(None))
    if statuses:
        query = query.where(Application.status.in_(statuses))
    if source:
        query = query.where(Application.source == source)
    if company:
        query = query.where(Application.company_name.ilike(f"%{escape_like(company)}%", escape="\\"))
    if domain:
        query = query.where(func.lower(Application.domain) == domain.strip().lower())
    if q:
        pattern = f"%{escape_like(q.strip())}%"
        query = query.where(or_(Application.title.ilike(pattern, escape="\\"),
                                Application.company_name.ilike(pattern, escape="\\")))
    if applied_from:
        query = query.where(Application.applied_at >= applied_from)
    if applied_to:
        query = query.where(Application.applied_at <= applied_to)
    if created_from:
        query = query.where(Application.created_at >= created_from)
    if created_to:
        query = query.where(Application.created_at <= created_to)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    column = {"created_at": Application.created_at, "updated_at": Application.updated_at,
              "applied_at": Application.applied_at, "company_name": func.lower(Application.company_name),
              "title": func.lower(Application.title), "status": Application.status,
              "deleted_at": Application.deleted_at}[sort]
    ordered = column.desc().nulls_last() if order == "desc" else column.asc().nulls_last()
    tiebreak = Application.application_id.desc() if order == "desc" else Application.application_id.asc()
    items = list(db.scalars(query.order_by(ordered, tiebreak).offset(skip).limit(limit)))
    return total, items


def list_reminders(db: Session, user_id: int, *, application_id: int | None, state: str,
                   due_from: datetime | None, due_to: datetime | None, overdue: bool | None,
                   skip: int, limit: int) -> tuple[int, list[ApplicationReminder]]:
    now = utcnow()
    query = (select(ApplicationReminder).join(Application)
             .where(Application.user_id == user_id, Application.deleted_at.is_(None)))
    if application_id is not None:
        query = query.where(ApplicationReminder.application_id == application_id)
    if state == "pending":
        query = query.where(ApplicationReminder.is_completed.is_(False))
    elif state == "completed":
        query = query.where(ApplicationReminder.is_completed.is_(True))
    if due_from:
        query = query.where(ApplicationReminder.remind_at >= due_from)
    if due_to:
        query = query.where(ApplicationReminder.remind_at <= due_to)
    if overdue is True:
        query = query.where(ApplicationReminder.is_completed.is_(False), ApplicationReminder.remind_at < now)
    elif overdue is False:
        query = query.where(or_(ApplicationReminder.is_completed.is_(True), ApplicationReminder.remind_at >= now))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = list(db.scalars(query.order_by(ApplicationReminder.remind_at, ApplicationReminder.reminder_id)
                            .offset(skip).limit(limit)))
    return total, items
