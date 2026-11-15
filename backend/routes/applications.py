"""Application tracking API (Phase 7).

Every endpoint requires login and only ever returns the caller's own
records; another student's id returns 404. The student id always comes from
the access token, never from the request. Fixed paths (dashboard,
bookmarks, reminders, interviews, trash) are registered before
``/{application_id}`` so they can never be read as an id.
"""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Application, ApplicationInterview, ApplicationReminder, Internship, SavedInternship, User
from backend.schemas.application_schema import (
    ApplicationCreate,
    ApplicationList,
    ApplicationOut,
    ApplicationUpdate,
    BookmarkList,
    BookmarkOut,
    BookmarkStatus,
    DashboardOut,
    HistoryOut,
    InterviewCreate,
    InterviewOut,
    InterviewUpdate,
    InternshipSummary,
    ReminderCreate,
    ReminderList,
    ReminderOut,
    ReminderUpdate,
    Status,
    StatusResult,
    StatusUpdate,
    require_aware,
)
from backend.services import application_service as svc
from backend.services.application_dashboard import dashboard as build_dashboard
from backend.utils.dependencies import get_current_user

router = APIRouter(prefix="/applications", tags=["Application Tracking"])

SortField = Literal["created_at", "updated_at", "applied_at", "company_name", "title", "status"]


