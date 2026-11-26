
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.services.interview_generator import DEFAULT_MIX, MAX_QUESTIONS


class QuestionMix(BaseModel):
    technical: int = Field(default=DEFAULT_MIX["technical"], ge=0, le=10)
    project: int = Field(default=DEFAULT_MIX["project"], ge=0, le=5)
    behavioral: int = Field(default=DEFAULT_MIX["behavioral"], ge=0, le=5)
    internship: int = Field(default=DEFAULT_MIX["internship"], ge=0, le=5)

    @model_validator(mode="after")
    def total_in_range(self):
        total = self.technical + self.project + self.behavioral + self.internship
        if not 1 <= total <= MAX_QUESTIONS:
            raise ValueError(f"The question mix must contain 1-{MAX_QUESTIONS} questions")
        return self


class CreateSessionRequest(BaseModel):
    resume_id: int
    internship_id: int | None = None
    mode: Literal["practice", "mock"] = "practice"
    mix: QuestionMix = Field(default_factory=QuestionMix)
    difficulty: Literal["mixed", "easy", "medium", "hard"] = "mixed"
    # Career-track slug (e.g. "java-developer"): technical questions focus on that role's skills.
    target_role: str | None = Field(default=None, max_length=60, pattern=r"^[a-z0-9-]+$")
    time_limit_seconds: int | None = Field(default=None, ge=30, le=900)
    use_llm: bool = False
    llm_consent: bool = False


class AnswerRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=5000)
    time_taken_seconds: int | None = Field(default=None, ge=0, le=3600)
    use_llm_feedback: bool = False
    llm_consent: bool = False

    @field_validator("answer_text")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Answer must not be blank")
        return value


class QuestionOut(BaseModel):
    question_id: int
    position: int
    category: str
    difficulty: str | None
    text: str
    skill: str | None
    skill_status: str | None
    source_fact_ids: list[str]
    time_limit_seconds: int | None
    answered: bool
    attempts: int
    latest_score: float | None
    latest_feedback: str | None
    evaluation: dict[str, Any] | None
    revealed: bool
    # Hidden (null) in mock mode until answered or revealed.
    key_points: list[str] | None
    explanation: str | None
    suggested_answer: dict[str, Any] | None


class SessionOut(BaseModel):
    session_id: int
    title: str | None
    mode: str | None
    status: str
    resume_id: int | None
    internship_id: int | None
    difficulty: str | None
    question_mix: dict[str, Any] | None
    generation_method: str | None
    total_questions: int | None
    answered_count: int
    score: float | None
    summary: dict[str, Any] | None
    # Why the session has fewer (or different) questions than requested.
    notices: list[dict[str, Any]] = []
    started_at: datetime
    completed_at: datetime | None
    questions: list[QuestionOut]


class SessionListItem(BaseModel):
    session_id: int
    title: str | None
    mode: str | None
    status: str
    internship_id: int | None
    resume_id: int | None
    total_questions: int | None
    answered_count: int
    score: float | None
    started_at: datetime
    completed_at: datetime | None


class AnswerOut(BaseModel):
    answer_id: int
    question_id: int
    attempt: int
    answer_text: str
    time_taken_seconds: int | None
    score: float
    label: str
    evaluation: dict[str, Any]
    feedback: str
    feedback_source: str
    created_at: datetime


class PreviewQuestion(BaseModel):
    category: str
    difficulty: str
    text: str
    skill: str | None
    skill_status: str | None
    source_fact_ids: list[str]


class ProgressOut(BaseModel):
    sessions_total: int
    sessions_completed: int
    questions_answered: int
    answers_total: int
    average_score: float | None
    by_category: dict[str, float]
    by_skill: dict[str, float]
    retry_improvement: dict[str, Any]
    trend: list[dict[str, Any]]
