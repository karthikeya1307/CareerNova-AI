"""Request/response schemas for application tracking (Phase 7).

Time handling: every incoming timestamp must carry a UTC offset (for
example ``2026-11-20T10:30:00+05:30`` for India Standard Time, or a ``Z``
suffix). It is converted to UTC before storage. Every timestamp in a Phase 7
response is returned in UTC ISO 8601 form ending in ``Z``.

Request bodies reject unknown fields, so a ``user_id`` (or ``status`` on the
details endpoint) can never be smuggled in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, PlainSerializer

from backend.models import APPLICATION_STATUSES, INTERVIEW_MODES, INTERVIEW_OUTCOMES, INTERVIEW_TYPES

Status = Literal["SAVED", "APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"]
InterviewType = Literal["technical", "hr", "behavioral", "managerial", "case_study", "assignment", "group", "other"]
InterviewMode = Literal["online", "offline", "phone"]
InterviewOutcome = Literal["pending", "passed", "failed", "cancelled", "no_show"]
WorkMode = Literal["Onsite", "Hybrid", "Remote"]

assert set(Status.__args__) == set(APPLICATION_STATUSES)
assert set(InterviewType.__args__) == set(INTERVIEW_TYPES)
assert set(InterviewMode.__args__) == set(INTERVIEW_MODES)
assert set(InterviewOutcome.__args__) == set(INTERVIEW_OUTCOMES)

MAX_URL = 1000
MAX_NOTES = 5000
MAX_DESCRIPTION = 2000


# ------------------------------------------------------------------
# Shared field types
# ------------------------------------------------------------------

def require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Include a timezone offset, for example 2026-11-20T10:30:00+05:30 (IST) or ...Z (UTC).")
    return value.astimezone(timezone.utc)


def to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_url(value: str) -> str:
    value = value.strip()
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError("A URL cannot contain spaces or control characters.")
    parts = urlsplit(value)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError("Enter a full http:// or https:// URL.")
    return value


def strip_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Cannot be blank.")
    return value


AwareDateTime = Annotated[datetime, AfterValidator(require_aware)]
UTCDateTime = Annotated[datetime, PlainSerializer(to_utc_iso, return_type=str)]
Url = Annotated[str, Field(min_length=1, max_length=MAX_URL), AfterValidator(clean_url)]
Name = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(strip_text)]
Short = Annotated[str, Field(min_length=1, max_length=150), AfterValidator(strip_text)]
Notes = Annotated[str, Field(max_length=MAX_NOTES)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------
# Requests
# ------------------------------------------------------------------

class ApplicationCreate(StrictModel):
    internship_id: int | None = Field(default=None, ge=1)
    company_name: Name | None = None
    title: Name | None = None
    application_url: Url | None = None
    external_reference: Annotated[str, Field(min_length=1, max_length=100), AfterValidator(strip_text)] | None = None
    domain: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(strip_text)] | None = None
    location: Short | None = None
    work_mode: WorkMode | None = None
    status: Literal["SAVED", "APPLIED"] = "SAVED"
    applied_at: AwareDateTime | None = None
    notes: Notes | None = None
    contact_name: Annotated[str, Field(min_length=1, max_length=120), AfterValidator(strip_text)] | None = None
    contact_email: Annotated[EmailStr, Field(max_length=255)] | None = None
    resume_document_id: int | None = Field(default=None, ge=1)
    cover_letter_document_id: int | None = Field(default=None, ge=1)


class ApplicationUpdate(StrictModel):
    """Details only. Status changes go through PATCH /applications/{id}/status."""

    company_name: Name | None = None
    title: Name | None = None
    application_url: Url | None = None
    external_reference: Annotated[str, Field(min_length=1, max_length=100), AfterValidator(strip_text)] | None = None
    domain: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(strip_text)] | None = None
    location: Short | None = None
    work_mode: WorkMode | None = None
    applied_at: AwareDateTime | None = None
    notes: Notes | None = None
    contact_name: Annotated[str, Field(min_length=1, max_length=120), AfterValidator(strip_text)] | None = None
    contact_email: Annotated[EmailStr, Field(max_length=255)] | None = None
    resume_document_id: int | None = Field(default=None, ge=1)
    cover_letter_document_id: int | None = Field(default=None, ge=1)


class StatusUpdate(StrictModel):
    status: Status
    correction: bool = False
    expected_status: Status | None = None


class InterviewCreate(StrictModel):
    interview_type: InterviewType
    mode: InterviewMode
    scheduled_at: AwareDateTime
    duration_minutes: int | None = Field(default=None, ge=5, le=600)
    meeting_url: Annotated[str, Field(min_length=1, max_length=500), AfterValidator(clean_url)] | None = None
    location: Annotated[str, Field(min_length=1, max_length=200), AfterValidator(strip_text)] | None = None
    preparation_notes: Notes | None = None
    feedback: Notes | None = None
    outcome: InterviewOutcome = "pending"
    interview_session_id: int | None = Field(default=None, ge=1)


class InterviewUpdate(StrictModel):
    interview_type: InterviewType | None = None
    mode: InterviewMode | None = None
    scheduled_at: AwareDateTime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=600)
    meeting_url: Annotated[str, Field(min_length=1, max_length=500), AfterValidator(clean_url)] | None = None
    location: Annotated[str, Field(min_length=1, max_length=200), AfterValidator(strip_text)] | None = None
    preparation_notes: Notes | None = None
    feedback: Notes | None = None
    outcome: InterviewOutcome | None = None
    interview_session_id: int | None = Field(default=None, ge=1)


class ReminderCreate(StrictModel):
    title: Short
    description: Annotated[str, Field(max_length=MAX_DESCRIPTION)] | None = None
    remind_at: AwareDateTime


class ReminderUpdate(StrictModel):
    title: Short | None = None
    description: Annotated[str, Field(max_length=MAX_DESCRIPTION)] | None = None
    remind_at: AwareDateTime | None = None
    is_completed: bool | None = None


# ------------------------------------------------------------------
# Responses
# ------------------------------------------------------------------

class InternshipSummary(BaseModel):
    internship_id: int
    title: str
    company: str
    location: str | None
    work_mode: str | None
    domain: str | None
    deadline: UTCDateTime | None
    is_active: bool
    deadline_passed: bool


class BookmarkOut(BaseModel):
    bookmark_id: int
    internship_id: int
    created_at: UTCDateTime
    internship: InternshipSummary
    application_id: int | None


class BookmarkStatus(BaseModel):
    saved: bool
    bookmark: BookmarkOut | None


class BookmarkList(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[BookmarkOut]


class StatusChange(BaseModel):
    from_status: str
    to_status: str
    reason: str


class InterviewOut(BaseModel):
    interview_id: int
    application_id: int
    round_number: int
    interview_type: str
    mode: str
    scheduled_at: UTCDateTime
    duration_minutes: int | None
    meeting_url: str | None
    location: str | None
    preparation_notes: str | None
    feedback: str | None
    outcome: str
    interview_session_id: int | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    status_change: StatusChange | None = None


class ReminderOut(BaseModel):
    reminder_id: int
    application_id: int
    application_title: str
    company_name: str
    title: str
    description: str | None
    remind_at: UTCDateTime
    is_completed: bool
    completed_at: UTCDateTime | None
    overdue: bool
    due_within_24h: bool
    delivery: Literal["not_sent"] = "not_sent"
    created_at: UTCDateTime
    updated_at: UTCDateTime


class ReminderList(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[ReminderOut]


class ApplicationOut(BaseModel):
    application_id: int
    source: str
    internship_id: int | None
    company_name: str
    title: str
    application_url: str | None
    external_reference: str | None
    domain: str | None
    location: str | None
    work_mode: str | None
    status: str
    applied_at: UTCDateTime | None
    status_changed_at: UTCDateTime | None
    notes: str | None
    contact_name: str | None
    contact_email: str | None
    resume_document_id: int | None
    cover_letter_document_id: int | None
    internship_active: bool | None
    deadline_passed: bool | None
    interview_count: int
    next_interview: InterviewOut | None
    pending_reminders: int
    next_reminder: ReminderOut | None
    deleted_at: UTCDateTime | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    possible_duplicates: list[int] = []
    related: dict[str, Any] | None = None       # read-only links to Phases 3, 5 and 6 (detail view only)


class ApplicationList(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[ApplicationOut]


class StatusResult(BaseModel):
    changed: bool
    from_status: str
    to_status: str
    application: ApplicationOut
    warnings: list[str] = []


class HistoryEntry(BaseModel):
    history_id: int
    from_status: str | None
    to_status: str
    change_type: str
    changed_at: UTCDateTime


class ActivityEntry(BaseModel):
    activity_id: int
    event_type: str
    details: dict[str, Any] | None
    created_at: UTCDateTime


class HistoryOut(BaseModel):
    application_id: int
    status_history: list[HistoryEntry]
    activity: list[ActivityEntry]


class UpcomingInterview(BaseModel):
    interview_id: int
    application_id: int
    company_name: str
    title: str
    round_number: int
    interview_type: str
    mode: str
    scheduled_at: UTCDateTime


class DashboardOut(BaseModel):
    generated_at: UTCDateTime
    saved_internships: int
    total_applications: int
    by_status: dict[str, int]
    submitted_applications: int
    selected: int
    rejected: int
    interviews_scheduled: int
    upcoming_interviews: int
    next_interviews: list[UpcomingInterview]
    pending_reminders: int
    overdue_reminders: int
    completed_reminders: int
    success_rate: float | None
    decision_rate: float | None
    interview_rate: float | None
    formulas: dict[str, str]
    recent_activity: list[dict[str, Any]]
