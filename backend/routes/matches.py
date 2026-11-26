
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
from backend.services import job_insights, job_sources
from backend.services.candidate_profile import (
    InsufficientResumeDataError,
    build_candidate,
    latest_completed_extraction,
)
from backend.services.matching_agent import is_eligible, to_posting
from backend.services.resume_readiness import score_resume
from backend.services.resume_skills import get_resume_skill_rows
from backend.services.compatibility import ALGORITHM_VERSION, compute_compatibility
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


class InsightContext:
    """What job insights need about one resume, computed once per request."""

    def __init__(self, db: Session, resume_id: int):
        self.skills = [skill.name for _, skill in get_resume_skill_rows(db, resume_id)]
        extraction = latest_completed_extraction(db, resume_id)
        self.readiness = score_resume(extraction.extracted_data or {})["score"] if extraction else None
        self.evidence = _skill_evidence(db, resume_id)

    def build(self, internship, breakdown: dict) -> dict:
        return job_insights.build(internship, breakdown, self.skills, self.readiness, evidence=self.evidence)


EVIDENCE_KINDS = {"project", "experience", "internship"}


def _skill_evidence(db: Session, resume_id: int) -> dict[str, list[str]]:
    """skill (casefold) -> titles of project / experience / internship entries that mention it."""
    from backend.models import Resume
    from backend.services.ats import skill_locations
    from backend.services.fact_base import NoExtractionError, build_fact_base
    from backend.services.prep.context import short_title

    resume = db.get(Resume, resume_id)
    if resume is None:
        return {}
    try:
        facts = build_fact_base(db, resume)
    except NoExtractionError:
        return {}
    out: dict[str, list[str]] = {}
    for skill, places in skill_locations(facts).items():
        titles = []
        for fact_id in places:
            fact = facts.by_id.get(fact_id)
            if fact is not None and fact.kind in EVIDENCE_KINDS:
                title = short_title(fact.title, 80)
                if title not in titles:
                    titles.append(title)
        if titles:
            out[skill] = titles
    return out


def item_from_result(result, internship, rank, ctx: "InsightContext | None" = None) -> MatchItem:
    breakdown = result.breakdown()
    item = _item(breakdown, result.score, result.label, rank, internship)
    if ctx is not None:
        item.insights = ctx.build(internship, breakdown)
    return item


def item_from_row(row: MatchResult, ctx: "InsightContext | None" = None) -> MatchItem:
    item = _item(row.breakdown or {}, row.score, row.label, row.rank, row.internship)
    if ctx is not None:
        item.insights = ctx.build(row.internship, row.breakdown or {})
    return item


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


def run_response(rows: list[MatchResult], db: Session | None = None) -> MatchRunResponse:
    first = rows[0]
    ctx = InsightContext(db, first.resume_id) if db is not None and first.resume_id else None
    meta = (first.breakdown or {}).get("run", {})
    return MatchRunResponse(
        run_id=first.run_id,
        resume_id=first.resume_id,
        algorithm_version=first.algorithm_version or ALGORITHM_VERSION,
        created_at=first.created_at,
        semantic_available=meta.get("semantic_available", False),
        candidates_considered=meta.get("candidates_considered", len(rows)),
        filters=meta.get("filters", {}),
        results=[item_from_row(row, ctx) for row in rows],
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

    ctx = InsightContext(db, resume.resume_id)
    return MatchRunResponse(
        run_id=run.run_id,
        resume_id=resume.resume_id,
        algorithm_version=ALGORITHM_VERSION,
        created_at=run.created_at,
        semantic_available=run.semantic_available,
        candidates_considered=run.candidates_considered,
        filters=run.filters,
        results=[
            item_from_result(result, internship, rank, ctx)
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

    return run_response(load_run_rows(db, latest_run_id), db)


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

    return run_response(rows, db)


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

    return item_from_result(result, internship, None, InsightContext(db, resume.resume_id))


# ============================================================
# EXPLORE ANY JOB (P2)
# GET /matches/explore?resume_id=&q=&domain=&location=&work_mode=&skip=&limit=
# Browse every open opportunity, not limited to the resume's best matches. With a resume, each job
# also gets insights (skill match, eligibility, readiness, category). Nothing is saved.
# ============================================================

EXPLORE_SEMANTIC_NOTE = "Semantic similarity is not computed while exploring; the score uses skills, education and location."


@router.get("/explore")
def explore_jobs(
    resume_id: int | None = Query(default=None, ge=1),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    domain: str | None = Query(default=None, max_length=80),
    location: str | None = Query(default=None, max_length=150),
    work_mode: WorkMode | None = None,
    category: Literal["apply_now", "improve", "long_term"] | None = None,
    source: Literal["dataset", "admin", "manual"] | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import or_

    resume = get_owned_resume(db, resume_id, current_user) if resume_id else None
    conditions = [Internship.is_active.is_(True)]
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(or_(Internship.title.ilike(pattern), Internship.company.ilike(pattern),
                              Internship.description.ilike(pattern), Internship.domain.ilike(pattern)))
    if domain:
        conditions.append(Internship.domain == domain)
    if work_mode:
        conditions.append(Internship.work_mode == work_mode)
    if location and location.strip():
        conditions.append(Internship.location.ilike(f"%{location.strip()}%"))
    if source:
        conditions.append(Internship.source == source)

    rows = [i for i in db.scalars(
        select(Internship).where(*conditions)
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
        .order_by(Internship.internship_id)
    ) if is_eligible(i)]                               # deadline not passed
    rows, duplicates_hidden = job_sources.unique_listings(rows)

    candidate = ctx = None
    if resume is not None:
        try:
            candidate = build_candidate(db, resume).candidate
        except InsufficientResumeDataError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
        ctx = InsightContext(db, resume.resume_id)

    items = []
    for internship in rows:
        entry = {"internship": to_response(internship), "score": None, "label": None, "insights": None}
        if candidate is not None:
            result = compute_compatibility(candidate, to_posting(internship), None, EXPLORE_SEMANTIC_NOTE)
            entry["score"], entry["label"] = result.score, result.label
            entry["insights"] = ctx.build(internship, result.breakdown())
        items.append(entry)
    if category and ctx is not None:
        items = [e for e in items if e["insights"]["category"] == category]

    return {
        "mode": "explore",
        "resume_id": resume.resume_id if resume else None,
        "total": len(items),
        "duplicates_hidden": duplicates_hidden,
        "skip": skip,
        "limit": limit,
        "category_counts": ({c: sum(1 for e in items if e["insights"]["category"] == c)
                             for c in ("apply_now", "improve", "long_term")} if ctx is not None else None),
        "items": items[skip:skip + limit],
    }
