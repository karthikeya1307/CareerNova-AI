"""Application dashboard (Phase 7): counts and rates for ONE student.

Every query is filtered by the authenticated user's id and excludes
applications in the trash. Empty accounts return zeros and ``None`` rates.

Formulas (percentages rounded to one decimal place):
  submitted_applications = applications with applied_at set (submitted at some point)
  success_rate   = submitted SELECTED / submitted_applications x 100 (None if nothing submitted)
  decision_rate  = SELECTED / (SELECTED + REJECTED) x 100         (None if no decisions yet)
  interview_rate = submitted applications with >= 1 non-cancelled
                   interview round / submitted_applications x 100 (None if nothing submitted)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    APPLICATION_STATUSES,
    Application,
    ApplicationActivity,
    ApplicationInterview,
    ApplicationReminder,
    SavedInternship,
)
from backend.services.application_service import utcnow

FORMULAS = {
    "submitted_applications": "applications with an application date (submitted at some point)",
    "success_rate": "SELECTED applications that were submitted / submitted_applications x 100",
    "decision_rate": "SELECTED / (SELECTED + REJECTED) x 100",
    "interview_rate": "submitted applications with at least one non-cancelled interview round / "
                      "submitted_applications x 100",
}


def _rate(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 1) if denominator else None


def dashboard(db: Session, user_id: int, now: datetime | None = None) -> dict[str, Any]:
    from backend.schemas.application_schema import to_utc_iso

    now = now or utcnow()
    active = (Application.user_id == user_id, Application.deleted_at.is_(None))

    by_status = {status: 0 for status in APPLICATION_STATUSES}
    for status, count in db.execute(select(Application.status, func.count()).where(*active)
                                    .group_by(Application.status)):
        by_status[status] = count
    total = sum(by_status.values())
    submitted = db.scalar(select(func.count()).select_from(Application)
                          .where(*active, Application.applied_at.is_not(None)))
    # Only submitted applications count towards the success rate, so it can never exceed 100% (M2).
    selected_submitted = db.scalar(select(func.count()).select_from(Application)
                                   .where(*active, Application.applied_at.is_not(None),
                                          Application.status == "SELECTED"))
    with_interviews = db.scalar(
        select(func.count(func.distinct(Application.application_id))).select_from(Application)
        .join(ApplicationInterview)
        .where(*active, Application.applied_at.is_not(None), ApplicationInterview.outcome != "cancelled"))

    rounds = select(ApplicationInterview, Application).join(Application).where(*active)
    interviews_scheduled = db.scalar(select(func.count()).select_from(
        rounds.where(ApplicationInterview.outcome != "cancelled").subquery()))
    upcoming_query = rounds.where(ApplicationInterview.outcome == "pending", ApplicationInterview.scheduled_at >= now)
    upcoming = db.scalar(select(func.count()).select_from(upcoming_query.subquery()))
    next_interviews = [{
        "interview_id": interview.interview_id, "application_id": application.application_id,
        "company_name": application.company_name, "title": application.title,
        "round_number": interview.round_number, "interview_type": interview.interview_type,
        "mode": interview.mode, "scheduled_at": interview.scheduled_at,
    } for interview, application in db.execute(
        upcoming_query.order_by(ApplicationInterview.scheduled_at, ApplicationInterview.interview_id).limit(5))]

    reminders = select(ApplicationReminder).join(Application).where(*active)

    def count(query) -> int:
        return db.scalar(select(func.count()).select_from(query.subquery()))

    pending = count(reminders.where(ApplicationReminder.is_completed.is_(False)))
    overdue = count(reminders.where(ApplicationReminder.is_completed.is_(False), ApplicationReminder.remind_at < now))
    completed = count(reminders.where(ApplicationReminder.is_completed.is_(True)))

    recent = [{
        "activity_id": activity.activity_id, "application_id": application.application_id,
        "company_name": application.company_name, "title": application.title,
        "event_type": activity.event_type, "details": activity.details,
        "created_at": to_utc_iso(activity.created_at),
    } for activity, application in db.execute(
        select(ApplicationActivity, Application).join(Application).where(*active)
        .order_by(ApplicationActivity.created_at.desc(), ApplicationActivity.activity_id.desc()).limit(10))]

    saved = db.scalar(select(func.count()).select_from(SavedInternship).where(SavedInternship.user_id == user_id))
    selected, rejected = by_status["SELECTED"], by_status["REJECTED"]
    return {
        "generated_at": now,
        "saved_internships": saved,
        "total_applications": total,
        "by_status": by_status,
        "submitted_applications": submitted,
        "selected": selected,
        "rejected": rejected,
        "interviews_scheduled": interviews_scheduled,
        "upcoming_interviews": upcoming,
        "next_interviews": next_interviews,
        "pending_reminders": pending,
        "overdue_reminders": overdue,
        "completed_reminders": completed,
        "success_rate": _rate(selected_submitted, submitted),
        "decision_rate": _rate(selected, selected + rejected),
        "interview_rate": _rate(with_interviews, submitted),
        "formulas": FORMULAS,
        "recent_activity": recent,
    }
