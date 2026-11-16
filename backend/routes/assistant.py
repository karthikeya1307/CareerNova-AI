"""Conversational career assistant API (Phase 8).

Login required; every conversation belongs to its creator and another
student's id returns 404. The assistant only reads data and suggests
actions; AI rewording is off unless ``use_llm`` and ``llm_consent`` are both
true for that message.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Conversation, Message, User
from backend.schemas.assistant_schema import (
    MAX_MESSAGE_CHARS,
    CapabilitiesOut,
    ConversationCreate,
    ConversationList,
    ConversationOut,
    ConversationUpdate,
    ExchangeOut,
    MessageCreate,
    MessageOut,
)
from backend.services.assistant import rate_limit, service
from backend.services.assistant.intents import EXAMPLES
from backend.services.llm.base import get_llm_provider, llm_status
from backend.utils.dependencies import get_current_user

router = APIRouter(prefix="/assistant", tags=["Career Assistant"])
logger = logging.getLogger(__name__)

AI_DISCLOSURE = (
    "With AI rewording, only the facts in the assistant's answer (internship details, your skills and resume "
    "facts, scores, statuses, dates and counts) and the type of question are sent to an external "
    "language-model provider ({provider}). Never sent: the text of your question, your chat history, your name, "
    "e-mail, phone, links, address or PIN code, notes, contact persons, reminder titles or descriptions, document "
    "titles, or the company and job titles you typed for external applications. Every AI sentence is checked "
    "against those facts; if it cannot be verified, the standard answer is shown instead."
)

RECENT_MESSAGES = 50


def fail(exc: service.AssistantError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def message_out(message: Message, sources: list[dict] | None = None) -> MessageOut:
    return MessageOut(
        message_id=message.message_id, sender=message.sender, content=message.content, intent=message.intent,
        sources=sources if sources is not None else (message.sources or []), result_set=message.result_set,
        suggested_actions=message.suggested_actions or [], generation_method=message.generation_method,
        warnings=message.warnings or [], created_at=message.created_at)


def conversation_out(conversation: Conversation, messages: list[MessageOut] | None = None) -> ConversationOut:
    return ConversationOut(
        conversation_id=conversation.conversation_id, title=conversation.title, resume_id=conversation.resume_id,
        message_count=conversation.message_count or 0, last_message_at=conversation.last_message_at,
        created_at=conversation.created_at, updated_at=conversation.updated_at, messages=messages)


def messages_out(db: Session, user_id: int, messages: list[Message]) -> list[MessageOut]:
    annotated = service.annotate_sources(db, user_id, messages)
    return [message_out(m, annotated[m.message_id]) for m in messages]


@router.get("/capabilities", response_model=CapabilitiesOut)
def capabilities(current_user: User = Depends(get_current_user)):
    return CapabilitiesOut(
        intents=EXAMPLES,
        llm={**llm_status(), "assistant_disclosure": (AI_DISCLOSURE.format(provider=llm_status()["provider"])
                                                     if llm_status()["available"] else None)},
        limits={"message_chars": MAX_MESSAGE_CHARS, "messages_per_minute": rate_limit.LIMITS["minute"],
                "messages_per_day": rate_limit.LIMITS["day"], "ai_answers_per_hour": rate_limit.LIMITS["llm_hour"],
                "conversations": service.MAX_CONVERSATIONS, "messages_per_conversation": service.MAX_MESSAGES},
        notes=["Answers use only your own data and the internship knowledge base, with sources.",
               "The assistant never changes your data; suggested actions need your confirmation.",
               "AI rewording is off unless you turn it on for a message and consent; your name, contact "
               "details, address and PIN code are removed first, and unverifiable AI answers are discarded."])


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(request: ConversationCreate, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    try:
        conversation = service.create_conversation(db, current_user.user_id, request.resume_id, request.title)
    except service.AssistantError as exc:
        raise fail(exc)
    return conversation_out(conversation, [])


@router.get("/conversations", response_model=ConversationList)
def list_conversations(skip: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
                       db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total, items = service.list_conversations(db, current_user.user_id, skip, limit)
    return ConversationList(total=total, skip=skip, limit=limit, items=[conversation_out(c) for c in items])


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    try:
        conversation = service.owned_conversation(db, current_user.user_id, conversation_id)
    except service.AssistantError as exc:
        raise fail(exc)
    recent = service.list_messages(db, conversation, None, RECENT_MESSAGES)
    return conversation_out(conversation, messages_out(db, current_user.user_id, recent))


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(conversation_id: int, request: ConversationUpdate, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    try:
        conversation = service.update_conversation(db, current_user.user_id, conversation_id,
                                                   request.model_dump(), request.model_fields_set)
    except service.AssistantError as exc:
        raise fail(exc)
    return conversation_out(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response)
def delete_conversation(conversation_id: int, confirm: bool = False, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    if not confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Add ?confirm=true to delete this conversation and all its messages "
                                   "permanently.")
    try:
        service.delete_conversation(db, current_user.user_id, conversation_id)
    except service.AssistantError as exc:
        raise fail(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: int, before_id: int | None = Query(default=None, ge=1),
                  limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    try:
        conversation = service.owned_conversation(db, current_user.user_id, conversation_id)
    except service.AssistantError as exc:
        raise fail(exc)
    return messages_out(db, current_user.user_id, service.list_messages(db, conversation, before_id, limit))


@router.post("/conversations/{conversation_id}/messages", response_model=ExchangeOut,
             status_code=status.HTTP_201_CREATED)
def post_message(conversation_id: int, request: MessageCreate, response: Response, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    provider = None
    if request.use_llm:
        if not request.llm_consent:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="AI assistance requires llm_consent=true after showing the privacy "
                                       "disclosure from GET /assistant/capabilities.")
        provider = get_llm_provider()
        if provider is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="AI assistance is not configured on this server.")
    # Message limits are counted for every request; the hourly AI limit only when a provider call is made.
    try:
        rate_limit.hit(db.get_bind(), current_user.user_id, ("minute", "day"))
    except rate_limit.RateLimited as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Too many assistant requests. Try again in {exc.retry_after} seconds.",
                            headers={"Retry-After": str(exc.retry_after)}) from None
    try:
        user_message, assistant_message = service.post_message(db, current_user, conversation_id, request.message,
                                                               provider)
    except service.AssistantError as exc:
        raise fail(exc)
    except SQLAlchemyError:
        # Database problems: nothing is saved and no internals are exposed. (Programming errors are not
        # caught here; they surface as a generic 500 without details.)
        db.rollback()
        logger.warning("Assistant message failed because of a database error (conversation %s)", conversation_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="The assistant could not answer right now. Please try again.") from None
    annotated = service.annotate_sources(db, current_user.user_id, [assistant_message])
    return ExchangeOut(conversation_id=conversation_id, user_message=message_out(user_message, []),
                       assistant_message=message_out(assistant_message, annotated[assistant_message.message_id]))
