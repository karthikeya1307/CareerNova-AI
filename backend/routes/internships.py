
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
from backend.utils.roles import ROLE_ADMIN


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
    include_inactive: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = []

    # Only administrators may see deactivated internships.
    if not (include_inactive and current_user.role == ROLE_ADMIN):
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
    try:
        embedder = embeddings.get_embedder()
        hits = vector_index.search(db, q.strip(), k, embedder)
        manifest = vector_index.read_manifest()
    except (vector_index.IndexNotReadyError, embeddings.EmbeddingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc)
        )

    return {
        "query": q.strip(),
        "index_built_at": manifest["built_at"] if manifest else None,
        "results": [
            {"similarity": hit.similarity, "internship": to_response(hit.internship)}
            for hit in hits
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
        db, internship_id, include_inactive=current_user.role == ROLE_ADMIN
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
):
    fields = data.model_dump(exclude={"required_skills", "preferred_skills"})
    internship = Internship(**fields, source="admin", is_active=True)

    try:
        db.add(internship)
        db.flush()
        set_internship_skills(
            db, internship, skills_payload(data.required_skills, data.preferred_skills)
        )
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
):
    internship = get_internship_or_404(db, internship_id, include_inactive=True)

    internship.is_active = False
    mark_index_pending(db, internship.internship_id)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
