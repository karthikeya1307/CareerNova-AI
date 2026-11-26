"""Career tracks for 14 roles (P3). Read-only; signed-in users."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import Internship, InternshipSkill, Resume, User
from backend.routes.internships import to_response
from backend.services import career_tracks, skill_progress
from backend.services.matching_agent import is_eligible
from backend.services.skill_gap import candidate_skill_names
from backend.utils.dependencies import get_current_user

router = APIRouter(prefix="/career-tracks", tags=["Career Tracks"])


def track_or_404(slug: str) -> dict:
    track = career_tracks.get_track(slug)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Career track not found")
    return track


def owned_resume_skills(db: Session, user: User, resume_id: int | None) -> list[str] | None:
    if resume_id is None:
        return None
    resume = db.scalar(select(Resume).where(Resume.resume_id == resume_id, Resume.user_id == user.user_id))
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return candidate_skill_names(db, resume.resume_id)


@router.get("")
def list_tracks(current_user: User = Depends(get_current_user)):
    return [career_tracks.summary(t) for t in career_tracks.load_tracks()]


@router.get("/{slug}")
def get_track(
    slug: str,
    resume_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    track = track_or_404(slug)
    skills = owned_resume_skills(db, current_user, resume_id)
    return career_tracks.detail(track, skills, skill_progress.statuses_for(db, current_user.user_id))


@router.get("/{slug}/jobs")
def get_track_jobs(
    slug: str,
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Open listings that ask for this track's skills (most overlap first)."""
    track = track_or_404(slug)
    internships = [i for i in db.scalars(
        select(Internship).where(Internship.is_active.is_(True))
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
    ) if is_eligible(i)]
    ranked = career_tracks.relevant_jobs(track, internships, limit)
    return {"track": slug, "items": [{"internship": to_response(i), "track_skill_overlap": score} for i, score in ranked]}
