"""Persist normalized resume skills.

``sync_resume_skills`` replaces ONE resume's ``resume_skills`` rows.
Shared ``skills`` rows are only ever created or re-categorised here;
they are never deleted, because other resumes and internships use them.

Callers own the transaction: nothing here commits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.models import ResumeSkill, Skill
from backend.services.skill_normalizer import (
    CATEGORY_OTHER,
    NormalizedSkill,
    normalize_extracted_skills,
)

MAX_EVIDENCE_LENGTH = 500


def get_or_create_skills(
    db: Session, skills: list[NormalizedSkill]
) -> dict[str, Skill]:
    """Return {casefolded name: Skill}, creating missing rows safely.

    ``ON CONFLICT DO NOTHING`` makes concurrent uploads of the same new
    skill safe against the case-insensitive unique index.
    """

    if not skills:
        return {}

    for skill in skills:
        db.execute(
            insert(Skill)
            .values(name=skill.name, category=skill.category)
            .on_conflict_do_nothing()
        )

    wanted = {skill.name.casefold() for skill in skills}

    rows = db.scalars(
        select(Skill).where(func.lower(Skill.name).in_(wanted))
    ).all()

    by_key = {row.name.casefold(): row for row in rows}

    # Upgrade category for rows created earlier as "other" once the
    # catalog knows the skill. Never downgrade a known category.
    for skill in skills:
        row = by_key.get(skill.name.casefold())
        if (
            row is not None
            and skill.category != CATEGORY_OTHER
            and row.category != skill.category
        ):
            row.category = skill.category

    return by_key


def sync_resume_skills(
    db: Session,
    resume_id: int,
    extracted_data: dict[str, Any],
) -> list[tuple[Skill, NormalizedSkill]]:
    """Replace a resume's skill links from parser output.

    Only this resume's ``ResumeSkill`` rows are removed and re-created.
    Returns the (Skill, NormalizedSkill) pairs in resume order.
    """

    normalized = normalize_extracted_skills(extracted_data)
    skill_rows = get_or_create_skills(db, normalized)

    db.execute(
        delete(ResumeSkill).where(ResumeSkill.resume_id == resume_id)
    )

    pairs: list[tuple[Skill, NormalizedSkill]] = []

    for item in normalized:
        skill_row = skill_rows[item.name.casefold()]
        evidence = f"{item.source}: {item.raw}" if item.source else item.raw

        db.add(ResumeSkill(
            resume_id=resume_id,
            skill_id=skill_row.skill_id,
            proficiency=None,
            evidence=evidence[:MAX_EVIDENCE_LENGTH],
        ))
        pairs.append((skill_row, item))

    db.flush()

    return pairs


def get_resume_skill_rows(
    db: Session, resume_id: int
) -> list[tuple[ResumeSkill, Skill]]:
    """Return a resume's skill links with their Skill rows."""

    return list(db.execute(
        select(ResumeSkill, Skill)
        .join(Skill, Skill.skill_id == ResumeSkill.skill_id)
        .where(ResumeSkill.resume_id == resume_id)
        .order_by(Skill.category, Skill.name)
    ).tuples())
