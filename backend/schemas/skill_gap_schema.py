
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


GapStatus = Literal["pending", "in_progress", "completed", "dismissed"]


class InternshipRef(BaseModel):
    internship_id: int
    title: str
    company: str
    domain: str | None = None
    is_active: bool = True


class RelatedSkill(BaseModel):
    skill: str
    reason: str


class SkillItem(BaseModel):
    skill: str
    category: str | None
    importance: str                  # required | preferred
    status: str                      # matched | partial | missing
    related_skills: list[RelatedSkill] = Field(default_factory=list)


class LearningPlan(BaseModel):
    skill: str
    curated: bool
    level: str | None
    estimated_hours: int | None
    prerequisites: list[str]
    missing_prerequisites: list[str] = Field(default_factory=list)
    topics: list[str]
    note: str | None = None


class SkillPlanItem(SkillItem):
    plan: LearningPlan


class InternshipGapResponse(BaseModel):
    resume_id: int
    internship: InternshipRef
    algorithm_version: str
    learning_plan_version: str
    summary: dict[str, int]
    matched: list[SkillItem]
    partial: list[SkillItem]
    missing: list[SkillItem]
    learning_order: list[str]
    learning_plans: list[SkillPlanItem]


class GenerateRequest(BaseModel):
    """Choose the internships to analyse.

    Provide ``internship_ids`` OR ``run_id``. With neither, the resume's
    latest matching run is used. ``top_k`` limits how many results of a
    run are analysed.
    """

    internship_ids: list[int] | None = Field(default=None, min_length=1, max_length=20)
    run_id: UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("internship_ids")
    @classmethod
    def unique_ids(cls, value):
        if value is not None and len(set(value)) != len(value):
            raise ValueError("internship_ids must be unique")
        return value

    @model_validator(mode="after")
    def one_source(self):
        if self.internship_ids is not None and self.run_id is not None:
            raise ValueError("Provide either internship_ids or run_id, not both")
        return self


class RecommendationItem(BaseModel):
    recommendation_id: int
    resume_id: int | None
    skill_id: int
    skill: str
    category: str | None
    gap_level: str
    importance: str | None
    priority_score: float | None
    demand_count: int | None
    internship_ids: list[int]
    related_skills: list[RelatedSkill]
    recommended_action: str
    learning_plan: dict[str, Any] | None
    learning_plan_version: str | None
    status: GapStatus
    completed_via: str | None
    is_current: bool
    source: str | None
    source_run_id: UUID | None
    top_internship: InternshipRef | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AnalysedInternship(InternshipRef):
    relevance: float           # compatibility score / 100 used as weight


class GenerateResponse(BaseModel):
    resume_id: int
    algorithm_version: str
    learning_plan_version: str
    source: str
    run_id: UUID | None
    internships: list[AnalysedInternship]
    skipped_internship_ids: list[int]
    newly_acquired_skills: list[str]
    learning_order: list[str]
    recommendations: list[RecommendationItem]


class StatusUpdate(BaseModel):
    status: GapStatus
