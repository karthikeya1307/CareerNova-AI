"""Skill-gap analysis and learning recommendations (Phase 4, algorithm gap-v1).

Per internship, every required and preferred skill is classified as:
    matched  - the candidate has it
    partial  - missing, but the candidate has a closely related skill
               (curated list in skill_relations.py)
    missing  - neither

Across several internships (the latest match run, or internships the
student selects) each gap skill gets a priority 0-100:

    priority = 100 x sum_i(importance_i x relevance_i x partial_i) / sum_i(relevance_i)

    importance: required 1.0, preferred 0.5 (0 if not needed by i)
    relevance:  the internship's Phase 3 compatibility score / 100
                (read-only input; Phase 3 scoring is not changed)
    partial:    0.5 if the candidate has a related skill, else 1.0

So a required, fully missing skill needed by every analysed internship
scores 100. Ties are broken by required count, demand, then name.

All facts come from PostgreSQL records and the curated, link-free
learning plans; nothing is generated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Internship, Resume, SkillGapRecommendation
from backend.services.internship_text import internship_skill_names
from backend.services.learning_plans import (
    learning_order,
    missing_prerequisites,
    plan_for,
    plans_version,
)
from backend.services.resume_skills import get_resume_skill_rows
from backend.services.skill_relations import find_related_in

GAP_ALGORITHM_VERSION = "gap-v1"
IMPORTANCE_WEIGHT = {"required": 1.0, "preferred": 0.5}
PARTIAL_FACTOR = 0.5
MIN_RELEVANCE = 0.05

STATUSES = ("pending", "in_progress", "completed", "dismissed")


# ============================================================
# SINGLE INTERNSHIP ANALYSIS
# ============================================================

@dataclass
class SkillAssessment:
    skill: str
    category: str | None
    importance: str
    status: str                       # matched | partial | missing
    related: list[dict[str, str]] = field(default_factory=list)


def candidate_skill_names(db: Session, resume_id: int) -> list[str]:
    return [skill.name for _, skill in get_resume_skill_rows(db, resume_id)]


def assess_internship(candidate_skills: list[str], internship: Internship) -> list[SkillAssessment]:
    have = {s.casefold() for s in candidate_skills}
    categories = {l.skill.name: l.skill.category for l in internship.skill_links}
    required, preferred = internship_skill_names(internship)
    result = []

    for importance, skills in (("required", required), ("preferred", preferred)):
        for skill in skills:
            if skill.casefold() in have:
                result.append(SkillAssessment(skill, categories.get(skill), importance, "matched"))
                continue
            related = [
                {"skill": name, "reason": reason}
                for name, reason in find_related_in(skill, candidate_skills)
            ]
            status = "partial" if related else "missing"
            result.append(SkillAssessment(skill, categories.get(skill), importance, status, related))
    return result


def gap_plan(skill: str, candidate_skills: list[str]) -> dict[str, Any]:
    plan = plan_for(skill)
    plan["missing_prerequisites"] = missing_prerequisites(skill, set(candidate_skills))
    return plan


def analyse_internship(candidate_skills: list[str], internship: Internship) -> dict[str, Any]:
    """Read-only gap report for one internship."""

    assessments = assess_internship(candidate_skills, internship)
    by_status = {s: [a for a in assessments if a.status == s] for s in ("matched", "partial", "missing")}

    def item(a: SkillAssessment) -> dict[str, Any]:
        return {
            "skill": a.skill,
            "category": a.category,
            "importance": a.importance,
            "status": a.status,
            "related_skills": a.related,
        }

    gaps = sorted(
        by_status["missing"] + by_status["partial"],
        key=lambda a: (a.importance != "required", a.status != "missing", a.skill.casefold()),
    )
    required = [a for a in assessments if a.importance == "required"]
    preferred = [a for a in assessments if a.importance == "preferred"]

    return {
        "algorithm_version": GAP_ALGORITHM_VERSION,
        "learning_plan_version": plans_version(),
        "summary": {
            "required_total": len(required),
            "required_matched": sum(a.status == "matched" for a in required),
            "required_partial": sum(a.status == "partial" for a in required),
            "required_missing": sum(a.status == "missing" for a in required),
            "preferred_total": len(preferred),
            "preferred_matched": sum(a.status == "matched" for a in preferred),
            "preferred_partial": sum(a.status == "partial" for a in preferred),
            "preferred_missing": sum(a.status == "missing" for a in preferred),
        },
        "matched": [item(a) for a in by_status["matched"]],
        "partial": [item(a) for a in by_status["partial"]],
        "missing": [item(a) for a in by_status["missing"]],
        "learning_order": learning_order([a.skill for a in gaps], known=set(candidate_skills)),
        "learning_plans": [
            {**item(a), "plan": gap_plan(a.skill, candidate_skills)} for a in gaps
        ],
    }


# ============================================================
# AGGREGATION AND PRIORITY
# ============================================================

@dataclass
class GapItem:
    skill: str
    skill_id: int
    category: str | None
    gap_level: str                     # missing | partial
    importance: str                    # strongest importance seen
    weight: float = 0.0
    demand: int = 0
    required_count: int = 0
    internships: list[Internship] = field(default_factory=list)
    related: list[dict[str, str]] = field(default_factory=list)
    priority: float = 0.0


def aggregate_gaps(
    candidate_skills: list[str],
    items: list[tuple[Internship, float]],
) -> tuple[list[GapItem], float]:
    """Combine gaps over (internship, relevance) pairs; return ranked items."""

    gaps: dict[str, GapItem] = {}
    total_relevance = 0.0

    for internship, relevance in items:
        relevance = max(MIN_RELEVANCE, min(1.0, relevance))
        total_relevance += relevance
        skill_ids = {l.skill.name: l.skill.skill_id for l in internship.skill_links}

        for a in assess_internship(candidate_skills, internship):
            if a.status == "matched":
                continue
            gap = gaps.get(a.skill)
            if gap is None:
                gap = gaps[a.skill] = GapItem(
                    skill=a.skill, skill_id=skill_ids[a.skill], category=a.category,
                    gap_level=a.status, importance=a.importance, related=a.related,
                )
            factor = PARTIAL_FACTOR if a.status == "partial" else 1.0
            gap.weight += IMPORTANCE_WEIGHT[a.importance] * relevance * factor
            gap.demand += 1
            gap.required_count += a.importance == "required"
            if a.importance == "required":
                gap.importance = "required"
            gap.internships.append(internship)

    for gap in gaps.values():
        gap.priority = round(min(100.0, 100.0 * gap.weight / total_relevance), 1) if total_relevance else 0.0

    ranked = sorted(
        gaps.values(),
        key=lambda g: (-g.priority, -g.required_count, -g.demand, g.skill.casefold()),
    )
    return ranked, total_relevance


def recommended_action(gap: GapItem, total_internships: int, missing_prereqs: list[str]) -> str:
    verb = "Strengthen" if gap.gap_level == "partial" else "Learn"
    preferred_count = gap.demand - gap.required_count
    parts = []
    if gap.required_count:
        parts.append(f"required by {gap.required_count}")
    if preferred_count:
        parts.append(f"preferred by {preferred_count}")
    example = gap.internships[0]
    text = (
        f"{verb} {gap.skill}: {' and '.join(parts)} of the {total_internships} "
        f"internship{'s' if total_internships != 1 else ''} analysed "
        f"(for example {example.title} at {example.company})."
    )
    if gap.related:
        related = ", ".join(r["skill"] for r in gap.related)
        text += f" You already know {related}, which partly covers it ({gap.related[0]['reason']})."
    if missing_prereqs:
        text += f" Start with: {', '.join(missing_prereqs)}."
    return text


# ============================================================
# PERSISTENCE AND PROGRESS
# ============================================================

def detect_acquired_skills(db: Session, resume_id: int) -> list[str]:
    """Complete open recommendations whose skill is now on the resume.

    Caller commits. Returns the newly acquired skill names.
    """
    have = {s.casefold() for s in candidate_skill_names(db, resume_id)}
    now = datetime.now(timezone.utc)
    acquired = []
    for rec in db.scalars(
        select(SkillGapRecommendation).where(
            SkillGapRecommendation.resume_id == resume_id,
            SkillGapRecommendation.status.in_(("pending", "in_progress")),
        )
    ):
        if rec.skill.name.casefold() in have:
            rec.status = "completed"
            rec.completed_via = "resume"
            rec.completed_at = now
            acquired.append(rec.skill.name)
    return sorted(acquired)


@dataclass
class GenerationResult:
    recommendations: list[SkillGapRecommendation]
    learning_order: list[str]
    internships: list[tuple[Internship, float]]
    newly_acquired: list[str]
    source: str
    run_id: uuid.UUID | None


def generate_recommendations(
    db: Session,
    resume: Resume,
    items: list[tuple[Internship, float]],
    source: str,
    run_id: uuid.UUID | None = None,
) -> GenerationResult:
    """Upsert recommendations for one resume; preserves progress status."""

    newly_acquired = detect_acquired_skills(db, resume.resume_id)
    candidate_skills = candidate_skill_names(db, resume.resume_id)
    gaps, _ = aggregate_gaps(candidate_skills, items)
    version = plans_version()

    existing = {
        rec.skill_id: rec for rec in db.scalars(
            select(SkillGapRecommendation).where(
                SkillGapRecommendation.user_id == resume.user_id,
                SkillGapRecommendation.resume_id == resume.resume_id,
            )
        )
    }

    current_ids = set()
    ordered: list[SkillGapRecommendation] = []
    for gap in gaps:
        prereqs = missing_prerequisites(gap.skill, set(candidate_skills))
        rec = existing.get(gap.skill_id)
        if rec is None:
            rec = SkillGapRecommendation(
                user_id=resume.user_id, resume_id=resume.resume_id,
                skill_id=gap.skill_id, status="pending",
            )
            db.add(rec)
        elif rec.status == "completed" and rec.completed_via == "resume":
            # Detected earlier, but the skill is no longer on the resume.
            rec.status, rec.completed_via, rec.completed_at = "pending", None, None

        rec.internship_id = gap.internships[0].internship_id
        rec.gap_level = gap.gap_level
        rec.importance = gap.importance
        rec.priority_score = gap.priority
        rec.demand_count = gap.demand
        rec.internship_ids = [i.internship_id for i in gap.internships]
        rec.related_skills = gap.related
        rec.learning_plan = {**plan_for(gap.skill), "missing_prerequisites": prereqs}
        rec.learning_plan_version = version
        rec.recommended_action = recommended_action(gap, len(items), prereqs)
        rec.source = source
        rec.source_run_id = run_id
        rec.is_current = True
        current_ids.add(gap.skill_id)
        ordered.append(rec)

    for skill_id, rec in existing.items():
        if skill_id not in current_ids:
            rec.is_current = False

    db.commit()
    for rec in ordered:
        db.refresh(rec)

    order = learning_order([g.skill for g in gaps], known=set(candidate_skills))
    return GenerationResult(ordered, order, items, newly_acquired, source, run_id)


def update_status(rec: SkillGapRecommendation, status: str) -> None:
    """Apply a progress change with consistent timestamps."""
    if status not in STATUSES:
        raise ValueError(f"Unknown status {status}")
    if status == rec.status:
        return
    now = datetime.now(timezone.utc)

    if status == "in_progress":
        rec.started_at = rec.started_at or now
        rec.completed_at, rec.completed_via = None, None
    elif status == "completed":
        rec.started_at = rec.started_at or now
        rec.completed_at, rec.completed_via = now, "user"
    else:  # pending or dismissed
        rec.completed_at, rec.completed_via = None, None
        if status == "pending":
            rec.started_at = None
    rec.status = status
