"""Request/response schemas for the career assistant (Phase 8).

Request bodies reject unknown fields. All timestamps are returned in UTC
ISO 8601 ending in ``Z`` (same convention as Phase 7).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from backend.schemas.application_schema import UTCDateTime, strip_text

MAX_MESSAGE_CHARS = 2000

Title = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(strip_text)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationCreate(StrictModel):
    resume_id: int | None = Field(default=None, ge=1)
    title: Title | None = None


class ConversationUpdate(StrictModel):
    resume_id: int | None = Field(default=None, ge=1)
    title: Title | None = None


class MessageCreate(StrictModel):
    message: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_CHARS), AfterValidator(strip_text)]
    use_llm: bool = False
    llm_consent: bool = False


class SourceOut(BaseModel):
    type: str
    id: str
    label: str
    available: bool | None = None


class MessageOut(BaseModel):
    message_id: int
    sender: str
    content: str
    intent: str | None
    sources: list[SourceOut]
    result_set: dict[str, Any] | None
    suggested_actions: list[dict[str, Any]]
    generation_method: str | None
    warnings: list[dict[str, Any]]
    created_at: UTCDateTime


class ConversationOut(BaseModel):
    conversation_id: int
    title: str | None
    resume_id: int | None
    message_count: int
    last_message_at: UTCDateTime | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    messages: list[MessageOut] | None = None


class ConversationList(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[ConversationOut]


class ExchangeOut(BaseModel):
    conversation_id: int
    user_message: MessageOut
    assistant_message: MessageOut


class CapabilitiesOut(BaseModel):
    intents: dict[str, list[str]]
    llm: dict[str, Any]
    limits: dict[str, int]
    notes: list[str]
