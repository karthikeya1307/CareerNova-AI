
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import (
    Internship,
    InternshipSkill,
    MatchResult,
    Resume,
    SkillGapRecommendation,
    User,
)
from backend.schemas.skill_gap_schema import (
    GapStatus,
    GenerateRequest,
    GenerateResponse,
    InternshipGapResponse,
    RecommendationItem,
    StatusUpdate,
)
from backend.services.candidate_profile import InsufficientResumeDataError
from backend.services.learning_plans import plans_version
from backend.services.matching_agent import is_eligible, score_single
from backend.services.skill_gap import (
    GAP_ALGORITHM_VERSION,
    analyse_internship,
    candidate_skill_names,
    generate_recommendations,
    update_status,
)
from backend.utils.dependencies import get_current_user


router = APIRouter(
    prefix="/skill-gaps",
    tags=["Skill Gap Analysis"]
)


# ============================================================
# HELPERS
# ============================================================

def get_owned_resume(db: Session, resume_id: int, user: User) -> Resume:
    resume = db.scalar(
        select(Resume).where(Resume.resume_id == resume_id, Resume.user_id == user.user_id)
    )
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


def load_internships(db: Session, ids: list[int]) -> dict[int, Internship]:
    return {
        i.internship_id: i for i in db.scalars(
            select(Internship)
            .where(Internship.internship_id.in_(ids))
            .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
        )
    }


def internship_ref(internship: Internship) -> dict:
    return {
        "internship_id": internship.internship_id,
        "title": internship.title,
        "company": internship.company,
        "domain": internship.domain,
        "is_active": internship.is_active,
    }


def to_item(rec: SkillGapRecommendation) -> RecommendationItem:
    return RecommendationItem(
        recommendation_id=rec.recommendation_id,
        resume_id=rec.resume_id,
        skill_id=rec.skill_id,
        skill=rec.skill.name,
        category=rec.skill.category,
        gap_level=rec.gap_level,
        importance=rec.importance,
        priority_score=rec.priority_score,
        demand_count=rec.demand_count,
        internship_ids=rec.internship_ids or [],
        related_skills=rec.related_skills or [],
        recommended_action=rec.recommended_action,
        learning_plan=rec.learning_plan,
        learning_plan_version=rec.learning_plan_version,
        status=rec.status,
        completed_via=rec.completed_via,
        is_current=rec.is_current,
        source=rec.source,
        source_run_id=rec.source_run_id,
        top_internship=internship_ref(rec.internship) if rec.internship else None,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        started_at=rec.started_at,
        completed_at=rec.completed_at,
    )


# ============================================================
# ANALYSE ONE INTERNSHIP (read-only)
# GET /skill-gaps/resumes/{resume_id}/internships/{internship_id}
# ============================================================

@router.get(
    "/resumes/{resume_id}/internships/{internship_id}",
    response_model=InternshipGapResponse,
)
def analyse_one_internship(
    resume_id: int,
    internship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)
    internship = load_internships(db, [internship_id]).get(internship_id)

    if internship is None or not is_eligible(internship):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")

    report = analyse_internship(candidate_skill_names(db, resume.resume_id), internship)
    return {"resume_id": resume.resume_id, "internship": internship_ref(internship), **report}


# ============================================================
# GENERATE / REFRESH RECOMMENDATIONS
# POST /skill-gaps/resumes/{resume_id}
# ============================================================

@router.post(
    "/resumes/{resume_id}",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate(
    resume_id: int,
    request: GenerateRequest = Body(default_factory=GenerateRequest),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)

    if not candidate_skill_names(db, resume.resume_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This resume has no recognised skills. Add a skills section and re-parse it.",
        )

    skipped: list[int] = []
    items: list[tuple[Internship, float]] = []

    if request.internship_ids is not None:
        source, run_id = "selection", None
        found = load_internships(db, request.internship_ids)
        unavailable = [i for i in request.internship_ids if i not in found or not is_eligible(found[i])]
        if unavailable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Internships not found or no longer available: {unavailable}",
            )
        for internship_id in request.internship_ids:
            internship = found[internship_id]
            try:
                result, _ = score_single(db, resume, internship)
            except InsufficientResumeDataError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
            items.append((internship, result.score / 100))
    else:
        source = "match_run"
        run_id = request.run_id
        if run_id is None:
            run_id = db.scalar(
                select(MatchResult.run_id)
                .where(MatchResult.resume_id == resume.resume_id, MatchResult.run_id.is_not(None))
                .order_by(MatchResult.created_at.desc(), MatchResult.match_id.desc())
                .limit(1)
            )
            if run_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No matching run yet. Run matching first or provide internship_ids.",
                )

        rows = db.scalars(
            select(MatchResult)
            .where(MatchResult.run_id == run_id, MatchResult.resume_id == resume.resume_id)
            .order_by(MatchResult.rank)
        ).all()
        if not rows:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match run not found")

        rows = rows[: request.top_k]
        found = load_internships(db, [r.internship_id for r in rows])
        for row in rows:
            internship = found.get(row.internship_id)
            if internship is None or not is_eligible(internship):
                skipped.append(row.internship_id)
                continue
            items.append((internship, row.score / 100))
        if not items:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="None of the internships in this run are still available. Run matching again.",
            )

    try:
        generated = generate_recommendations(db, resume, items, source, run_id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recommendations changed while generating. Please try again.",
        )

    return GenerateResponse(
        resume_id=resume.resume_id,
        algorithm_version=GAP_ALGORITHM_VERSION,
        learning_plan_version=plans_version(),
        source=generated.source,
        run_id=generated.run_id,
        internships=[
            {**internship_ref(i), "relevance": round(relevance, 4)} for i, relevance in generated.internships
        ],
        skipped_internship_ids=skipped,
        newly_acquired_skills=generated.newly_acquired,
        learning_order=generated.learning_order,
        recommendations=[to_item(rec) for rec in generated.recommendations],
    )


