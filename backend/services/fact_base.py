"""Candidate fact base for document generation (Phase 5).

Every statement about the candidate in a generated document must come from
a fact here. Facts are built from the latest successful resume extraction
and the student's profile and get stable IDs:

    sum-1            professional summary
    prof-1           degree from the profile page
    edu-N            education entries
    exp-N            work experience entries
    int-N            internship entries (resume section)
    proj-N           project entries
    cert-N, ach-N, lang-N   certifications, achievements, languages

Contact details (name, e-mail, phone, links, location) are kept separately
in ``CandidateFacts.contact`` and are NEVER part of ``facts``, so they can
never be sent to an external LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Resume, StudentProfile
from backend.services.candidate_profile import latest_completed_extraction
from backend.services.resume_skills import get_resume_skill_rows

MAX_FACT_CHARS = 1200

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
URL_RE = re.compile(r"(https?://\S+|www\.\S+|linkedin\.com/\S+|github\.com/\S+)", re.IGNORECASE)


class NoExtractionError(ValueError):
    """The resume has no successful extraction to build facts from."""


@dataclass(frozen=True)
class Fact:
    id: str
    kind: str          # summary | education | experience | internship | project | ...
    text: str

    @property
    def title(self) -> str:
        return self.text.splitlines()[0].strip()

    @property
    def lines(self) -> list[str]:
        return [line.strip() for line in self.text.splitlines() if line.strip()]

    @property
    def body(self) -> list[str]:
        """Description lines after the title (or the single line)."""
        return self.lines[1:] if len(self.lines) > 1 else self.lines


@dataclass
class CandidateFacts:
    resume_id: int
    contact: dict[str, str | None]
    facts: list[Fact]
    skills: list[str]                       # canonical, from resume_skills
    degree: str | None = None
    by_id: dict[str, Fact] = field(default_factory=dict)

    def __post_init__(self):
        self.by_id = {f.id: f for f in self.facts}

    def of_kind(self, *kinds: str) -> list[Fact]:
        return [f for f in self.facts if f.kind in kinds]


def scrub(text: str, contact: dict[str, str | None]) -> str:
    """Remove e-mail addresses, phone numbers, links and the name."""
    text = EMAIL_RE.sub("[removed]", text)
    text = URL_RE.sub("[removed]", text)
    text = PHONE_RE.sub("[removed]", text)
    name = (contact.get("name") or "").strip()
    if len(name) >= 3:
        text = re.sub(re.escape(name), "the candidate", text, flags=re.IGNORECASE)
    return text


def _entry_texts(values: Any) -> list[str]:
    result = []
    for value in values or []:
        text = value.get("details") if isinstance(value, dict) else value
        if isinstance(text, str) and text.strip():
            result.append(text.strip()[:MAX_FACT_CHARS])
    return result


def build_fact_base(db: Session, resume: Resume) -> CandidateFacts:
    extraction = latest_completed_extraction(db, resume.resume_id)
    if extraction is None:
        raise NoExtractionError("This resume has no successfully parsed content.")
    data = extraction.extracted_data or {}

    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == resume.user_id))

    contact = {
        "name": data.get("full_name"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "linkedin": data.get("linkedin"),
        "github": data.get("github"),
        "location": (profile.location if profile and profile.location else data.get("address")),
    }

    facts: list[Fact] = []

    def add(prefix: str, kind: str, texts: list[str]) -> None:
        for number, text in enumerate(texts, start=1):
            facts.append(Fact(f"{prefix}-{number}", kind, scrub(text, contact)))

    summary = data.get("professional_summary")
    if isinstance(summary, str) and summary.strip():
        add("sum", "summary", [summary.strip()[:MAX_FACT_CHARS]])

    degree = None
    if profile and profile.degree:
        parts = [profile.degree, profile.college, str(profile.graduation_year) if profile.graduation_year else None]
        degree = profile.degree
        add("prof", "education", [", ".join(p for p in parts if p)])

    education = _entry_texts(data.get("education"))
    add("edu", "education", education)
    if degree is None and education:
        degree = education[0].splitlines()[0]

    add("exp", "experience", _entry_texts(data.get("work_experience")))
    add("int", "internship", _entry_texts(data.get("internships")))
    add("proj", "project", _entry_texts(data.get("projects")))
    add("cert", "certification", _entry_texts(data.get("certifications")))
    add("ach", "achievement", _entry_texts(data.get("achievements")))
    add("lang", "language", _entry_texts(data.get("languages")))

    skills = [skill.name for _, skill in get_resume_skill_rows(db, resume.resume_id)]
    return CandidateFacts(resume.resume_id, contact, facts, skills, degree)
