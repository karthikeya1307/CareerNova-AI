
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class ResumeParsedData(BaseModel):
    """Structured information extracted from a resume."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None

    linkedin: str | None = None
    github: str | None = None

    professional_summary: str | None = None

    skills: list[str] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)

    education: list[dict[str, Any]] = Field(default_factory=list)
    work_experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)

    certifications: list[str] = Field(default_factory=list)
    internships: list[dict[str, Any]] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class NormalizedSkillItem(BaseModel):
    """A canonical skill linked to a resume."""

    skill_id: int
    name: str
    category: str | None
    # Parser section the skill came from, e.g. "technical_skills".
    source: str | None = None


class ResumeUploadResponse(BaseModel):
    """Response returned after successful resume upload and parsing."""

    resume_id: int
    filename: str
    file_type: str
    status: str
    uploaded_at: datetime
    extracted_data: ResumeParsedData
    # Added in Phase 1 (additive; existing fields unchanged).
    normalized_skills: list[NormalizedSkillItem] = Field(
        default_factory=list
    )


class ResumeDetailResponse(BaseModel):
    """Response returned when retrieving a saved resume."""

    resume_id: int
    filename: str
    file_type: str
    status: str
    uploaded_at: datetime
    extracted_data: ResumeParsedData
    # Added in Phase 1 (additive; existing fields unchanged).
    normalized_skills: list[NormalizedSkillItem] = Field(
        default_factory=list
    )


class ResumeSkillsResponse(BaseModel):
    """Normalized skills of one resume."""

    resume_id: int
    skills: list[NormalizedSkillItem]


class ResumeListItem(BaseModel):
    """Basic resume information for listing a user's uploads."""

    resume_id: int
    filename: str
    file_type: str
    status: str
    uploaded_at: datetime
