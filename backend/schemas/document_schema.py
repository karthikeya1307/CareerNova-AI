
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator


# ============================================================
# REQUESTS
# ============================================================

class ResumeOptionsIn(BaseModel):
    max_skills: int = Field(default=15, ge=5, le=30)
    max_projects: int = Field(default=3, ge=0, le=6)
    max_experience: int = Field(default=4, ge=0, le=8)
    max_bullets: int = Field(default=4, ge=1, le=6)


class LLMChoice(BaseModel):
    use_llm: bool = False
    # Must be true when use_llm is true: the student accepted the disclosure.
    llm_consent: bool = False


class CreateResumeRequest(LLMChoice):
    resume_id: int
    internship_id: int
    options: ResumeOptionsIn = Field(default_factory=ResumeOptionsIn)


class CreateCoverLetterRequest(LLMChoice):
    resume_id: int
    internship_id: int
    tone: Literal["formal", "concise"] = "formal"
    emphasize_skills: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("emphasize_skills")
    @classmethod
    def clean(cls, values):
        cleaned = [v.strip() for v in values if v and v.strip()]
        if any(len(v) > 60 for v in cleaned):
            raise ValueError("skill names must be at most 60 characters")
        return cleaned


# ============================================================
# EDITABLE CONTENT
# ============================================================

ShortText = Annotated[str, Field(max_length=200)]
LineText = Annotated[str, Field(min_length=1, max_length=500)]


class Header(BaseModel):
    name: ShortText | None = None
    email: ShortText | None = None
    phone: ShortText | None = None
    location: ShortText | None = None
    linkedin: ShortText | None = None
    github: ShortText | None = None
    target: ShortText | None = None


class ResumeItem(BaseModel):
    heading: ShortText | None = None
    lines: list[LineText] = Field(default_factory=list, max_length=20)
    fact_ids: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=20)


class ResumeSection(BaseModel):
    key: Annotated[str, Field(min_length=1, max_length=40)]
    title: Annotated[str, Field(min_length=1, max_length=60)]
    items: list[ResumeItem] = Field(default_factory=list, max_length=50)


class ResumeContent(BaseModel):
    type: Literal["resume"]
    header: Header = Field(default_factory=Header)
    sections: list[ResumeSection] = Field(max_length=12)


class Paragraph(BaseModel):
    key: Annotated[str, Field(min_length=1, max_length=40)]
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    fact_ids: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=20)


class Recipient(BaseModel):
    company: ShortText | None = None
    title: ShortText | None = None


class CoverLetterContent(BaseModel):
    type: Literal["cover_letter"]
    header: Header = Field(default_factory=Header)
    recipient: Recipient = Field(default_factory=Recipient)
    paragraphs: list[Paragraph] = Field(min_length=1, max_length=12)
    signoff: Annotated[str, Field(max_length=60)] = "Sincerely,"
    signature: ShortText | None = None


DocumentContent = Annotated[Union[ResumeContent, CoverLetterContent], Field(discriminator="type")]


class UpdateDocumentRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    content: DocumentContent


# ============================================================
# RESPONSES
# ============================================================

class InternshipRef(BaseModel):
    internship_id: int
    title: str
    company: str
    is_active: bool


class DocumentResponse(BaseModel):
    document_id: int
    document_type: str
    title: str | None
    resume_id: int | None
    internship: InternshipRef | None
    generation_method: str | None
    llm_provider: str | None
    llm_model: str | None
    current_version: int
    content: str
    content_json: dict[str, Any] | None
    fact_check: dict[str, Any] | None
    ats_report: dict[str, Any] | None
    options: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class DocumentListItem(BaseModel):
    document_id: int
    document_type: str
    title: str | None
    resume_id: int | None
    internship: InternshipRef | None
    generation_method: str | None
    current_version: int
    warning_count: int
    created_at: datetime
    updated_at: datetime


class VersionItem(BaseModel):
    version: int
    source: str
    warning_count: int
    created_at: datetime


class LLMStatusResponse(BaseModel):
    available: bool
    provider: str | None
    model: str | None
    disclosure: str | None
