
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import Internship, InternshipSkill, Skill, User
from backend.schemas.internship_schema import (
    InternshipCreate,
    InternshipFiltersResponse,
    InternshipListResponse,
    InternshipResponse,
    InternshipSearchResponse,
    InternshipSkillItem,
    InternshipUpdate,
)
from backend.services import embeddings, vector_index
from backend.services.internship_seed import mark_index_pending, set_internship_skills
from backend.services.internship_text import internship_skill_names
from backend.utils.dependencies import get_current_user, require_admin
from backend.services import audit, job_sources
from backend.utils.roles import is_admin_role


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internships",
    tags=["Internships"]
)


# ============================================================
# HELPERS
# ============================================================

def to_response(internship: Internship) -> InternshipResponse:
    required, preferred = internship_skill_names(internship)

    response = InternshipResponse.model_validate(internship)
    response.required_skills = required
    response.preferred_skills = preferred
    response.source_label = job_sources.source_label(internship)
    response.freshness = job_sources.freshness(internship)
    response.skills = [
        InternshipSkillItem(
            skill_id=link.skill.skill_id,
            name=link.skill.name,
            category=link.skill.category,
            importance=link.importance,
        )
        for link in sorted(
            internship.skill_links,
            key=lambda l: (l.importance != "required", l.skill.name.casefold()),
        )
    ]
    return response


def with_skills(query):
    return query.options(
        selectinload(Internship.skill_links).selectinload(InternshipSkill.skill)
    )


def get_internship_or_404(
    db: Session, internship_id: int, include_inactive: bool
) -> Internship:
    internship = db.scalar(
        with_skills(select(Internship)).where(
            Internship.internship_id == internship_id
        )
    )
    if internship is None or (not internship.is_active and not include_inactive):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship not found"
        )
    return internship


def skills_payload(required: list[str], preferred: list[str]) -> dict[str, str]:
    skills = {name: "required" for name in required}
    for name in preferred:
        skills.setdefault(name, "preferred")
    return skills


# ============================================================
# LIST / FILTER
# GET /internships/
# ============================================================

@router.get("/", response_model=InternshipListResponse)
def list_internships(
    q: str | None = Query(default=None, max_length=100),
    domain: str | None = Query(default=None, max_length=80),
    work_mode: str | None = Query(default=None, max_length=20),
    location: str | None = Query(default=None, max_length=150),
    skill: str | None = Query(default=None, max_length=60),
    source: str | None = Query(default=None, max_length=30),
    include_inactive: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = []

    # Only administrators may see deactivated internships.
    if not (include_inactive and is_admin_role(current_user.role)):
        filters.append(Internship.is_active.is_(True))

    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(
            Internship.title.ilike(pattern),
            Internship.company.ilike(pattern),
            Internship.description.ilike(pattern),
        ))
    if domain:
        filters.append(func.lower(Internship.domain) == domain.strip().lower())
    if work_mode:
        filters.append(func.lower(Internship.work_mode) == work_mode.strip().lower())
    if location:
        filters.append(Internship.location.ilike(f"%{location.strip()}%"))
    if source:
        if source not in job_sources.SOURCES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"source must be one of: {', '.join(job_sources.SOURCES)}")
        filters.append(Internship.source == source)
    if skill:
        filters.append(Internship.skill_links.any(
            InternshipSkill.skill.has(func.lower(Skill.name) == skill.strip().lower())
        ))

    total = db.scalar(select(func.count()).select_from(Internship).where(*filters))
    items = db.scalars(
        with_skills(select(Internship))
        .where(*filters)
        .order_by(Internship.internship_id)
        .offset(skip)
        .limit(limit)
    ).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [to_response(i) for i in items],
    }


# ============================================================
# FILTER OPTIONS
# GET /internships/filters
# ============================================================

@router.get("/filters", response_model=InternshipFiltersResponse)
def internship_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    def distinct(column):
        return [
            value for value in db.scalars(
                select(column).where(
                    Internship.is_active.is_(True), column.is_not(None)
                ).distinct().order_by(column)
            )
        ]

    return {
        "domains": distinct(Internship.domain),
        "work_modes": distinct(Internship.work_mode),
        "locations": distinct(Internship.location),
    }


# ============================================================
# SEMANTIC SEARCH
# GET /internships/search?q=...
# ============================================================

