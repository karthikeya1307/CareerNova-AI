"""Open internships relevant to a role (the career track's skills), with the student's matching / missing skills."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Internship, InternshipSkill
from backend.services import career_tracks
from backend.services.internship_text import internship_skill_names
from backend.services.matching_agent import is_eligible
from backend.services.prep.context import ResumeContext


def for_role(db: Session, track: dict[str, Any], ctx: ResumeContext, limit: int = 3) -> list[dict[str, Any]]:
    internships = [i for i in db.scalars(
        select(Internship).where(Internship.is_active.is_(True))
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))) if is_eligible(i)]
    out = []
    for internship, _ in career_tracks.relevant_jobs(track, internships, limit):
        required, preferred = internship_skill_names(internship)
        wanted = list(dict.fromkeys(required + preferred))
        out.append({
            "internship_id": internship.internship_id, "title": internship.title, "company": internship.company,
            "location": internship.location, "source": internship.source,
            "matching_skills": [s for s in wanted if ctx.has(s)],
            "missing_skills": [s for s in required if not ctx.has(s)],
        })
    return out
