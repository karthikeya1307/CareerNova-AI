"""Build a matching candidate from a resume and the student's profile.

Sources, in priority order:
    skills    -> the resume's normalized skills (Phase 1)
    degree    -> StudentProfile.degree, else first parsed education entry
    location  -> request override, else StudentProfile.location,
                 else parsed resume address

Only skills, degree, location and summary are used; no names, emails or
phone numbers enter the candidate or the semantic query.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Resume, ResumeExtraction, StudentProfile
from backend.services.compatibility import Candidate
from backend.services.resume_skills import get_resume_skill_rows

MAX_SUMMARY_CHARS = 500


class InsufficientResumeDataError(ValueError):
    """The resume has nothing to match on."""


@dataclass(frozen=True)
class CandidateContext:
    candidate: Candidate
    query_text: str


def latest_completed_extraction(db: Session, resume_id: int) -> ResumeExtraction | None:
    return db.scalar(
        select(ResumeExtraction)
        .where(
            ResumeExtraction.resume_id == resume_id,
            ResumeExtraction.status == "completed",
        )
        .order_by(ResumeExtraction.created_at.desc(), ResumeExtraction.extraction_id.desc())
        .limit(1)
    )


def _first_education_text(data: dict) -> str | None:
    for entry in data.get("education") or []:
        if isinstance(entry, dict):
            text = entry.get("details") or entry.get("degree")
            if isinstance(text, str) and text.strip():
                return text.strip().splitlines()[0][:200]
    return None


def build_query_text(skills: list[str], degree: str | None, summary: str | None) -> str:
    """Same format as used for the semantic calibration study."""
    parts = [f"Skills: {', '.join(skills)}"]
    if degree:
        parts.append(f"Education: {degree}")
    if summary:
        parts.append(f"Summary: {summary[:MAX_SUMMARY_CHARS]}")
    return "\n".join(parts)


def build_candidate(
    db: Session, resume: Resume, location_override: str | None = None
) -> CandidateContext:
    skills = [skill.name for _, skill in get_resume_skill_rows(db, resume.resume_id)]
    if not skills:
        raise InsufficientResumeDataError(
            "This resume has no recognised skills to match on. "
            "Add a skills section to the resume and re-parse it."
        )

    extraction = latest_completed_extraction(db, resume.resume_id)
    data = extraction.extracted_data if extraction else {}

    profile = db.scalar(
        select(StudentProfile).where(StudentProfile.user_id == resume.user_id)
    )

    degree, degree_source = None, None
    if profile and profile.degree:
        degree, degree_source = profile.degree, "profile"
    elif (resume_degree := _first_education_text(data)):
        degree, degree_source = resume_degree, "resume"

    location, location_source = None, None
    if location_override and location_override.strip():
        location, location_source = location_override.strip(), "request"
    elif profile and profile.location:
        location, location_source = profile.location, "profile"
    elif isinstance(data.get("address"), str) and data["address"].strip():
        location, location_source = data["address"].strip(), "resume"

    summary = data.get("professional_summary")
    summary = summary if isinstance(summary, str) else None

    candidate = Candidate(
        skills=tuple(skills),
        degree_text=degree,
        degree_source=degree_source,
        location_text=location,
        location_source=location_source,
    )
    return CandidateContext(
        candidate=candidate,
        query_text=build_query_text(skills, degree, summary),
    )