def fail(exc: svc.ApplicationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def aware(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return require_aware(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{name}: {exc}") from None


def ordered_range(start: datetime | None, end: datetime | None, names: str) -> None:
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"{names}: the start must not be after the end.")


def not_blank(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{name} cannot be blank.")
    return value


# ------------------------------------------------------------------
# Serialisation
# ------------------------------------------------------------------

def internship_summary(internship: Internship) -> InternshipSummary:
    return InternshipSummary(
        internship_id=internship.internship_id, title=internship.title, company=internship.company,
        location=internship.location, work_mode=internship.work_mode, domain=internship.domain,
        deadline=internship.deadline, is_active=internship.is_active,
        deadline_passed=svc.deadline_passed(internship))


def interview_out(interview: ApplicationInterview, change: dict | None = None) -> InterviewOut:
    return InterviewOut(
        interview_id=interview.interview_id, application_id=interview.application_id,
        round_number=interview.round_number, interview_type=interview.interview_type, mode=interview.mode,
        scheduled_at=interview.scheduled_at, duration_minutes=interview.duration_minutes,
        meeting_url=interview.meeting_url, location=interview.location,
        preparation_notes=interview.preparation_notes, feedback=interview.feedback, outcome=interview.outcome,
        interview_session_id=interview.interview_session_id, created_at=interview.created_at,
        updated_at=interview.updated_at, status_change=change)


def reminder_out(reminder: ApplicationReminder, application: Application, now: datetime) -> ReminderOut:
    remind_at = svc.as_utc(reminder.remind_at)
    pending = not reminder.is_completed
    return ReminderOut(
        reminder_id=reminder.reminder_id, application_id=application.application_id,
        application_title=application.title, company_name=application.company_name, title=reminder.title,
        description=reminder.description, remind_at=reminder.remind_at, is_completed=reminder.is_completed,
        completed_at=reminder.completed_at, overdue=pending and remind_at < now,
        due_within_24h=pending and now <= remind_at <= now + timedelta(hours=24),
        created_at=reminder.created_at, updated_at=reminder.updated_at)


def application_out(db: Session, application: Application, *, detail: bool = False,
                    summary: dict | None = None, duplicates: list[int] | None = None) -> ApplicationOut:
    now = svc.utcnow()
    summary = summary or svc.summaries(db, [application], now)[application.application_id]
    internship = summary["internship"]
    return ApplicationOut(
        application_id=application.application_id, source=application.source,
        internship_id=application.internship_id, company_name=application.company_name, title=application.title,
        application_url=application.application_url, external_reference=application.external_reference,
        domain=application.domain, location=application.location, work_mode=application.work_mode,
        status=application.status, applied_at=application.applied_at,
        status_changed_at=application.status_changed_at, notes=application.notes,
        contact_name=application.contact_name, contact_email=application.contact_email,
        resume_document_id=application.resume_document_id,
        cover_letter_document_id=application.cover_letter_document_id,
        internship_active=internship.is_active if internship else None,
        deadline_passed=svc.deadline_passed(internship, now) if internship else None,
        interview_count=summary["interview_count"],
        next_interview=interview_out(summary["next_interview"]) if summary["next_interview"] else None,
        pending_reminders=summary["pending_reminders"],
        next_reminder=reminder_out(summary["next_reminder"], application, now) if summary["next_reminder"] else None,
        deleted_at=application.deleted_at, created_at=application.created_at, updated_at=application.updated_at,
        possible_duplicates=duplicates or [],
        related=svc.related_links(db, application) if detail else None)


def page_out(db: Session, total: int, skip: int, limit: int, items: list[Application]) -> ApplicationList:
    summaries = svc.summaries(db, items, svc.utcnow())
    return ApplicationList(total=total, skip=skip, limit=limit, items=[
        application_out(db, a, summary=summaries[a.application_id]) for a in items])


def applied_ids(db: Session, user_id: int, internship_ids: list[int]) -> dict[int, int]:
    """internship_id -> active application_id, in one query."""
    if not internship_ids:
        return {}
    return {internship_id: application_id for internship_id, application_id in db.execute(
        select(Application.internship_id, Application.application_id).where(
            Application.user_id == user_id, Application.internship_id.in_(internship_ids),
            Application.deleted_at.is_(None)))}


def bookmark_out(db: Session, bookmark: SavedInternship, application_id: int | None = -1) -> BookmarkOut:
    if application_id == -1:
        application_id = applied_ids(db, bookmark.user_id, [bookmark.internship_id]).get(bookmark.internship_id)
    return BookmarkOut(bookmark_id=bookmark.bookmark_id, internship_id=bookmark.internship_id,
                       created_at=bookmark.created_at, internship=internship_summary(bookmark.internship),
                       application_id=application_id)


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return build_dashboard(db, current_user.user_id)


# ------------------------------------------------------------------
# Bookmarks
# ------------------------------------------------------------------

@router.get("/bookmarks", response_model=BookmarkList)
def list_bookmarks(skip: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    base = select(SavedInternship).where(SavedInternship.user_id == current_user.user_id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    items = list(db.scalars(base.order_by(SavedInternship.created_at.desc(), SavedInternship.bookmark_id.desc())
                            .offset(skip).limit(limit)))
    applied = applied_ids(db, current_user.user_id, [b.internship_id for b in items])
    return BookmarkList(total=total, skip=skip, limit=limit,
                        items=[bookmark_out(db, b, applied.get(b.internship_id)) for b in items])


@router.post("/bookmarks/{internship_id}", response_model=BookmarkOut)
def save_bookmark(internship_id: int, response: Response, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    try:
        bookmark, created = svc.save_bookmark(db, current_user.user_id, internship_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return bookmark_out(db, bookmark)


@router.get("/bookmarks/{internship_id}", response_model=BookmarkStatus)
def bookmark_status(internship_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    bookmark = svc.get_bookmark(db, current_user.user_id, internship_id)
    return BookmarkStatus(saved=bookmark is not None, bookmark=bookmark_out(db, bookmark) if bookmark else None)


@router.delete("/bookmarks/{internship_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_bookmark(internship_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    try:
        svc.delete_bookmark(db, current_user.user_id, internship_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------
# Reminders (stored only; never delivered by e-mail or SMS)
# ------------------------------------------------------------------

@router.get("/reminders", response_model=ReminderList)
def list_reminders(
    application_id: int | None = Query(default=None, ge=1),
    state: Literal["pending", "completed", "all"] = Query(default="pending", alias="status"),
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    overdue: bool | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    due_from, due_to = aware(due_from, "due_from"), aware(due_to, "due_to")
    ordered_range(due_from, due_to, "due_from/due_to")
    total, items = svc.list_reminders(
        db, current_user.user_id, application_id=application_id, state=state,
        due_from=due_from, due_to=due_to, overdue=overdue, skip=skip, limit=limit)
    now = svc.utcnow()
    return ReminderList(total=total, skip=skip, limit=limit,
                        items=[reminder_out(r, r.application, now) for r in items])


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
def update_reminder(reminder_id: int, request: ReminderUpdate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    try:
        reminder = svc.update_reminder(db, current_user.user_id, reminder_id, request.model_dump(),
                                       request.model_fields_set)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return reminder_out(reminder, reminder.application, svc.utcnow())


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_reminder(reminder_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    try:
        svc.delete_reminder(db, current_user.user_id, reminder_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------
# Interview rounds by id
# ------------------------------------------------------------------

@router.get("/interviews/{interview_id}", response_model=InterviewOut)
def get_interview(interview_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    try:
        return interview_out(svc.owned_interview(db, current_user.user_id, interview_id))
    except svc.ApplicationError as exc:
        raise fail(exc)


@router.patch("/interviews/{interview_id}", response_model=InterviewOut)
def update_interview(interview_id: int, request: InterviewUpdate, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    try:
        interview, change = svc.update_interview(db, current_user.user_id, interview_id, request.model_dump(),
                                                 request.model_fields_set)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return interview_out(interview, change)


@router.delete("/interviews/{interview_id}")
def delete_interview(interview_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    try:
        change = svc.delete_interview(db, current_user.user_id, interview_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return {"deleted": True, "status_change": change}


# ------------------------------------------------------------------
# Applications
# ------------------------------------------------------------------

def _list(db, user, trash, **kwargs):
    total, items = svc.list_applications(db, user.user_id, trash=trash, **kwargs)
    return page_out(db, total, kwargs["skip"], kwargs["limit"], items)


@router.get("/trash", response_model=ApplicationList)
def list_trash(skip: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
               db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _list(db, current_user, True, statuses=None, source=None, company=None, domain=None, q=None,
                 applied_from=None, applied_to=None, created_from=None, created_to=None,
                 sort="deleted_at", order="desc", skip=skip, limit=limit)


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(request: ApplicationCreate, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    try:
        application = svc.create_application(db, current_user.user_id, request.model_dump(),
                                             request.model_fields_set)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return application_out(db, application, detail=True, duplicates=svc.possible_duplicates(db, application))


@router.get("", response_model=ApplicationList)
def list_applications(
    status_filter: list[Status] | None = Query(default=None, alias="status"),
    source: Literal["internal", "external"] | None = None,
    company: str | None = Query(default=None, min_length=1, max_length=100),
    domain: str | None = Query(default=None, min_length=1, max_length=80),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    applied_from: datetime | None = None,
    applied_to: datetime | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: SortField = "updated_at",
    order: Literal["asc", "desc"] = "desc",
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    applied_from, applied_to = aware(applied_from, "applied_from"), aware(applied_to, "applied_to")
    created_from, created_to = aware(created_from, "created_from"), aware(created_to, "created_to")
    ordered_range(applied_from, applied_to, "applied_from/applied_to")
    ordered_range(created_from, created_to, "created_from/created_to")
    return _list(db, current_user, False, statuses=status_filter, source=source,
                 company=not_blank(company, "company"), domain=not_blank(domain, "domain"), q=not_blank(q, "q"),
                 applied_from=applied_from, applied_to=applied_to, created_from=created_from,
                 created_to=created_to, sort=sort, order=order, skip=skip, limit=limit)


@router.get("/{application_id}", response_model=ApplicationOut)
def get_application(application_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    try:
        application = svc.owned_application(db, current_user.user_id, application_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return application_out(db, application, detail=True)


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(application_id: int, request: ApplicationUpdate, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    try:
        application = svc.update_application(db, current_user.user_id, application_id, request.model_dump(),
                                             request.model_fields_set)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return application_out(db, application, detail=True, duplicates=svc.possible_duplicates(db, application))


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def trash_application(application_id: int, confirm: bool = False, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    if not confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Add ?confirm=true to move this application to the trash. "
                                   "Consider setting the status to WITHDRAWN instead.")
    try:
        svc.move_to_trash(db, current_user.user_id, application_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{application_id}/restore", response_model=ApplicationOut)
def restore_application(application_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    try:
        application = svc.restore_application(db, current_user.user_id, application_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return application_out(db, application, detail=True)


@router.delete("/{application_id}/permanent", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_application_permanently(application_id: int, confirm: bool = False, db: Session = Depends(get_db),
                                   current_user: User = Depends(get_current_user)):
    if not confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Add ?confirm=true to delete this application and all its history, "
                                   "interviews, reminders and activity permanently. This cannot be undone.")
    try:
        svc.delete_permanently(db, current_user.user_id, application_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{application_id}/status", response_model=StatusResult)
def update_status(application_id: int, request: StatusUpdate, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    try:
        application, changed, previous = svc.change_status(
            db, current_user.user_id, application_id, request.status, correction=request.correction,
            expected_status=request.expected_status)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return StatusResult(changed=changed, from_status=previous, to_status=application.status,
                        application=application_out(db, application),
                        warnings=svc.pending_round_warnings(db, application) if changed else [])


@router.get("/{application_id}/history", response_model=HistoryOut)
def get_history(application_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    try:
        application = svc.owned_application(db, current_user.user_id, application_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return HistoryOut(
        application_id=application.application_id,
        status_history=[{"history_id": h.history_id, "from_status": h.from_status, "to_status": h.to_status,
                         "change_type": h.change_type, "changed_at": h.changed_at}
                        for h in application.status_history],
        activity=[{"activity_id": a.activity_id, "event_type": a.event_type, "details": a.details,
                   "created_at": a.created_at} for a in application.activity])


@router.post("/{application_id}/interviews", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
def add_interview(application_id: int, request: InterviewCreate, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    try:
        interview, change = svc.add_interview(db, current_user.user_id, application_id, request.model_dump())
    except svc.ApplicationError as exc:
        raise fail(exc)
    return interview_out(interview, change)


@router.get("/{application_id}/interviews", response_model=list[InterviewOut])
def list_interviews(application_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    try:
        application = svc.owned_application(db, current_user.user_id, application_id)
    except svc.ApplicationError as exc:
        raise fail(exc)
    return [interview_out(i) for i in application.interviews]


@router.post("/{application_id}/reminders", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def add_reminder(application_id: int, request: ReminderCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    try:
        reminder = svc.add_reminder(db, current_user.user_id, application_id, request.model_dump())
    except svc.ApplicationError as exc:
        raise fail(exc)
    return reminder_out(reminder, reminder.application, svc.utcnow())
