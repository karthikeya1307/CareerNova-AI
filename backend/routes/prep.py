"""Interview preparation agent API (HR assignment). Signed-in users; read-only.

Every endpoint uses only the signed-in student's own parsed resume (``?resume_id=`` must be theirs;
default: their latest parsed resume). Without a parsed resume the answer is 409 ``resume_required``.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Resume, User
from backend.services import career_tracks, prep, skill_progress
from backend.services.prep.questions import LEVELS
from backend.utils.dependencies import get_current_user

router = APIRouter(prefix="/prep", tags=["Interview Preparation Agent"])


def context_or_409(db: Session, user: User, resume_id: int | None) -> prep.ResumeContext:
    if resume_id is not None and db.scalar(select(Resume.resume_id).where(
            Resume.resume_id == resume_id, Resume.user_id == user.user_id)) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    ctx = prep.load_context(db, user.user_id, resume_id)
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "resume_required",
            "message": "Upload a resume and wait for it to be parsed - preparation is based on your resume."})
    return ctx


def track_or_404(slug: str) -> dict:
    track = career_tracks.get_track(slug)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return track


@router.get("/profile")
def resume_profile(resume_id: int | None = Query(default=None), db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    ctx = context_or_409(db, current_user, resume_id)
    return {**prep.profile(ctx), "strengths": prep.skill_evidence(ctx)}


@router.get("/roles")
def recommended_roles(resume_id: int | None = Query(default=None), limit: int = Query(default=5, ge=1, le=14),
                      db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ctx = context_or_409(db, current_user, resume_id)
    from backend.services.prep.internships import for_role
    roles = prep.recommend(ctx, limit)
    for role in roles:
        role["internships"] = for_role(db, career_tracks.get_track(role["slug"]), ctx, 3)
    return {"resume_id": ctx.resume.resume_id, "algorithm": "roles-v1", "roles": roles,
            "note": "Fit = 75% core skills + 25% advanced skills found on your resume. Guidance, not a hiring prediction."}


@router.get("/roles/{slug}")
def role_fit(slug: str, resume_id: int | None = Query(default=None), db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    track = track_or_404(slug)
    return prep.assess(track, context_or_409(db, current_user, resume_id))


@router.get("/roles/{slug}/technical-questions")
def technical_questions(slug: str, level: str | None = Query(default=None), resume_id: int | None = Query(default=None),
                        db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if level is not None and level not in LEVELS:
        raise HTTPException(status_code=422, detail=f"level must be one of {', '.join(LEVELS)}")
    track = track_or_404(slug)
    return prep.technical_questions(track, context_or_409(db, current_user, resume_id), level)


@router.get("/roles/{slug}/hr-questions")
def hr_questions(slug: str, resume_id: int | None = Query(default=None), db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    track = track_or_404(slug)
    return prep.hr_questions(track, context_or_409(db, current_user, resume_id))


@router.get("/guidance/{question_id}")
def answer_guidance(question_id: str, role: str | None = Query(default=None), resume_id: int | None = Query(default=None),
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    track = track_or_404(role) if role else None
    result = prep.guidance(question_id[:80], context_or_409(db, current_user, resume_id), track)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return result


@router.get("/roles/{slug}/roadmap")
def preparation_roadmap(slug: str, resume_id: int | None = Query(default=None), db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    track = track_or_404(slug)
    ctx = context_or_409(db, current_user, resume_id)
    progress = {k: v["status"] for k, v in skill_progress.statuses_for(db, current_user.user_id).items()}
    return prep.roadmap(track, ctx, progress)
