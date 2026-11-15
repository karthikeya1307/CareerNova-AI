
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.internship_schema import InternshipResponse


class ScoreComponent(BaseModel):
    name: str                 # skills | semantic | education | location
    score: float              # 0..1
    weight: float
    weighted: float           # contribution to the final score (0..100 scale)
    status: str               # assessed | unknown | not_stated | unavailable
    detail: str


class MatchItem(BaseModel):
    rank: int | None
    score: float = Field(ge=0, le=100)
    label: str
    algorithm_version: str
    # Sum of the components' weighted contributions, before caps.
    score_before_caps: float = Field(ge=0, le=100)
    data_completeness: float
    required_skill_coverage: float | None
    components: list[ScoreComponent]
    matched_required_skills: list[str]
    missing_required_skills: list[str]
    matched_preferred_skills: list[str]
    missing_preferred_skills: list[str]
    missing_information: list[str]
    caps_applied: list[str]
    explanation: list[str]
    internship: InternshipResponse


class MatchRunResponse(BaseModel):
    run_id: UUID
    resume_id: int
    algorithm_version: str
    created_at: datetime
    semantic_available: bool
    candidates_considered: int
    filters: dict
    results: list[MatchItem]


class MatchRunSummary(BaseModel):
    run_id: UUID
    created_at: datetime
    algorithm_version: str | None
    result_count: int
    top_score: float | None
    top_label: str | None
