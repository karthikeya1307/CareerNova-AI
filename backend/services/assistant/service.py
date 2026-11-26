"""Conversations and message handling for the career assistant (Phase 8).

One message = one transaction: the conversation row is locked (so two
messages in the same conversation cannot interleave their context updates),
the question is understood and resolved, facts are gathered, the answer is
rendered (and optionally reworded by the AI and verified), both messages
and the new context pointers are written, and everything commits once.
"""

from __future__ import annotations

import re

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
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
from backend.services.assistant import app_guide, doc_agent, prep_agent, product_help, tools
from backend.services.assistant.facts import ResultItem, ToolResult, action
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
    "product_help": "About CareerNova AI", app_guide.INTENT: "How CareerNova AI works",
    "document_qa": "Document Q&A",
    **prep_agent.TITLES,
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


ASSISTANTS = ("application", "interview")


def assistant_of(conversation: Conversation) -> str:
    """Which assistant a chat belongs to. Chats created before the split are Application Assistant chats."""
    kind = (conversation.context or {}).get("assistant")
    return kind if kind in ASSISTANTS else "application"


def attached_ids(conversation: Conversation) -> list[int]:
    return doc_agent.attached_ids(conversation)


def create_conversation(db: Session, user_id: int, resume_id: int | None, title: str | None,
                        assistant: str = "application") -> Conversation:
    if assistant not in ASSISTANTS:
        raise AssistantError("Unknown assistant.")
    count = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id))
    if count >= MAX_CONVERSATIONS:
        raise Conflict(f"You can keep at most {MAX_CONVERSATIONS} conversations. Delete some to start a new one.")
    conversation = Conversation(user_id=user_id, resume_id=owned_resume_id(db, user_id, resume_id), title=title,
                                # Application chats keep the original empty context (missing "assistant" = application), so the
                                # context still holds only pointers; interview chats are marked.
                                context={"assistant": assistant} if assistant != "application" else {},
                                message_count=0)
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


def list_conversations(db: Session, user_id: int, skip: int, limit: int,
                       assistant: str | None = None) -> tuple[int, list[Conversation]]:
    query = select(Conversation).where(Conversation.user_id == user_id)
    if assistant is not None:
        kind = Conversation.context["assistant"].as_string()
        query = query.where(kind == "interview") if assistant == "interview" else \
            query.where(or_(kind.is_(None), kind != "interview"))
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
        # Numbered items, headings ("## ..."), bold labels and pre-formatted bullets are kept as they are.
        keep = fact.text[:1].isdigit() or fact.text.startswith(("#", "-", " ", "**"))
        lines.append(fact.text if keep else f"- {fact.text}")
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


# Intents per assistant (see post_message).
PREP_ONLY_INTENTS = {"resume_analysis", "role_recommendation", "role_fit", "strengths", "weaknesses", "role_select",
                     "technical_questions", "hr_questions", "answer_guidance", "prep_roadmap", "mock_interview"}
INTERVIEW_DATA_INTENTS = {"interview_prep", "skill_gap", "learning_plan", "top_matches", "match_explain",
                          "profile_summary", "internship_detail", "followup"}
APPLICATION_ONLY_INTENTS = {"application_status", "upcoming_interviews", "reminders", "dashboard", "document_help",
                            "internship_search", "help"}
ASSISTANT_PAGES = {"application": "/assistant", "interview": "/interview-assistant"}
SHARED_DATA_INTENTS = {"interview_prep", "skill_gap", "learning_plan"}   # answered by both assistants
PREP_WORDING = re.compile(r"\b(?:interview\w*|prep|prepar\w*|roadmap|mock|hr)\b", re.I)


def stays_in_application(text: str, intent: str) -> bool:
    """A generic learning-plan / skill-gap request ("give me a learning plan", "what should I learn to become X?") was
    always answered by the Application Assistant, so it stays there. Anything worded as interview preparation
    (HR/technical questions, mock interview, preparation roadmap) goes to the Interview Preparation Assistant."""
    return intent in ("learning_plan", "skill_gap") and not PREP_WORDING.search(text)


def redirect_result(target: str) -> ToolResult:
    """A question that belongs to the other assistant: say so and offer the way there (no answer is guessed)."""
    if target == "interview":
        result = ToolResult(intro=(
            "That's a job for the Interview Preparation Assistant. It uses your resume to recommend roles, generate "
            "technical and HR questions with answer guidance, build a preparation roadmap, run mock interviews and "
            "answer questions about your study documents."))
        result.actions.append(action("Open the Interview Preparation Assistant", "GET", ASSISTANT_PAGES["interview"],
                                     requires_confirmation=False))
    else:
        result = ToolResult(intro=(
            "I'm the Interview Preparation Assistant, so I focus on getting you ready for interviews. Questions about "
            "using CareerNova AI, your applications, reminders or documents are answered by the Application Assistant."))
        result.actions.append(action("Open the Application Assistant", "GET", ASSISTANT_PAGES["application"],
                                     requires_confirmation=False))
    return result


