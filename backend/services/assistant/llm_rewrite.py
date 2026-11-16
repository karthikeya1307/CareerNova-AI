"""Optional AI rewording of a deterministic answer (off by default, consent per message).

What is sent: the detected TOPIC (an intent name such as "internship_search")
and the answer's facts in their AI-safe form - nothing else. Not sent: the
student's question text, chat history, reminder titles, document titles,
external companies' names and job titles (free text the student typed, which
may name other people), notes, contact details or reminder descriptions.

The request still goes through Phase 5's ``call_llm`` (exact contact check,
hardened scrubbing of names, addresses, PIN codes, e-mails and phone numbers,
final re-check). The AI may only rephrase the facts; its answer is verified
claim by claim against the facts it was given (verify.py) and discarded in
favour of the deterministic answer if anything fails or is uncertain.

The hourly AI limit is counted at the moment the provider is actually called
(``CountingProvider``), with the same atomic counter as the message limits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.models import Resume, User
from backend.services.assistant import rate_limit
from backend.services.assistant.facts import ToolResult
from backend.services.assistant.verify import verify_answer
from backend.services.document_common import FactCheckLog, call_llm
from backend.services.fact_base import CandidateFacts, NoExtractionError, build_fact_base
from backend.services.llm.base import LLMError, LLMProvider

SYSTEM = (
    "You are a careful career assistant. Rephrase the provided FACTS as a short, friendly answer about the "
    "given TOPIC for a student. STRICT RULES: use ONLY the facts; never add skills, numbers, dates, companies, "
    "statuses, opinions or promises; keep a missing skill missing; every sentence must list the ids of the "
    "facts it is based on. Return JSON only: "
    '{"sentences": [{"text": "...", "fact_ids": ["F1"]}]} with at most 8 sentences.'
)

TOPICS = {
    "profile_summary": "the student's resume", "internship_search": "internship search results",
    "internship_detail": "an internship's details", "top_matches": "the student's top internship matches",
    "match_explain": "why an internship matches the student", "skill_gap": "the student's skill gaps",
    "learning_plan": "a learning plan", "document_help": "resume and cover-letter help",
    "interview_prep": "interview preparation", "application_status": "the student's applications",
    "upcoming_interviews": "upcoming interviews", "reminders": "pending reminders",
    "dashboard": "the student's application overview",
}


class CountingProvider:
    """Wraps the provider so the hourly AI limit is counted only when a call is really made."""

    def __init__(self, provider: LLMProvider, engine: Engine, user_id: int):
        self._provider, self._engine, self._user_id = provider, engine, user_id
        self.name, self.model = provider.name, provider.model
        self.calls = 0
        self.limited: rate_limit.RateLimited | None = None

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        try:
            rate_limit.hit(self._engine, self._user_id, ("llm_hour",))
        except rate_limit.RateLimited as exc:
            self.limited = exc
            raise LLMError(f"The hourly limit for AI answers was reached; try again in {exc.retry_after} "
                           "seconds.") from None
        self.calls += 1
        return self._provider.complete_json(system, user)


def privacy_profile(db: Session, user: User, resume: Resume | None) -> CandidateFacts:
    """Contact details to keep out of the request: the resume's AND the account's."""
    candidate = None
    if resume is not None:
        try:
            candidate = build_fact_base(db, resume)
        except NoExtractionError:
            candidate = None
    contact = dict(candidate.contact) if candidate else {}
    account_name = f"{user.first_name} {user.last_name}".strip()
    if not contact.get("name"):
        contact["name"] = account_name
    contact["account_name"] = account_name
    contact["account_email"] = user.email
    contact["account_phone"] = user.phone_number
    return CandidateFacts(resume.resume_id if resume else 0, contact, [], [],
                          address=candidate.address if candidate else None)


def rewrite(db: Session, provider: CountingProvider, user: User, resume: Resume | None, intent: str,
            result: ToolResult) -> tuple[str | None, list[dict[str, Any]], dict[str, Any]]:
    """Return (verified text or None, cited sources, fact-check record)."""
    shared = [fact.for_llm() for fact in result.facts]
    payload = {"topic": TOPICS.get(intent, "the student's question"),
               "facts": [{"id": f.id, "text": f.text} for f in shared]}

    log = FactCheckLog()
    response = call_llm(provider, SYSTEM, payload, privacy_profile(db, user, resume), log)
    record: dict[str, Any] = {"llm_used": log.llm_used, "warnings": log.warnings, "problems": []}
    if response is None:
        return None, [], record
    sentences, problems = verify_answer(response, shared)
    record["problems"] = problems
    record["sentences_checked"] = len(response.get("sentences", [])) if isinstance(response, dict) else 0
    if sentences is None:
        return None, [], record

    by_id = {f.id: f for f in shared}
    cited, seen = [], set()
    for sentence in sentences:
        for fact_id in sentence["fact_ids"]:
            for source in by_id[fact_id].sources:
                key = (source.type, source.id)
                if key not in seen:
                    seen.add(key)
                    cited.append(source.as_dict())
    return " ".join(s["text"] for s in sentences), cited, record
