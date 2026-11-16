"""Resolve what a question refers to.

Follow-ups resolve against the EXACT ordered list an earlier assistant
message displayed (stored on that message as ``result_set``), not against
"the last thing mentioned":

* "the second one" -> item 2 of the most recent list shown in this
  conversation (a newer list replaces the older one, even if reordered);
* "it" / "that one" -> the current focus, else the only item of the last
  list; with several candidates the assistant asks which one;
* explicit references ("internship #12", "application #5") and company
  names are checked against the database and the student's own records.

The conversation context only stores pointers (message ids); if the message
holding a list was deleted (for example together with a deleted resume) the
list is gone and the assistant says so instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Conversation, Internship, Message
from backend.services.assistant.facts import ResultItem, ToolResult
from backend.services.assistant.intents import Understanding
from backend.services.compatibility import CITY_ALIASES
from backend.services.matching_agent import is_eligible

APPLICATION_INTENTS = {"application_status"}


@dataclass
class Resolution:
    internship_id: int | None = None
    application_id: int | None = None
    skill: str | None = None
    item: ResultItem | None = None          # the list item / focus that was used
    item_intent: str | None = None          # intent of the message that showed that item
    location: str | None = None
    company_applications: list[int] = field(default_factory=list)
    clarify: ToolResult | None = None
    notes: list[str] = field(default_factory=list)


def _items(result_set: dict[str, Any] | None) -> list[ResultItem]:
    if not result_set:
        return []
    return [ResultItem(i["type"], str(i["id"]), i.get("label", ""), i.get("extra") or {})
            for i in result_set.get("items", [])]


def load_list(db: Session, conversation: Conversation) -> tuple[Message | None, bool]:
    """(message holding the last displayed list, pointer_was_stale)."""
    pointer = (conversation.context or {}).get("last_result_message_id")
    if not pointer:
        return None, False
    message = db.scalar(select(Message).where(Message.message_id == pointer,
                                              Message.conversation_id == conversation.conversation_id))
    if message is None or not message.result_set:
        return None, True
    return message, False


def load_focus(db: Session, conversation: Conversation) -> tuple[ResultItem | None, str | None]:
    focus = (conversation.context or {}).get("focus")
    if not focus:
        return None, None
    message = db.scalar(select(Message).where(Message.message_id == focus.get("message_id"),
                                              Message.conversation_id == conversation.conversation_id))
    if message is None:
        return None, None
    label = next((item.label for item in _items(message.result_set)
                  if item.type == focus.get("type") and item.id == str(focus.get("id"))), "")
    if not label:
        label = (message.entities or {}).get("focus_label", "")
    return ResultItem(focus["type"], str(focus["id"]), label), message.intent


def clarify(question: str, options: list[ResultItem], kind: str | None = None) -> ToolResult:
    result = ToolResult(status="clarify")
    if options:
        result.intro = question + "\n" + "\n".join(f"{n}. {o.label}" for n, o in enumerate(options, start=1))
        result.result_kind = kind or options[0].type
        result.results = options
        result.clarify_options = options
        result.outro = "Reply with the number, for example \"the first one\"."
    else:
        result.intro = question
    return result


def apply_item(resolution: Resolution, item: ResultItem) -> None:
    resolution.item = item
    if item.type == "internship":
        resolution.internship_id = int(item.id)
    elif item.type == "application":
        resolution.application_id = int(item.id)
    elif item.type == "skill":
        resolution.skill = item.id


def find_location(db: Session, text: str) -> str | None:
    for alias, city in CITY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return city
    cities = {(loc or "").split(",")[0].strip() for loc in db.scalars(
        select(Internship.location).where(Internship.is_active.is_(True)).distinct()) if loc}
    for city in sorted(cities, key=len, reverse=True):
        if len(city) >= 3 and re.search(rf"\b{re.escape(city.lower())}\b", text):
            return city
    return None


def internships_by_company(db: Session, text: str) -> list[Internship]:
    found = []
    for internship in db.scalars(select(Internship).where(Internship.is_active.is_(True))):
        company = internship.company.lower().strip()
        if len(company) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(company)}(?![a-z0-9])", text) \
                and is_eligible(internship):
            found.append(internship)
    return found


def resolve(db: Session, user_id: int, conversation: Conversation, u: Understanding, intent: str) -> Resolution:
    from backend.services.assistant.tools import find_applications_by_company, internship_label

    resolution = Resolution(location=find_location(db, u.text) if intent == "internship_search" else None)
    if u.skills:
        resolution.skill = u.skills[0]

    # 1. Explicit ids always win.
    if u.application_id is not None:
        resolution.application_id = u.application_id
        return resolution
    if u.internship_id is not None:
        resolution.internship_id = u.internship_id
        return resolution

    # 2. Ordinals: the most recent displayed list.
    if u.ordinal is not None:
        message, stale = load_list(db, conversation)
        items = _items(message.result_set) if message else []
        if not items:
            resolution.clarify = clarify(
                "That earlier list is no longer available (it may have been deleted)." if stale else
                "I don't have a list to pick from yet. Ask me to find internships or show your applications first.",
                [])
            return resolution
        index = len(items) - 1 if u.ordinal == -1 else u.ordinal - 1
        if not 0 <= index < len(items):
            resolution.clarify = clarify(f"The last list had {len(items)} item(s). Which one do you mean?", items,
                                         message.result_set.get("kind"))
            return resolution
        apply_item(resolution, items[index])
        resolution.item_intent = message.intent
        return resolution

    # 3. Company names (the student's own applications, or public internships).
    if intent in APPLICATION_INTENTS:
        matches = find_applications_by_company(db, user_id, u.text)
        if matches:
            resolution.company_applications = [a.application_id for a in matches]
            if len(matches) == 1:
                resolution.application_id = matches[0].application_id
            return resolution
    elif intent not in ("internship_search", "help", "profile_summary", "dashboard", "reminders",
                        "upcoming_interviews", "top_matches"):
        companies = internships_by_company(db, u.text)
        if len(companies) == 1:
            resolution.internship_id = companies[0].internship_id
            return resolution
        if len(companies) > 1:
            options = [ResultItem("internship", str(i.internship_id), internship_label(i)) for i in companies[:5]]
            resolution.clarify = clarify("Several open internships match that company. Which one?", options)
            return resolution

    # 4. Pronouns: focus first, then a single-item list, otherwise ask.
    if u.referent or intent == "followup":
        focus, focus_intent = load_focus(db, conversation)
        if focus is not None:
            apply_item(resolution, focus)
            resolution.item_intent = focus_intent
            return resolution
        message, stale = load_list(db, conversation)
        items = _items(message.result_set) if message else []
        if len(items) == 1:
            apply_item(resolution, items[0])
            resolution.item_intent = message.intent
        elif len(items) > 1:
            resolution.clarify = clarify("Which one do you mean?", items, message.result_set.get("kind"))
        elif intent == "followup" or u.referent:
            resolution.clarify = clarify(
                "That earlier answer is no longer available." if stale else
                "I'm not sure what you're referring to. Could you name the internship, company or application?",
                [])
    return resolution
