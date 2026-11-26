
from datetime import datetime
from typing import Any

from pydantic import field_validator, BaseModel, Field, ConfigDict, model_validator


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
    # P2 (additive): earlier uploads of the same file or the same content.
    duplicate_of: list[int] = Field(default_factory=list)
    duplicate_kind: str | None = None          # identical_file | same_content


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
    # P2 (additive): where the current data came from (a parser, or "user_corrected").
    parser_type: str | None = None
    corrected: bool = False


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
    # Resume versions: 1 = the first resume uploaded to the account; label = the student's own name for it;
    # is_preferred = the version the student chose as current (at most one).
    version: int | None = None
    label: str | None = None
    is_preferred: bool = False


class ResumeVersionUpdate(BaseModel):
    """PATCH /resumes/{id}: rename a version and/or mark it as the preferred (current) resume."""

    label: str | None = Field(default=None, max_length=120)
    is_preferred: bool | None = None

    @field_validator("label")
    @classmethod
    def clean_label(cls, value):
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class ResumeCorrection(ResumeParsedData):
    """The student's corrected version of the extracted data (stored as a new extraction).

    Size limits keep the stored JSON bounded; content is the student's own and is not invented.
    """

    @model_validator(mode="after")
    def check_sizes(self):
        for name, value in self.model_dump().items():
            if isinstance(value, str) and len(value) > 5000:
                raise ValueError(f"{name} is too long (max 5000 characters).")
            if isinstance(value, list):
                if len(value) > 100:
                    raise ValueError(f"{name} has too many items (max 100).")
                for item in value:
                    text = item if isinstance(item, str) else " ".join(
                        str(v) for v in (item or {}).values()) if isinstance(item, dict) else str(item)
                    if len(text) > 5000:
                        raise ValueError(f"An item in {name} is too long (max 5000 characters).")
        return self
