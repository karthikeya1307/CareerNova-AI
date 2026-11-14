"""Validate and import the internship dataset into PostgreSQL.

PostgreSQL is the single source of truth for internships. The import is
idempotent: records are matched by their dataset ``id``
(``internships.external_id``); re-running updates changed records and
leaves unchanged ones alone. An administrator's deactivation is never
undone by a re-import.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from backend.models import Internship, InternshipSkill, KnowledgeDocument
from backend.services.resume_skills import get_or_create_skills
from backend.services.skill_normalizer import CATEGORY_OTHER, normalize_skill

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "backend" / "data" / "internships.json"

MAX_STIPEND = 1_000_000
MAX_DURATION_WEEKS = 104
MAX_SKILLS = 30


# ============================================================
# DATASET RECORD SCHEMA
# ============================================================

class InternshipRecord(BaseModel):
    """One posting in internships.json. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    company: str = Field(min_length=1, max_length=200)
    role_title: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=80)
    location: str = Field(min_length=1, max_length=150)
    mode: Literal["Onsite", "Hybrid", "Remote"]
    duration_weeks: int = Field(ge=1, le=MAX_DURATION_WEEKS)
    stipend_inr_per_month: int = Field(ge=0, le=MAX_STIPEND)
    min_education: str = Field(min_length=1, max_length=200)
    required_skills: list[str] = Field(min_length=1, max_length=MAX_SKILLS)
    preferred_skills: list[str] = Field(default_factory=list, max_length=MAX_SKILLS)
    description: str = Field(min_length=1, max_length=5000)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return str(uuid.UUID(value))

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def validate_skill_list(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values]
        if any(not v for v in cleaned):
            raise ValueError("skill names must not be empty")
        if len({v.casefold() for v in cleaned}) != len(cleaned):
            raise ValueError("duplicate skills in list")
        return cleaned


@dataclass
class ValidationReport:
    total: int = 0
    valid: list[InternshipRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    unmapped_skills: dict[str, int] = field(default_factory=dict)
    skill_count: int = 0
    stipend_range: tuple[int, int] | None = None

    @property
    def ok(self) -> bool:
        return not self.errors and not self.duplicate_ids and not self.unmapped_skills


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Dataset must be a JSON array of internship objects")
    return data


def validate_records(raw_records: list[Any]) -> ValidationReport:
    """Validate every record; collect all problems instead of stopping."""

    report = ValidationReport(total=len(raw_records))
    seen_ids: dict[str, int] = {}
    skills_seen: set[str] = set()

    for index, raw in enumerate(raw_records):
        label = f"record {index}"

        if not isinstance(raw, dict):
            report.errors.append(f"{label}: not an object")
            continue

        try:
            record = InternshipRecord.model_validate(raw)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                report.errors.append(f"{label} ({raw.get('id')}): {loc}: {err['msg']}")
            continue

        label = f"record {index} ({record.id})"

        if record.id in seen_ids:
            report.duplicate_ids.append(record.id)
            continue
        seen_ids[record.id] = index

        overlap = (
            {s.casefold() for s in record.required_skills}
            & {s.casefold() for s in record.preferred_skills}
        )
        if overlap:
            report.errors.append(
                f"{label}: skills both required and preferred: {sorted(overlap)}"
            )
            continue

        for raw_skill in record.required_skills + record.preferred_skills:
            normalized = normalize_skill(raw_skill)
            if normalized is None or normalized.category == CATEGORY_OTHER:
                report.unmapped_skills[raw_skill] = (
                    report.unmapped_skills.get(raw_skill, 0) + 1
                )
            else:
                skills_seen.add(normalized.name)

        report.valid.append(record)

    report.skill_count = len(skills_seen)
    if report.valid:
        stipends = [r.stipend_inr_per_month for r in report.valid]
        report.stipend_range = (min(stipends), max(stipends))

    return report


# ============================================================
# IMPORT
# ============================================================

@dataclass
class SeedResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


def _record_fields(record: InternshipRecord) -> dict[str, Any]:
    return {
        "title": record.role_title,
        "company": record.company,
        "description": record.description,
        "location": record.location,
        "domain": record.domain,
        "work_mode": record.mode,
        "duration_weeks": record.duration_weeks,
        "stipend_per_month": record.stipend_inr_per_month,
        "stipend_currency": "INR",
        "min_education": record.min_education,
        "source": "dataset",
    }


def _record_skills(record: InternshipRecord) -> dict[str, str]:
    """canonical skill name -> importance"""
    skills: dict[str, str] = {}
    for importance, values in (
        ("required", record.required_skills),
        ("preferred", record.preferred_skills),
    ):
        for raw in values:
            normalized = normalize_skill(raw)
            if normalized is not None:
                skills.setdefault(normalized.name, importance)
    return skills


def set_internship_skills(
    db: Session, internship: Internship, skills: dict[str, str]
) -> None:
    """Replace an internship's skill links (shared skills are reused)."""

    normalized = [
        s for s in (normalize_skill(name) for name in skills) if s is not None
    ]
    rows = get_or_create_skills(db, normalized)

    db.execute(
        delete(InternshipSkill).where(
            InternshipSkill.internship_id == internship.internship_id
        )
    )
    for skill in normalized:
        db.add(InternshipSkill(
            internship_id=internship.internship_id,
            skill_id=rows[skill.name.casefold()].skill_id,
            importance=skills.get(skill.name) or skills.get(skill.raw, "required"),
        ))
    db.flush()
    db.expire(internship, ["skill_links"])


def mark_index_pending(db: Session, internship_id: int) -> None:
    """Flag the internship's knowledge document for re-indexing."""
    for document in db.scalars(
        select(KnowledgeDocument).where(
            KnowledgeDocument.internship_id == internship_id
        )
    ):
        document.indexing_status = "pending"


def seed_internships(
    db: Session, records: list[InternshipRecord], apply: bool
) -> SeedResult:
    """Create or update internships. Caller commits (or rolls back)."""

    result = SeedResult()

    existing = {
        row.external_id: row
        for row in db.scalars(
            select(Internship)
            .where(Internship.external_id.in_([r.id for r in records]))
            .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
        )
    }

    for record in records:
        fields = _record_fields(record)
        skills = _record_skills(record)
        current = existing.get(record.id)

        if current is None:
            result.created += 1
            if apply:
                internship = Internship(external_id=record.id, is_active=True, **fields)
                db.add(internship)
                db.flush()
                set_internship_skills(db, internship, skills)
            continue

        current_skills = {
            link.skill.name: link.importance for link in current.skill_links
        }
        changed = any(getattr(current, k) != v for k, v in fields.items())

        if not changed and current_skills == skills:
            result.unchanged += 1
            continue

        result.updated += 1
        if apply:
            for key, value in fields.items():
                setattr(current, key, value)
            set_internship_skills(db, current, skills)
            mark_index_pending(db, current.internship_id)

    if apply:
        db.flush()

    return result
