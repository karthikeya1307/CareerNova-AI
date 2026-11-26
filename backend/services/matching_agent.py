"""Resume -> internship matching agent.

Pipeline:
    1. Build the candidate (skills, degree, location, query text).
    2. Retrieve candidates: vector-index nearest neighbours UNION every active
       internship sharing at least one skill with the resume.
    3. Re-check each candidate in PostgreSQL (active, deadline not passed,
       optional work-mode filter).
    4. Score each with compatibility.compute_compatibility. The semantic
       similarity of candidates outside the index top-N is computed from
       the stored vector (NumpyIndex.reconstruct), so every candidate is
       scored the same way.
    5. Rank deterministically and persist the top k as one run.

If the index or embedding model is unavailable, matching still works:
the semantic component is marked "unavailable" (conservative score).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    Internship,
    InternshipSkill,
    KnowledgeDocument,
    MatchResult,
    Resume,
    Skill,
)
from backend.services import embeddings, vector_index
from backend.services.candidate_profile import CandidateContext, build_candidate
from backend.services.compatibility import (
    ALGORITHM_VERSION,
    SEMANTIC_NOT_INDEXED_DETAIL,
    CompatibilityResult,
    Posting,
    compute_compatibility,
    rank_results,
)
from backend.services.internship_text import internship_skill_names

logger = logging.getLogger(__name__)

MIN_SEMANTIC_POOL = 50
SEMANTIC_POOL_MULTIPLIER = 5


class InternshipNotEligibleError(ValueError):
    """Internship is inactive or past its deadline."""


@dataclass
class SemanticContext:
    available: bool
    index: object | None = None
    query_vector: np.ndarray | None = None
    top: dict[int, float] = field(default_factory=dict)        # document_id -> cosine
    doc_by_internship: dict[int, int] = field(default_factory=dict)

    def cosine_for(self, internship_id: int) -> tuple[float | None, str | None]:
        """Return (cosine, detail-if-unavailable) for one internship."""
        if not self.available:
            return None, None  # default "index or model not ready" detail
        doc_id = self.doc_by_internship.get(internship_id)
        if doc_id is None:
            return None, SEMANTIC_NOT_INDEXED_DETAIL
        if doc_id in self.top:
            return self.top[doc_id], None
        try:
            vector = self.index.reconstruct(int(doc_id))
        except Exception:
            return None, SEMANTIC_NOT_INDEXED_DETAIL
        return float(np.dot(self.query_vector[0], vector)), None


@dataclass
class MatchRun:
    run_id: uuid.UUID
    created_at: datetime
    semantic_available: bool
    candidates_considered: int
    filters: dict
    results: list[tuple[CompatibilityResult, Internship]]


# ============================================================
# HELPERS
# ============================================================

def to_posting(internship: Internship) -> Posting:
    required, preferred = internship_skill_names(internship)
    return Posting(
        internship_id=internship.internship_id,
        required_skills=tuple(required),
        preferred_skills=tuple(preferred),
        min_education=internship.min_education,
        work_mode=internship.work_mode,
        location=internship.location,
    )


def _eligible_filter(now: datetime):
    return (
        Internship.is_active.is_(True),
        or_(Internship.deadline.is_(None), Internship.deadline >= now),
    )


def is_eligible(internship: Internship, now: datetime | None = None) -> bool:
    """Same rule as the SQL filter: active and deadline not passed."""
    now = now or datetime.now(timezone.utc)
    if not internship.is_active:
        return False
    deadline = internship.deadline
    if deadline is None:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline >= now


def build_semantic_context(db: Session, query_text: str, pool: int) -> SemanticContext:
    """Semantic search context; degrades to 'unavailable' on any failure."""
    try:
        embedder = embeddings.get_embedder()
        loaded = vector_index.load_index()
        vector_index.ensure_compatible(loaded.manifest, embedder)

        index = loaded.index
        query_vector = np.ascontiguousarray(embedder.embed([query_text]), dtype="float32")

        top: dict[int, float] = {}
        if index.ntotal:
            scores, ids = index.search(query_vector, min(pool, index.ntotal))
            top = {int(i): float(s) for i, s in zip(ids[0], scores[0]) if i != -1}

    except (vector_index.IndexNotReadyError, embeddings.EmbeddingError):
        return SemanticContext(available=False)
    except Exception:
        # Matching must still work on skills, education and location.
        logger.exception("Semantic scoring failed; continuing without it")
        return SemanticContext(available=False)

    doc_by_internship = dict(db.execute(
        select(KnowledgeDocument.internship_id, KnowledgeDocument.document_id)
        .where(
            KnowledgeDocument.source_type == vector_index.SOURCE_TYPE,
            KnowledgeDocument.indexing_status == "indexed",
            KnowledgeDocument.internship_id.is_not(None),
        )
    ).tuples().all())

    return SemanticContext(True, index, query_vector, top, doc_by_internship)


def find_candidates(
    db: Session,
    context: CandidateContext,
    semantic: SemanticContext,
    work_mode: str | None,
    now: datetime,
) -> list[Internship]:
    internship_by_doc = {doc: iid for iid, doc in semantic.doc_by_internship.items()}
    ids = {internship_by_doc[d] for d in semantic.top if d in internship_by_doc}

    skill_keys = [s.casefold() for s in context.candidate.skills]
    ids |= set(db.scalars(
        select(InternshipSkill.internship_id)
        .join(Skill, Skill.skill_id == InternshipSkill.skill_id)
        .where(func.lower(Skill.name).in_(skill_keys))
    ))

    if not ids:
        return []

    query = (
        select(Internship)
        .where(Internship.internship_id.in_(ids), *_eligible_filter(now))
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
    )
    if work_mode:
        query = query.where(func.lower(Internship.work_mode) == work_mode.casefold())

    return list(db.scalars(query))


# ============================================================
# PUBLIC API
# ============================================================

def run_matching(
    db: Session,
    resume: Resume,
    k: int = 10,
    work_mode: str | None = None,
    location: str | None = None,
) -> MatchRun:
    """Score, rank and persist the top-k internships for a resume."""

    now = datetime.now(timezone.utc)
    context = build_candidate(db, resume, location_override=location)
    semantic = build_semantic_context(
        db, context.query_text, max(MIN_SEMANTIC_POOL, k * SEMANTIC_POOL_MULTIPLIER)
    )
    internships = find_candidates(db, context, semantic, work_mode, now)
    by_id = {i.internship_id: i for i in internships}

    scored = [
        compute_compatibility(
            context.candidate, to_posting(i), *semantic.cosine_for(i.internship_id)
        )
        for i in internships
    ]
    ranked = rank_results(scored)[:k]

    run_id = uuid.uuid4()
    filters = {"k": k, "work_mode": work_mode, "location_override": bool(location)}
    run_meta = {
        "semantic_available": semantic.available,
        "candidates_considered": len(internships),
        "filters": filters,
    }

    for rank, result in enumerate(ranked, start=1):
        components = {c.name: c for c in result.components}
        db.add(MatchResult(
            user_id=resume.user_id,
            resume_id=resume.resume_id,
            internship_id=result.internship_id,
            score=result.score,
            explanation=" ".join(result.explanation)[:4000],
            run_id=run_id,
            rank=rank,
            label=result.label,
            algorithm_version=ALGORITHM_VERSION,
            skill_score=components["skills"].score,
            semantic_score=(
                components["semantic"].score
                if components["semantic"].status == "assessed" else None
            ),
            education_score=components["education"].score,
            location_score=components["location"].score,
            required_skill_coverage=result.required_coverage,
            data_completeness=result.data_completeness,
            breakdown={**result.breakdown(), "run": run_meta},
        ))
    db.commit()

    return MatchRun(
        run_id=run_id,
        created_at=now,
        semantic_available=semantic.available,
        candidates_considered=len(internships),
        filters=filters,
        results=[(r, by_id[r.internship_id]) for r in ranked],
    )


def score_single(
    db: Session, resume: Resume, internship: Internship, location: str | None = None
) -> tuple[CompatibilityResult, bool]:
    """Score one internship on demand (not persisted)."""

    if not is_eligible(internship):
        raise InternshipNotEligibleError("Internship is inactive or past its deadline")

    context = build_candidate(db, resume, location_override=location)
    semantic = build_semantic_context(db, context.query_text, 1)
    result = compute_compatibility(
        context.candidate, to_posting(internship), *semantic.cosine_for(internship.internship_id)
    )
    return result, semantic.available
