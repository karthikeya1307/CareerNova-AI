"""Conversations and message handling for the career assistant (Phase 8).

One message = one transaction: the conversation row is locked (so two
messages in the same conversation cannot interleave their context updates),
the question is understood and resolved, facts are gathered, the answer is
rendered (and optionally reworded by the AI and verified), both messages
and the new context pointers are written, and everything commits once.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    Application,
    ApplicationInterview,
    ApplicationReminder,
    Conversation,
    GeneratedDocument,
    Internship,
    InterviewSession,
    MatchResult,
    Message,
    Resume,
    SavedInternship,
    SkillGapRecommendation,
    User,
)
from backend.services.assistant import tools
from backend.services.assistant.facts import ResultItem, ToolResult
from backend.services.assistant.intents import Understanding, default_semantic_intent, understand
from backend.services.assistant.resolver import Resolution, clarify, load_list, resolve

MAX_CONVERSATIONS = 200
MAX_MESSAGES = 500

TITLES = {
    "help": "Getting started", "profile_summary": "My profile", "internship_search": "Internship search",
    "internship_detail": "Internship details", "top_matches": "My matches", "match_explain": "Match explanation",
    "skill_gap": "Skill gaps", "learning_plan": "Learning plan", "document_help": "Resume and cover letter",
    "interview_prep": "Interview preparation", "application_status": "My applications",
    "upcoming_interviews": "Upcoming interviews", "reminders": "Reminders", "dashboard": "Application overview",
}


class AssistantError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(AssistantError):
    status_code = 404


class Conflict(AssistantError):
    status_code = 409


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Conversations
# ------------------------------------------------------------------

def owned_conversation(db: Session, user_id: int, conversation_id: int, *, lock: bool = False) -> Conversation:
    query = select(Conversation).where(Conversation.conversation_id == conversation_id,
                                       Conversation.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    conversation = db.scalar(query)
    if conversation is None:
        raise NotFound("Conversation not found")
    return conversation


def owned_resume_id(db: Session, user_id: int, resume_id: int | None) -> int | None:
    if resume_id is None:
        return None
    if db.scalar(select(Resume.resume_id).where(Resume.resume_id == resume_id, Resume.user_id == user_id)) is None:
        raise NotFound("Resume not found")
    return resume_id


def create_conversation(db: Session, user_id: int, resume_id: int | None, title: str | None) -> Conversation:
    count = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id))
    if count >= MAX_CONVERSATIONS:
        raise Conflict(f"You can keep at most {MAX_CONVERSATIONS} conversations. Delete some to start a new one.")
    conversation = Conversation(user_id=user_id, resume_id=owned_resume_id(db, user_id, resume_id), title=title,
                                context={}, message_count=0)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def update_conversation(db: Session, user_id: int, conversation_id: int, data: dict[str, Any],
                        provided: set[str]) -> Conversation:
    conversation = owned_conversation(db, user_id, conversation_id, lock=True)
    if "title" in provided:
        conversation.title = data.get("title")
    if "resume_id" in provided:
        conversation.resume_id = owned_resume_id(db, user_id, data.get("resume_id"))
        conversation.context = {**(conversation.context or {}), "focus": None}
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, user_id: int, conversation_id: int) -> None:
    conversation = owned_conversation(db, user_id, conversation_id, lock=True)
    db.delete(conversation)            # ON DELETE CASCADE removes every message
    db.commit()


def list_conversations(db: Session, user_id: int, skip: int, limit: int) -> tuple[int, list[Conversation]]:
    query = select(Conversation).where(Conversation.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = list(db.scalars(query.order_by(Conversation.updated_at.desc(), Conversation.conversation_id.desc())
                            .offset(skip).limit(limit)))
    return total, items


def list_messages(db: Session, conversation: Conversation, before_id: int | None, limit: int) -> list[Message]:
    query = select(Message).where(Message.conversation_id == conversation.conversation_id)
    if before_id is not None:
        query = query.where(Message.message_id < before_id)
    rows = list(db.scalars(query.order_by(Message.message_id.desc()).limit(limit)))
    return list(reversed(rows))


# ------------------------------------------------------------------
# Rendering (deterministic)
# ------------------------------------------------------------------

def render(result: ToolResult) -> str:
    lines = [result.intro] if result.intro else []
    for fact in result.facts:
        lines.append(fact.text if fact.text[:1].isdigit() else f"- {fact.text}")
    if result.outro:
        lines.append(result.outro)
    return "\n".join(lines).strip()


# ------------------------------------------------------------------
# Answering
# ------------------------------------------------------------------

def _which(resolution: Resolution, db: Session, conversation: Conversation, question: str,
           kind: str | None = None) -> ToolResult:
    message, _ = load_list(db, conversation)
    options = [ResultItem(i["type"], str(i["id"]), i.get("label", ""), i.get("extra") or {})
               for i in (message.result_set or {}).get("items", [])] if message else []
    if kind:
        options = [o for o in options if o.type == kind]
    return clarify(question, options)


def answer(db: Session, user: User, conversation: Conversation, u: Understanding) -> tuple[str, ToolResult]:
    """Pick the tool for the question and run it. Returns (final intent, result)."""
    intent = u.intent
    resolution = resolve(db, user.user_id, conversation, u, intent)
    if resolution.clarify is not None:
        return intent, resolution.clarify

    if intent == "followup":
        item, item_intent = resolution.item, resolution.item_intent
        if item is None:
            return "unknown", tools.help_result()
        if item.type == "application":
            intent = "application_status"
        elif item.type == "skill":
            intent = "learning_plan"
        elif item_intent in ("top_matches", "match_explain"):
            intent = "match_explain"
        elif item_intent in ("skill_gap", "document_help", "interview_prep"):
            intent = item_intent
        else:
            intent = "internship_detail"
    if intent == "internship_detail" and resolution.application_id is not None:
        intent = "application_status"

    uid = user.user_id
    resume_needed = intent in ("profile_summary", "top_matches", "match_explain", "skill_gap", "document_help",
                               "interview_prep")
    resume = tools.choose_resume(db, uid, conversation.resume_id) if resume_needed else None

    if intent == "help":
        return intent, tools.help_result()
    if intent == "profile_summary":
        return intent, tools.profile_summary(db, uid, resume)
    if intent == "internship_search":
        return intent, tools.internship_search(db, uid, u.search_terms, u.work_mode, resolution.location, u.text)
    if intent == "internship_detail":
        if resolution.internship_id is None:
            return intent, _which(resolution, db, conversation, "Which internship do you mean?", "internship")
        return intent, tools.internship_detail(db, uid, resolution.internship_id)
    if intent == "top_matches":
        return intent, tools.top_matches(db, uid, resume)
    if intent == "match_explain":
        if resolution.internship_id is None:
            return intent, _which(resolution, db, conversation,
                                  "Which internship should I explain? You can also ask \"show my top matches\".",
                                  "internship")
        return intent, tools.match_explain(db, uid, resume, resolution.internship_id)
    if intent == "skill_gap":
        return intent, tools.skill_gap(db, uid, resume, resolution.internship_id)
    if intent == "learning_plan":
        if not resolution.skill:
            return intent, _which(resolution, db, conversation, "Which skill would you like a plan for?", "skill")
        return intent, tools.learning_plan(db, uid, resolution.skill)
    if intent == "document_help":
        return intent, tools.document_help(db, uid, resume, resolution.internship_id)
    if intent == "interview_prep":
        return intent, tools.interview_prep(db, uid, resolution.skill, resolution.internship_id, resume)
    if intent == "application_status":
        if resolution.application_id is not None:
            return intent, tools.application_detail(db, uid, resolution.application_id)
        if len(resolution.company_applications) > 1:
            items = list(db.scalars(select(Application).where(
                Application.application_id.in_(resolution.company_applications))))
            options = [ResultItem("application", str(a.application_id), tools.application_label(a)) for a in items]
            return intent, clarify("You have several applications with that company. Which one?", options)
        return intent, tools.application_list(db, uid, u.statuses)
    if intent == "upcoming_interviews":
        return intent, tools.upcoming_interviews(db, uid)
    if intent == "reminders":
        return intent, tools.reminders(db, uid)
    if intent == "dashboard":
        return intent, tools.dashboard(db, uid)
    result = tools.help_result()
    result.intro = "I'm not sure I understood that. " + result.intro
    return "unknown", result


def post_message(db: Session, user: User, conversation_id: int, text: str, provider=None) -> tuple[Message, Message]:
    """Answer one question. ``provider`` is set only when the AI was requested WITH consent."""
    from backend.services.assistant.llm_rewrite import CountingProvider, rewrite

    conversation = owned_conversation(db, user.user_id, conversation_id, lock=True)
    if conversation.message_count + 2 > MAX_MESSAGES:
        raise Conflict(f"This conversation has reached {MAX_MESSAGES} messages. Start a new conversation.")

    u = understand(text, semantic=default_semantic_intent())
    intent, result = answer(db, user, conversation, u)
    content, sources = render(result), result.sources()
    method, provider_name, model, fact_check = "deterministic", None, None, None
    warnings = list(result.warnings)

    if provider is not None:
        if result.status == "ok" and result.facts:
            resume = (db.get(Resume, result.uses_resume_id) if result.uses_resume_id
                      else tools.choose_resume(db, user.user_id, conversation.resume_id))
            counting = CountingProvider(provider, db.get_bind(), user.user_id)
            ai_text, ai_sources, fact_check = rewrite(db, counting, user, resume, intent, result)
            fact_check["provider_calls"] = counting.calls
            if ai_text:
                content, sources, method = ai_text, ai_sources, "llm"
                provider_name, model = provider.name, provider.model
            elif counting.limited is not None:
                warnings.append({"code": "ai_rate_limited",
                                 "detail": f"The hourly limit for AI answers was reached; try again in "
                                           f"{counting.limited.retry_after} seconds. The standard answer is shown.",
                                 "retry_after": counting.limited.retry_after})
            else:
                warnings += fact_check.get("warnings") or []
                warnings.append({"code": "llm_unverified" if fact_check.get("llm_used") else "llm_unavailable",
                                 "detail": "The AI answer could not be verified against your data, so the standard "
                                           "answer is shown." if fact_check.get("llm_used") else
                                           "AI assistance was not available, so the standard answer is shown."})
        else:
            warnings.append({"code": "llm_not_applicable",
                             "detail": "This answer has no facts to reword, so the standard answer is shown."})

    now = utcnow()
    resume_link = result.uses_resume_id
    user_message = Message(conversation_id=conversation.conversation_id, sender="user", content=text,
                           resume_id=resume_link, intent=intent, entities=u.as_dict())
    db.add(user_message)
    focus = result.focus or (ResultItem(result.results[0].type, result.results[0].id, result.results[0].label)
                             if len(result.results) == 1 else None)
    assistant_message = Message(
        conversation_id=conversation.conversation_id, sender="assistant", content=content, sources=sources,
        resume_id=resume_link, intent=intent,
        entities={"focus_label": focus.label} if focus else None,
        result_set=({"kind": result.result_kind or result.results[0].type,
                     "items": [i.as_dict() for i in result.results]} if result.results else None),
        suggested_actions=result.actions or None, generation_method=method, llm_provider=provider_name,
        llm_model=model, fact_check=fact_check, warnings=warnings or None)
    db.add(assistant_message)
    db.flush()

    context = dict(conversation.context or {})
    if result.results:
        context["last_result_message_id"] = assistant_message.message_id
        context["focus"] = None
    if focus is not None:
        context["focus"] = {"type": focus.type, "id": focus.id, "message_id": assistant_message.message_id}
    conversation.context = context
    conversation.message_count = (conversation.message_count or 0) + 2
    conversation.last_message_at = now
    if not conversation.title:
        conversation.title = TITLES.get(intent, "Career chat")
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return user_message, assistant_message


# ------------------------------------------------------------------
# Source traceability on read
# ------------------------------------------------------------------

def _existing(db: Session, user_id: int, kind: str, ids: set[str]) -> set[str]:
    numeric = {int(i) for i in ids if str(i).isdigit()}
    if kind == "internship":
        return {str(i) for i in db.scalars(select(Internship.internship_id).where(
            Internship.internship_id.in_(numeric), Internship.is_active.is_(True)))}
    if kind == "application":
        return {str(i) for i in db.scalars(select(Application.application_id).where(
            Application.application_id.in_(numeric), Application.user_id == user_id,
            Application.deleted_at.is_(None)))}
    owned = {
        "match_result": (MatchResult.match_id, MatchResult.user_id),
        "skill_gap_recommendation": (SkillGapRecommendation.recommendation_id, SkillGapRecommendation.user_id),
        "document": (GeneratedDocument.document_id, GeneratedDocument.user_id),
        "interview_session": (InterviewSession.session_id, InterviewSession.user_id),
        "resume": (Resume.resume_id, Resume.user_id),
    }
    if kind in owned:
        column, owner = owned[kind]
        return {str(i) for i in db.scalars(select(column).where(column.in_(numeric), owner == user_id))}
    if kind == "resume_fact":
        resumes = {i.split(":")[0] for i in ids}
        alive = _existing(db, user_id, "resume", resumes)
        return {i for i in ids if i.split(":")[0] in alive}
    if kind == "bookmark":
        return {str(i) for i in db.scalars(select(SavedInternship.bookmark_id).where(
            SavedInternship.bookmark_id.in_(numeric), SavedInternship.user_id == user_id))}
    if kind in ("application_interview", "application_reminder"):
        model = ApplicationInterview if kind == "application_interview" else ApplicationReminder
        column = model.interview_id if kind == "application_interview" else model.reminder_id
        return {str(i) for i in db.scalars(select(column).join(Application).where(
            column.in_(numeric), Application.user_id == user_id, Application.deleted_at.is_(None)))}
    return set(ids)            # learning plans, question bank, dashboard, progress: informational


def annotate_sources(db: Session, user_id: int, messages: list[Message]) -> dict[int, list[dict[str, Any]]]:
    """Each source gets ``available``: False when the record was deleted, closed or trashed since."""
    wanted: dict[str, set[str]] = {}
    for message in messages:
        for source in message.sources or []:
            wanted.setdefault(source["type"], set()).add(str(source["id"]))
    alive = {kind: _existing(db, user_id, kind, ids) for kind, ids in wanted.items()}
    return {m.message_id: [{**s, "available": str(s["id"]) in alive.get(s["type"], set())}
                           for s in (m.sources or [])] for m in messages}
