
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


WorkMode = Literal["Onsite", "Hybrid", "Remote"]


def _clean_optional(value):
    if value is None:
        return None
    value = value.strip()
    return value or None


def _clean_skills(values):
    if values is None:
        return None
    cleaned, seen = [], set()
    for value in values:
        value = value.strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            cleaned.append(value)
    return cleaned


def _validate_url(value):
    value = _clean_optional(value)
    if value is not None and not value.lower().startswith(("http://", "https://")):
        raise ValueError("application_url must start with http:// or https://")
    return value


# ============================================================
# RESPONSES
# ============================================================

class InternshipSkillItem(BaseModel):
    skill_id: int
    name: str
    category: str | None
    importance: str


class InternshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internship_id: int
    external_id: str | None
    title: str
    company: str
    description: str | None
    eligibility: str | None
    location: str | None
    application_url: str | None
    deadline: datetime | None
    domain: str | None
    work_mode: str | None
    duration_weeks: int | None
    stipend_per_month: int | None
    stipend_currency: str
    min_education: str | None
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    skills: list[InternshipSkillItem] = Field(default_factory=list)
    # Job-source tracking (P3, additive). None = unknown.
    source_url: str | None = None
    posted_at: datetime | None = None
    last_verified_at: datetime | None = None
    source_label: str | None = None        # e.g. "Sample listing (curated dataset)"
    freshness: str | None = None           # verified | stale | unverified | expired


class InternshipListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[InternshipResponse]


class InternshipFiltersResponse(BaseModel):
    domains: list[str]
    work_modes: list[str]
    locations: list[str]


class InternshipSearchHit(BaseModel):
    similarity: float                     # cosine similarity of the text (0 when only keywords were used)
    score: float = 0.0                    # relevance: exact skill/role/keyword match combined with similarity
    reasons: list[str] = []               # why this posting matched the query
    internship: InternshipResponse


class SearchInterpretation(BaseModel):
    skills: list[str] = []
    roles: list[str] = []
    keywords: list[str] = []
    location: str | None = None
    work_mode: str | None = None
    opportunity: str = "internship"
    experience_level: str | None = None


class InternshipSearchResponse(BaseModel):
    query: str
    index_built_at: str | None
    mode: str = "hybrid"                  # "hybrid" (meaning + exact) or "keyword" (index unavailable)
    interpretation: SearchInterpretation | None = None
    message: str | None = None            # explains empty results or the internships-only catalogue
    results: list[InternshipSearchHit]


class IndexStatusResponse(BaseModel):
    built: bool
    built_at: str | None
    model_name: str | None
    model_revision: str | None
    dimension: int | None
    indexed_vectors: int
    configured_model: str
    model_matches_configuration: bool
    active_internships: int
    document_status_counts: dict[str, int]
    stale: bool


class IndexRebuildResponse(BaseModel):
    indexed: int
    deactivated_documents: int
    built_at: str
    model_name: str
    dimension: int


# ============================================================
# ADMIN REQUESTS
# ============================================================

class InternshipCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    eligibility: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=150)
    application_url: str | None = Field(default=None, max_length=1000)
    deadline: datetime | None = None
    domain: str | None = Field(default=None, max_length=80)
    work_mode: WorkMode | None = None
    duration_weeks: int | None = Field(default=None, ge=1, le=104)
    stipend_per_month: int | None = Field(default=None, ge=0, le=1_000_000)
    stipend_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    min_education: str | None = Field(default=None, max_length=200)
    required_skills: list[str] = Field(default_factory=list, max_length=30)
    preferred_skills: list[str] = Field(default_factory=list, max_length=30)
    source_url: str | None = Field(default=None, max_length=1000)
    posted_at: datetime | None = None

    @field_validator("title", "company")
    @classmethod
    def required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("description", "eligibility", "location", "domain", "min_education")
    @classmethod
    def optional_text(cls, value):
        return _clean_optional(value)

    @field_validator("application_url", "source_url")
    @classmethod
    def url(cls, value):
        return _validate_url(value)

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def skills(cls, values):
        values = _clean_skills(values)
        if any(len(v) > 60 for v in values):
            raise ValueError("skill names must be at most 60 characters")
        return values


class InternshipUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    eligibility: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=150)
    application_url: str | None = Field(default=None, max_length=1000)
    deadline: datetime | None = None
    domain: str | None = Field(default=None, max_length=80)
    work_mode: WorkMode | None = None
    duration_weeks: int | None = Field(default=None, ge=1, le=104)
    stipend_per_month: int | None = Field(default=None, ge=0, le=1_000_000)
    stipend_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    min_education: str | None = Field(default=None, max_length=200)
    required_skills: list[str] | None = Field(default=None, max_length=30)
    preferred_skills: list[str] | None = Field(default=None, max_length=30)
    source_url: str | None = Field(default=None, max_length=1000)
    posted_at: datetime | None = None
    is_active: bool | None = None

    @field_validator("title", "company")
    @classmethod
    def required_text(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("description", "eligibility", "location", "domain", "min_education")
    @classmethod
    def optional_text(cls, value):
        return _clean_optional(value)

    @field_validator("application_url", "source_url")
    @classmethod
    def url(cls, value):
        return _validate_url(value)

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def skills(cls, values):
        values = _clean_skills(values)
        if values and any(len(v) > 60 for v in values):
            raise ValueError("skill names must be at most 60 characters")
        return values