@router.get("/search", response_model=InternshipSearchResponse)
def search_internships(
    q: str = Query(min_length=2, max_length=500),
    k: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Natural-language search (role, skills, location, work mode) over the internship catalogue.

    Semantic similarity (embeddings) plus exact skill/role/location matching; if the model or the index is
    unavailable the same rules run on keywords only ("mode": "keyword") instead of failing."""
    from backend.services import job_search

    embedder, manifest = None, None
    try:
        embedder = embeddings.get_embedder()
        manifest = vector_index.read_manifest()
    except (vector_index.IndexNotReadyError, embeddings.EmbeddingError) as exc:
        # The specific reason (model files, admin commands) is for operators - log it, don't show it to students.
        logger.warning("Semantic internship search unavailable, using keywords: %s", exc)
    interpretation, results, mode, message = job_search.search(db, q.strip(), k, embedder)
    if mode == "keyword" and embedder is not None:
        logger.warning("Semantic index unavailable for search; keyword matching used")
    if mode == "keyword":
        notice = "Matching by keywords only right now (the meaning-based index is unavailable)."
        message = f"{message} {notice}" if message else notice

    return {
        "query": q.strip(),
        "index_built_at": manifest["built_at"] if manifest and mode == "hybrid" else None,
        "mode": mode,
        "interpretation": interpretation.as_dict(),
        "message": message,
        "results": [
            {"similarity": r.similarity if r.similarity is not None else 0.0, "score": r.score, "reasons": r.reasons,
             "internship": to_response(r.internship)}
            for r in results
        ],
    }


# ============================================================
# DETAIL
# GET /internships/{internship_id}
# ============================================================

@router.get("/{internship_id}", response_model=InternshipResponse)
def get_internship(
    internship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    internship = get_internship_or_404(
        db, internship_id, include_inactive=is_admin_role(current_user.role)
    )
    return to_response(internship)


# ============================================================
# ADMIN: CREATE
# POST /internships/
# ============================================================

@router.post(
    "/",
    response_model=InternshipResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_internship(
    data: InternshipCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    fields = data.model_dump(exclude={"required_skills", "preferred_skills"})
    key = job_sources.dedup_key(fields.get("title"), fields.get("company"), fields.get("location"))
    duplicate = job_sources.find_duplicate(db, key)
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "duplicate", "existing_internship_id": duplicate,
            "message": f"An active listing with the same title, company and location already exists (#{duplicate})."})
    internship = Internship(**fields, source="admin", is_active=True, dedup_key=key)

    try:
        db.add(internship)
        db.flush()
        set_internship_skills(
            db, internship, skills_payload(data.required_skills, data.preferred_skills)
        )
        audit.record(db, "internship.create", actor=current_admin,
                     target_label=f"Internship {internship.internship_id}: {internship.title} at {internship.company}",
                     details={"internship_id": internship.internship_id})
        db.commit()
    except Exception:
        db.rollback()
        raise

    return to_response(get_internship_or_404(db, internship.internship_id, True))


# ============================================================
# ADMIN: UPDATE
# PATCH /internships/{internship_id}
# ============================================================

@router.patch(
    "/{internship_id}",
    response_model=InternshipResponse,
    dependencies=[Depends(require_admin)],
)
def update_internship(
    internship_id: int,
    data: InternshipUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    internship = get_internship_or_404(db, internship_id, include_inactive=True)
    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update"
        )

    for key in ("title", "company", "stipend_currency", "is_active"):
        if key in changes and changes[key] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{key} cannot be null"
            )

    required = changes.pop("required_skills", None)
    preferred = changes.pop("preferred_skills", None)

    if {"title", "company", "location"} & changes.keys():
        new_key = job_sources.dedup_key(changes.get("title", internship.title), changes.get("company", internship.company),
                                        changes.get("location", internship.location))
        duplicate = job_sources.find_duplicate(db, new_key, exclude_id=internship.internship_id)
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
                "code": "duplicate", "existing_internship_id": duplicate,
                "message": f"An active listing with the same title, company and location already exists (#{duplicate})."})
        changes["dedup_key"] = new_key

    try:
        for key, value in changes.items():
            setattr(internship, key, value)

        if required is not None or preferred is not None:
            current_required, current_preferred = internship_skill_names(internship)
            set_internship_skills(db, internship, skills_payload(
                required if required is not None else current_required,
                preferred if preferred is not None else current_preferred,
            ))

        mark_index_pending(db, internship.internship_id)
        audit.record(db, "internship.update", actor=current_admin,
                     target_label=f"Internship {internship.internship_id}: {internship.title} at {internship.company}",
                     details={"internship_id": internship.internship_id,
                              "fields": sorted([*(k for k in changes if k != "dedup_key"),
                                                *(["required_skills"] if required is not None else []),
                                                *(["preferred_skills"] if preferred is not None else [])])})
        db.commit()
    except Exception:
        db.rollback()
        raise

    return to_response(get_internship_or_404(db, internship_id, True))


# ============================================================
# ADMIN: DEACTIVATE (soft delete)
# DELETE /internships/{internship_id}
# ============================================================

@router.delete(
    "/{internship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_admin)],
)
def deactivate_internship(
    internship_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    internship = get_internship_or_404(db, internship_id, include_inactive=True)

    internship.is_active = False
    mark_index_pending(db, internship.internship_id)
    audit.record(db, "internship.deactivate", actor=current_admin,
                 target_label=f"Internship {internship.internship_id}: {internship.title} at {internship.company}",
                 details={"internship_id": internship.internship_id})
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================
# ADMIN: MARK AS VERIFIED (job-source tracking)
# POST /internships/{internship_id}/verify
# ============================================================

@router.post("/{internship_id}/verify", response_model=InternshipResponse)
def verify_internship(
    internship_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """Record that an administrator checked the listing is still open at its source today."""
    from datetime import datetime, timezone

    internship = get_internship_or_404(db, internship_id, include_inactive=True)
    internship.last_verified_at = datetime.now(timezone.utc)
    audit.record(db, "internship.verify", actor=current_admin,
                 target_label=f"Internship {internship.internship_id}: {internship.title} at {internship.company}",
                 details={"internship_id": internship.internship_id})
    db.commit()
    return to_response(get_internship_or_404(db, internship_id, True))