def interview_scope_result() -> ToolResult:
    return ToolResult(status="empty", intro=(
        "I can only help with interview preparation. Try: \"Which roles are suitable for my resume?\", \"Prepare me "
        "for Data Analyst\", \"Generate technical questions\", \"Generate HR questions\", \"How do I answer question "
        "1?\", \"Create my preparation roadmap\", \"Start a mock interview\" - or upload a study document and ask "
        "about it."))


def post_message(db: Session, user: User, conversation_id: int, text: str, provider=None) -> tuple[Message, Message]:
    """Answer one question. ``provider`` is set only when the AI was requested WITH consent."""
    from backend.services.assistant.llm_rewrite import CountingProvider, privacy_profile, rewrite

    conversation = owned_conversation(db, user.user_id, conversation_id, lock=True)
    if conversation.message_count + 2 > MAX_MESSAGES:
        raise Conflict(f"This conversation has reached {MAX_MESSAGES} messages. Start a new conversation.")

    u = understand(text, semantic=default_semantic_intent())
    kind = assistant_of(conversation)
    prep = product = guide = None
    if kind == "interview":
        # Interview Preparation Assistant: attached study documents first (document Q&A), then the
        # preparation agent (resume -> roles -> questions -> guidance -> roadmap), then the career-data
        # tools that matter for interviews. Everything else is pointed to the Application Assistant.
        counting_doc = CountingProvider(provider, db.get_bind(), user.user_id) if provider is not None else None
        doc = doc_agent.route(db, user, conversation, text, counting_doc)
        if doc is not None:
            return _store_document_answer(db, conversation, text, u, doc[0], doc[1])
        prep = prep_agent.route(db, user, conversation, text)
        if prep is not None:
            intent, result = prep.intent, prep.result
        elif u.intent in APPLICATION_ONLY_INTENTS or (product_help.looks_like_product_question(text)
                                                       and u.intent not in SHARED_DATA_INTENTS):
            # "How do I upload my resume?" is about using the app, even though it mentions "my resume".
            intent, result = "assistant_redirect", redirect_result("application")
        elif u.intent in INTERVIEW_DATA_INTENTS:
            intent, result = answer(db, user, conversation, u)
        else:
            intent, result = "out_of_scope", interview_scope_result()
    else:
        # Application Assistant (unchanged scope): the product guide and the student's own data tools.
        # Interview-preparation requests are pointed to the Interview Preparation Assistant.
        # Workflow questions ("How does this app work?", "How can I prepare for interviews?") get step-by-step
        # guidance first; for interviews it explains how to use the separate Interview Preparation Assistant.
        guide = app_guide.route(db, user, conversation, text)
        if guide is not None:
            intent, result = app_guide.INTENT, guide[1]
        elif prep_agent.detect(text) in PREP_ONLY_INTENTS and not stays_in_application(text, u.intent):
            intent, result = "assistant_redirect", redirect_result("interview")
        else:
            product = product_help.route(db, conversation, text, u.intent, u.ordinal, u.referent)
            if product is not None:
                intent, result = product.intent, product.result
            else:
                intent, result = answer(db, user, conversation, u)
    content, sources = render(result), result.sources()
    method, provider_name, model, fact_check = "deterministic", None, None, None
    warnings = list(result.warnings)

    if provider is not None and guide is not None:
        warnings.append({"code": "llm_not_applicable",
                         "detail": "Step-by-step guidance is built from the product guide and your own progress, so "
                                   "it is shown as it is (no AI rewording)."})
    elif provider is not None and prep is not None:
        warnings.append({"code": "llm_not_applicable",
                         "detail": "Preparation answers are built from your resume and curated interview guides, so "
                                   "they are shown as they are (no AI rewording)."})
    elif provider is not None and product is not None:
        if intent == "product_help" and result.status == "ok" and result.facts:
            from backend.services.llm_privacy import personal_details

            counting = CountingProvider(provider, db.get_bind(), user.user_id)
            history = product_help.product_history(db, conversation)
            personal = personal_details(privacy_profile(db, user, None))
            ai_result, fact_check = product_help.llm_answer(counting, text, history, product.hits, personal,
                                                                product.threshold)
            fact_check["provider_calls"] = counting.calls
            if ai_result is not None:
                content, sources, method = ai_result.facts[0].text, ai_result.sources(), "llm"   # prose answer
                provider_name, model = provider.name, provider.model
            elif counting.limited is not None:
                warnings.append({"code": "ai_rate_limited",
                                 "detail": f"The hourly limit for AI answers was reached; try again in "
                                           f"{counting.limited.retry_after} seconds. The standard answer is shown.",
                                 "retry_after": counting.limited.retry_after})
            else:
                warnings += fact_check.get("warnings") or []
            if ai_result is None and counting.limited is None:
                warnings.append({"code": "llm_unverified" if fact_check.get("llm_used") else "llm_unavailable",
                                 "detail": "The AI answer could not be verified against the product guide, so the "
                                           "standard answer is shown." if fact_check.get("llm_used") else
                                           "AI assistance was not available, so the standard answer is shown."})
                warnings = list({w["code"]: w for w in warnings}.values())
        else:
            warnings.append({"code": "llm_not_applicable",
                             "detail": "This answer has no guide content to reword, so the standard answer is shown."})
    elif provider is not None:
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
        entities=({"product_query": product.query[:1000]} if product is not None and intent == "product_help"
                  else {"guide_topic": guide[0]} if guide is not None
                  else {"focus_label": focus.label} if focus else None),
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
    # Conversational memory for product questions: a pointer to the last product answer (never its text).
    if product is not None and intent == "product_help":
        context["product"] = {"message_id": assistant_message.message_id}
    else:
        context.pop("product", None)
    if prep is not None:
        for key, value in prep.context.items():
            if value is None:
                context.pop(key, None)
            else:
                context[key] = value
    elif context.get("prep_awaiting_role"):
        context.pop("prep_awaiting_role", None)      # a different question ends the role choice
    conversation.context = context
    conversation.message_count = (conversation.message_count or 0) + 2
    conversation.last_message_at = now
    if not conversation.title:
        conversation.title = TITLES.get(intent, "Career chat")
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return user_message, assistant_message