# ============================================================
# LIST RECOMMENDATIONS
# GET /skill-gaps
# ============================================================

@router.get("", response_model=list[RecommendationItem])
def list_recommendations(
    resume_id: int | None = None,
    status_filter: GapStatus | None = Query(default=None, alias="status"),
    current_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(SkillGapRecommendation)
        .where(SkillGapRecommendation.user_id == current_user.user_id)
        .options(
            selectinload(SkillGapRecommendation.skill),
            selectinload(SkillGapRecommendation.internship),
        )
        .order_by(
            SkillGapRecommendation.priority_score.desc().nulls_last(),
            SkillGapRecommendation.recommendation_id,
        )
    )
    if resume_id is not None:
        get_owned_resume(db, resume_id, current_user)
        query = query.where(SkillGapRecommendation.resume_id == resume_id)
    if status_filter is not None:
        query = query.where(SkillGapRecommendation.status == status_filter)
    if current_only:
        query = query.where(SkillGapRecommendation.is_current.is_(True))

    return [to_item(rec) for rec in db.scalars(query)]


# ============================================================
# UPDATE PROGRESS
# PATCH /skill-gaps/{recommendation_id}
# ============================================================

@router.patch("/{recommendation_id}", response_model=RecommendationItem)
def update_recommendation(
    recommendation_id: int,
    update: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rec = db.scalar(
        select(SkillGapRecommendation).where(
            SkillGapRecommendation.recommendation_id == recommendation_id,
            SkillGapRecommendation.user_id == current_user.user_id,
        )
    )
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    update_status(rec, update.status)
    db.commit()
    db.refresh(rec)
    return to_item(rec)


# ============================================================
# P3: SKILL PROGRESS AND PER-JOB ROADMAP
# GET  /skill-gaps/progress                       {skill: {status, updated_at}}
# PUT  /skill-gaps/progress   {skill, status}     not_started | learning | practiced | completed
# GET  /skill-gaps/resumes/{rid}/internships/{iid}/roadmap
# ============================================================

from pydantic import BaseModel as _BaseModel, Field as _Field  # noqa: E402

from backend.services import job_insights as _job_insights, skill_progress as _progress  # noqa: E402
from backend.services.skill_gap import assess_internship as _assess, candidate_skill_names as _skills  # noqa: E402


class SkillProgressUpdate(_BaseModel):
    skill: str = _Field(min_length=1, max_length=60)
    status: str = _Field(pattern="^(not_started|learning|practiced|completed)$")


@router.get("/progress")
def get_skill_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"statuses": list(_progress.STATUSES), "labels": _progress.LABELS,
            "skills": _progress.statuses_for(db, current_user.user_id)}


@router.put("/progress")
def set_skill_progress(
    payload: SkillProgressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        skill = _progress.resolve_skill(db, payload.skill)
    except _progress.UnknownSkillError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    progress = _progress.set_status(db, current_user.user_id, skill, payload.status)
    db.commit()
    db.refresh(progress)
    return {"skill": skill.name, "status": progress.status, "status_label": _progress.LABELS[progress.status],
            "updated_at": progress.updated_at}


@router.get("/resumes/{resume_id}/internships/{internship_id}/roadmap")
def get_job_roadmap(
    resume_id: int,
    internship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ordered learning roadmap for one job: missing and partial skills with plans and progress."""
    resume = get_owned_resume(db, resume_id, current_user)
    internship = load_internships(db, [internship_id]).get(internship_id)
    if internship is None or not internship.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")
    candidate = _skills(db, resume.resume_id)
    match = _job_insights.skill_match(_assess(candidate, internship))
    return {"resume_id": resume.resume_id,
            **_progress.roadmap(db, current_user.user_id, candidate, internship, match)}


@router.get("/role-analysis")
def role_analysis(
    role: str | None = Query(default=None, max_length=80, pattern=r"^[a-z0-9-]+$"),
    resume_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Skills grouped by area with evidence, the target role's requirements and prioritised gaps.

    Without ``role`` the answer is a clearly labelled general analysis (no gaps)."""
    from backend.services import skill_analysis

    try:
        return skill_analysis.analyse(db, current_user.user_id, role, resume_id)
    except skill_analysis.AnalysisError as exc:
        code = status.HTTP_409_CONFLICT if exc.code == "resume_required" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})
