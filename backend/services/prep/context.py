"""The signed-in student's resume as context for the preparation agent (never another user's)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Resume
from backend.services.ats import skill_locations
from backend.services.fact_base import CandidateFacts, NoExtractionError, build_fact_base
from backend.services.candidate_profile import latest_completed_extraction

EVIDENCE_KINDS = ("project", "experience", "internship", "certification", "achievement")
LABEL = {"project": "Project", "experience": "Experience", "internship": "Internship",
         "certification": "Certification", "achievement": "Achievement", "summary": "Summary",
         "education": "Education"}


def short_title(title: str, limit: int = 90) -> str:
    """A resume entry's first line, trimmed for display (no trailing full stop, cut at a word)."""
    text = title.strip().rstrip(".")
    # "Sales Dashboard - Built a Power BI ..." -> "Sales Dashboard" (a short name before a dash or colon).
    head = re.split(r"\s[-–—:]\s|:\s", text, maxsplit=1)[0].strip()
    # ...but never inside a date range ("Jun 2025 - Aug 2025").
    if 3 <= len(head) <= 60 and head != text and not re.search(r"\b(19|20)\d{2}$", head):
        text = head
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
    return text


@dataclass
class ResumeContext:
    resume: Resume
    facts: CandidateFacts
    locations: dict[str, list[str]]          # skill (casefold) -> ["skills", fact ids...]

    @property
    def skills(self) -> list[str]:
        return self.facts.skills

    def has(self, skill: str) -> bool:
        return skill.casefold() in self.locations

    def evidence(self, skill: str) -> list[dict[str, str]]:
        """Resume entries (not the skills list) that mention the skill: [{fact_id, kind, title}]."""
        out = []
        for fact_id in self.locations.get(skill.casefold(), []):
            fact = self.facts.by_id.get(fact_id)
            if fact is not None and fact.kind in EVIDENCE_KINDS:
                out.append({"fact_id": fact.id, "kind": fact.kind, "title": short_title(fact.title)})
        return out


def choose_resume(db: Session, user_id: int, preferred_resume_id: int | None = None) -> Resume | None:
    """The preferred resume if it belongs to the user and is parsed, else their latest parsed resume."""
    if preferred_resume_id:
        resume = db.scalar(select(Resume).where(Resume.resume_id == preferred_resume_id, Resume.user_id == user_id))
        if resume is not None and latest_completed_extraction(db, resume.resume_id) is not None:
            return resume
    # The student's preferred version first (if parsed), then the newest parsed resume.
    for resume in db.scalars(select(Resume).where(Resume.user_id == user_id)
                             .order_by(Resume.is_preferred.desc(), Resume.uploaded_at.desc(), Resume.resume_id.desc())):
        if latest_completed_extraction(db, resume.resume_id) is not None:
            return resume
    return None


def load_context(db: Session, user_id: int, preferred_resume_id: int | None = None) -> ResumeContext | None:
    """None when the user has no successfully parsed resume (the caller asks them to upload one)."""
    resume = choose_resume(db, user_id, preferred_resume_id)
    if resume is None:
        return None
    try:
        facts = build_fact_base(db, resume)
    except NoExtractionError:
        return None
    return ResumeContext(resume, facts, skill_locations(facts))


def skill_evidence(ctx: ResumeContext) -> list[dict[str, Any]]:
    """Every resume skill with where it is shown; skills used in projects/experience rank first."""
    rows = []
    for skill in ctx.skills:
        evidence = ctx.evidence(skill)
        rows.append({"skill": skill, "evidence": evidence, "evidence_count": len(evidence)})
    rows.sort(key=lambda r: (-r["evidence_count"], ctx.skills.index(r["skill"])))
    return rows


def profile(ctx: ResumeContext) -> dict[str, Any]:
    """What the agent knows from the resume (titles only - no contact details)."""
    f = ctx.facts

    def titles(*kinds: str) -> list[str]:
        return [short_title(x.title, 120) for x in f.of_kind(*kinds)]

    return {
        "resume_id": ctx.resume.resume_id,
        "filename": ctx.resume.filename,
        "first_name": ((f.contact.get("name") or "").split() or [None])[0],
        "degree": f.degree,
        "education": titles("education"),
        "skills": list(f.skills),
        "projects": titles("project"),
        "experience": titles("experience", "internship"),
        "certifications": titles("certification"),
        "achievements": titles("achievement"),
        "has_summary": bool(f.of_kind("summary")),
    }