def _store_document_answer(db: Session, conversation: Conversation, text: str, u: Understanding,
                           reply: "doc_agent.DocReply", documents) -> tuple[Message, Message]:
    now = utcnow()
    ids = [d.document_id for d in documents]
    user_message = Message(conversation_id=conversation.conversation_id, sender="user", content=text,
                           intent="document_qa", entities={**u.as_dict(), "study_document_ids": ids})
    db.add(user_message)
    assistant_message = Message(
        conversation_id=conversation.conversation_id, sender="assistant", content=reply.content, sources=reply.sources,
        intent="document_qa", entities={"study_document_ids": ids, "task": reply.task, "found": reply.found},
        generation_method=reply.method, llm_provider=reply.provider, llm_model=reply.model,
        fact_check=reply.llm_log, warnings=reply.warnings or None)
    db.add(assistant_message)
    db.flush()
    context = dict(conversation.context or {})
    if reply.task == "answer" and reply.found:
        context["doc_last_query"] = text[:500]
    conversation.context = context
    conversation.message_count = (conversation.message_count or 0) + 2
    conversation.last_message_at = now
    if not conversation.title:
        conversation.title = (f"Q&A: {documents[0].filename}" if len(documents) == 1
                              else f"Q&A: {len(documents)} documents")[:255]
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return user_message, assistant_message


def attach_study_documents(db: Session, user_id: int, conversation_id: int, document_ids: list[int]) -> Conversation:
    """Set the study documents this chat answers from ([] detaches them). Interview chats only."""
    from backend.services import study_documents

    conversation = owned_conversation(db, user_id, conversation_id, lock=True)
    if assistant_of(conversation) != "interview":
        raise Conflict("Study documents are used by the Interview Preparation Assistant. Open it to ask about documents.")
    ids = list(dict.fromkeys(int(i) for i in document_ids))
    if len(ids) > doc_agent.MAX_ATTACHED:
        raise AssistantError(f"Attach at most {doc_agent.MAX_ATTACHED} documents to one chat.")
    for document_id in ids:
        if study_documents.owned(db, user_id, document_id) is None:
            raise NotFound("Document not found")
    context = dict(conversation.context or {})
    context.pop("study_document_id", None)
    if ids:
        context["study_document_ids"] = ids
    else:
        context.pop("study_document_ids", None)
    context.pop("doc_last_query", None)
    conversation.context = context
    db.commit()
    db.refresh(conversation)
    return conversation


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
    if kind == "study_document":
        from backend.models import StudyDocument
        documents = {int(i.split(":")[0]) for i in ids if i.split(":")[0].isdigit()}
        alive = {str(d) for d in db.scalars(select(StudyDocument.document_id).where(
            StudyDocument.document_id.in_(documents), StudyDocument.user_id == user_id))}
        return {i for i in ids if i.split(":")[0] in alive}
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
