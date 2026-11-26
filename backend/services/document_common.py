"""Shared helpers for resume and cover-letter generation (Phase 5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.models import Internship
from backend.services.fact_base import CandidateFacts, Fact
from backend.services.fact_check import check_statement, skill_mentions
from backend.services.internship_text import internship_skill_names
from backend.services.llm.base import LLMError, LLMProvider, assert_no_contact

MAX_LLM_TEXT = 600


def polish(line: str) -> str:
    """Light, meaning-preserving tidy-up: whitespace, bullet marks, capital."""
    line = re.sub(r"\s+", " ", line.strip().lstrip("•▪*-–— ").strip())
    line = line.rstrip(";,")
    return line[:1].upper() + line[1:] if line else line


def fact_relevance(fact: Fact, internship: Internship) -> int:
    required, preferred = internship_skill_names(internship)
    mentioned = {s.casefold() for s in skill_mentions(fact.text)}
    return (
        2 * sum(s.casefold() in mentioned for s in required)
        + sum(s.casefold() in mentioned for s in preferred)
    )


def ranked_facts(facts: list[Fact], internship: Internship) -> list[Fact]:
    order = {f.id: i for i, f in enumerate(facts)}
    return sorted(facts, key=lambda f: (-fact_relevance(f, internship), order[f.id]))


def matched_skills(candidate: CandidateFacts, internship: Internship) -> tuple[list[str], list[str]]:
    have = {s.casefold() for s in candidate.skills}
    required, preferred = internship_skill_names(internship)
    return ([s for s in required if s.casefold() in have],
            [s for s in preferred if s.casefold() in have])


def internship_context(internship: Internship) -> dict[str, Any]:
    required, preferred = internship_skill_names(internship)
    return {
        "title": internship.title,
        "company": internship.company,
        "domain": internship.domain,
        "required_skills": required,
        "preferred_skills": preferred,
        "description": (internship.description or "")[:1500],      # the role's responsibilities
        "eligibility": (internship.eligibility or "")[:1000],      # stated requirements, if any
        "min_education": internship.min_education,
        "location": internship.location,
        "work_mode": internship.work_mode,
    }


def context_texts(internship: Internship) -> list[str]:
    return [internship.title or "", internship.company or "", internship.domain or "",
            internship.description or "", internship.eligibility or "", internship.min_education or ""]


def oxford_join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


@dataclass
class FactCheckLog:
    checked: int = 0
    rejected: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    llm_used: bool = False
    llm_accepted: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked_statements": self.checked,
            "rejected_statements": self.rejected,
            "warnings": self.warnings,
            "llm": {"used": self.llm_used, "accepted": self.llm_accepted,
                    "rejected": len(self.rejected)},
        }


REMOVED_PLACEHOLDER = "[removed]"   # llm_privacy.REMOVED


def validate_llm_statement(
    log: FactCheckLog,
    location: str,
    text: Any,
    fact_ids: Any,
    candidate: CandidateFacts,
    extra_context: list[str],
) -> str | None:
    """Return the cleaned statement if supported, else record it and return None."""
    log.checked += 1
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_LLM_TEXT:
        log.rejected.append({"location": location, "text": str(text)[:200],
                             "problems": [{"code": "invalid_output", "detail": "Missing or too long."}]})
        return None
    if REMOVED_PLACEHOLDER in text:
        log.rejected.append({"location": location, "text": text[:200],
                             "problems": [{"code": "privacy_placeholder",
                                           "detail": "Statement repeats a removed personal detail."}]})
        return None
    if not isinstance(fact_ids, list) or not fact_ids or not all(isinstance(f, str) for f in fact_ids):
        log.rejected.append({"location": location, "text": text[:200],
                             "problems": [{"code": "no_citation", "detail": "Statement cites no facts."}]})
        return None
    problems = check_statement(text, fact_ids, candidate.by_id, candidate.skills, extra_context)
    if problems:
        log.rejected.append({"location": location, "text": text[:200], "problems": problems})
        return None
    log.llm_accepted += 1
    return polish(text)


def call_llm(
    provider: LLMProvider,
    system: str,
    payload: dict[str, Any],
    candidate: CandidateFacts,
    log: FactCheckLog,
) -> dict[str, Any] | None:
    """Send a privacy-checked payload; return parsed JSON or None on failure.

    1. The original Phase 5 check: a request containing an exact contact
       value (full name, e-mail, phone, links) is blocked, as before.
    2. Phase 6 hardening: every candidate string is then scrubbed with the
       shared scrubber (name parts, address, street numbers, PIN codes) and
       checked again; anything left blocks the request.
    """
    import json

    from backend.services.llm_privacy import (
        find_llm_payload_personal_data,
        personal_details,
        scrub_llm_payload,
    )

    leftover: list[str] = []
    try:
        assert_no_contact(payload, candidate.contact)
        details = personal_details(candidate)
        payload = scrub_llm_payload(payload, details)
        leftover = find_llm_payload_personal_data(payload, details)
        if leftover:
            raise LLMError("personal data detected")
    except LLMError:
        log.warnings.append({"code": "privacy_guard",
                             "detail": "Personal contact information was detected in the request, so "
                                       "nothing was sent. Deterministic content was used instead."
                                       + (f" Detected: {', '.join(leftover)}." if leftover else "")})
        return None
    try:
        result = provider.complete_json(system, json.dumps(payload, ensure_ascii=False))
    except LLMError as exc:
        log.warnings.append({"code": "llm_unavailable",
                             "detail": f"{exc} Deterministic content was used instead."})
        return None
    log.llm_used = True
    return result


COMMON_RULES = (
    "You rewrite job-application content. STRICT RULES: "
    "1) Use ONLY information in the provided candidate facts. "
    "2) Never add employers, institutions, project names, dates, numbers, metrics, "
    "skills, tools or achievements that are not in the cited facts. "
    "3) Every statement must cite the fact ids it is based on. "
    "4) Do not mention skills the candidate does not list, even if the internship requires them. "
    "5) Use plain professional English. Respond with a single JSON object only."
)
