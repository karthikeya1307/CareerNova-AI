
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import Internship, InternshipSkill, MatchResult, Resume, User
from backend.routes.internships import get_internship_or_404, to_response
from backend.schemas.match_schema import MatchItem, MatchRunResponse, MatchRunSummary
from backend.services.candidate_profile import InsufficientResumeDataError
from backend.services.compatibility import ALGORITHM_VERSION
from backend.services.matching_agent import (
    InternshipNotEligibleError,
    run_matching,
    score_single,
)
from backend.utils.dependencies import get_current_user


router = APIRouter(
    prefix="/matches",
    tags=["Internship Matching"]
)

WorkMode = Literal["Onsite", "Hybrid", "Remote"]


# ============================================================
# HELPERS
# ============================================================

def get_owned_resume(db: Session, resume_id: int, user: User) -> Resume:
    resume = db.scalar(
        select(Resume).where(
            Resume.resume_id == resume_id,
            Resume.user_id == user.user_id,
        )
    )
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found"
        )
    return resume


def item_from_result(result, internship, rank) -> MatchItem:
    breakdown = result.breakdown()
    return _item(breakdown, result.score, result.label, rank, internship)


def item_from_row(row: MatchResult) -> MatchItem:
    return _item(row.breakdown or {}, row.score, row.label, row.rank, row.internship)


def _item(breakdown: dict, score, label, rank, internship) -> MatchItem:
    return MatchItem(
        rank=rank,
        score=score,
        label=label,
        algorithm_version=breakdown.get("algorithm_version", ALGORITHM_VERSION),
        data_completeness=breakdown.get("data_completeness", 0.0),
        score_before_caps=breakdown.get("score_before_caps", score),
        required_skill_coverage=breakdown.get("required_skill_coverage"),
        components=breakdown.get("components", []),
        matched_required_skills=breakdown.get("matched_required_skills", []),
        missing_required_skills=breakdown.get("missing_required_skills", []),
        matched_preferred_skills=breakdown.get("matched_preferred_skills", []),
        missing_preferred_skills=breakdown.get("missing_preferred_skills", []),
        missing_information=breakdown.get("missing_information", []),
        caps_applied=breakdown.get("caps_applied", []),
        explanation=breakdown.get("explanation", []),
        internship=to_response(internship),
    )


def load_run_rows(db: Session, run_id: UUID) -> list[MatchResult]:
    return list(db.scalars(
        select(MatchResult)
        .where(MatchResult.run_id == run_id)
        .options(
            selectinload(MatchResult.internship)
            .selectinload(Internship.skill_links)
            .selectinload(InternshipSkill.skill)
        )
        .order_by(MatchResult.rank)
    ))


def run_response(rows: list[MatchResult]) -> MatchRunResponse:
    first = rows[0]
    meta = (first.breakdown or {}).get("run", {})
    return MatchRunResponse(
        run_id=first.run_id,
        resume_id=first.resume_id,
        algorithm_version=first.algorithm_version or ALGORITHM_VERSION,
        created_at=first.created_at,
        semantic_available=meta.get("semantic_available", False),
        candidates_considered=meta.get("candidates_considered", len(rows)),
        filters=meta.get("filters", {}),
        results=[item_from_row(row) for row in rows],
    )


# ============================================================
# RUN MATCHING
# POST /matches/resumes/{resume_id}
# ============================================================

@router.post(
    "/resumes/{resume_id}",
    response_model=MatchRunResponse,
    status_code=status.HTTP_201_CREATED
)
def create_match_run(
    resume_id: int,
    k: int = Query(default=10, ge=1, le=50),
    work_mode: WorkMode | None = None,
    location: str | None = Query(default=None, min_length=2, max_length=150),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)

    try:
        run = run_matching(db, resume, k=k, work_mode=work_mode, location=location)
    except InsufficientResumeDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc)
        )
    except IntegrityError:
        # e.g. the resume was deleted while matching was running.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The resume changed while matching was running. Please try again."
        )

    return MatchRunResponse(
        run_id=run.run_id,
        resume_id=resume.resume_id,
        algorithm_version=ALGORITHM_VERSION,
        created_at=run.created_at,
        semantic_available=run.semantic_available,
        candidates_considered=run.candidates_considered,
        filters=run.filters,
        results=[
            item_from_result(result, internship, rank)
            for rank, (result, internship) in enumerate(run.results, start=1)
        ],
    )


# ============================================================
# LATEST RUN
# GET /matches/resumes/{resume_id}
# ============================================================

@router.get("/resumes/{resume_id}", response_model=MatchRunResponse)
def get_latest_match_run(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)

    latest_run_id = db.scalar(
        select(MatchResult.run_id)
        .where(MatchResult.resume_id == resume.resume_id, MatchResult.run_id.is_not(None))
        .order_by(MatchResult.created_at.desc(), MatchResult.match_id.desc())
        .limit(1)
    )
    if latest_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching results yet for this resume"
        )

    return run_response(load_run_rows(db, latest_run_id))


# ============================================================
# RUN HISTORY
# GET /matches/resumes/{resume_id}/history
# ============================================================

@router.get("/resumes/{resume_id}/history", response_model=list[MatchRunSummary])
def get_match_history(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)

    rows = db.execute(
        select(
            MatchResult.run_id,
            func.min(MatchResult.created_at),
            func.max(MatchResult.algorithm_version),
            func.count(),
            func.max(MatchResult.score),
        )
        .where(MatchResult.resume_id == resume.resume_id, MatchResult.run_id.is_not(None))
        .group_by(MatchResult.run_id)
        .order_by(func.min(MatchResult.created_at).desc())
    ).all()

    top_labels = dict(db.execute(
        select(MatchResult.run_id, MatchResult.label)
        .where(MatchResult.resume_id == resume.resume_id, MatchResult.rank == 1)
    ).tuples().all())

    return [
        MatchRunSummary(
            run_id=run_id, created_at=created_at, algorithm_version=version,
            result_count=count, top_score=top_score, top_label=top_labels.get(run_id),
        )
        for run_id, created_at, version, count, top_score in rows
    ]


# ============================================================
# ONE RUN
# GET /matches/runs/{run_id}
# ============================================================

@router.get("/runs/{run_id}", response_model=MatchRunResponse)
def get_match_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = load_run_rows(db, run_id)

    if not rows or rows[0].user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match run not found"
        )

    return run_response(rows)


# ============================================================
# SCORE ONE INTERNSHIP (not saved)
# GET /matches/resumes/{resume_id}/internships/{internship_id}
# ============================================================

@router.get(
    "/resumes/{resume_id}/internships/{internship_id}",
    response_model=MatchItem
)
def score_one_internship(
    resume_id: int,
    internship_id: int,
    location: str | None = Query(default=None, min_length=2, max_length=150),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)
    internship = get_internship_or_404(db, internship_id, include_inactive=False)

    try:
        result, _ = score_single(db, resume, internship, location=location)
    except InternshipNotEligibleError:
        # Past-deadline internships are treated like missing ones.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship not found"
        )
    except InsufficientResumeDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc)
        )

    return item_from_result(result, internship, None)
