"""Persistence, editing and version history for generated documents."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models import GeneratedDocument, GeneratedDocumentVersion, Resume
from backend.services.document_common import context_texts
from backend.services.document_renderer import render_text
from backend.services.fact_base import CandidateFacts, Fact, NoExtractionError, build_fact_base
from backend.services.fact_check import check_statement, skill_mentions


def add_version(
    db: Session,
    document: GeneratedDocument,
    content_json: dict[str, Any],
    source: str,
    fact_check: dict[str, Any] | None,
) -> GeneratedDocumentVersion:
    """Make ``content_json`` the current content and record a new version."""
    next_version = max((v.version for v in document.versions), default=0) + 1
    text = render_text(content_json)

    document.content_json = content_json
    document.content = text
    document.fact_check = fact_check
    document.current_version = next_version

    version = GeneratedDocumentVersion(
        version=next_version, content=text, content_json=content_json,
        source=source, fact_check=fact_check,
    )
    document.versions.append(version)
    return version


def _texts_with_locations(content: dict[str, Any]) -> list[tuple[str, str]]:
    if content.get("type") == "resume":
        return [
            (f"{section['title']} / {item.get('heading') or 'line'}", line)
            for section in content.get("sections", [])
            for item in section.get("items", [])
            for line in ([item["heading"]] if item.get("heading") else []) + item.get("lines", [])
        ]
    return [(f"paragraph '{p['key']}'", p["text"]) for p in content.get("paragraphs", [])]


def check_edited_content(
    db: Session, document: GeneratedDocument, content: dict[str, Any]
) -> dict[str, Any]:
    """Fact-check student-edited content against the whole fact base.

    Edits are always saved; problems are returned as warnings.
    """
    resume = db.get(Resume, document.resume_id) if document.resume_id else None
    try:
        candidate: CandidateFacts | None = build_fact_base(db, resume) if resume else None
    except NoExtractionError:
        candidate = None

    if candidate is None:
        return {"checked_statements": 0, "rejected_statements": [],
                "warnings": [{"code": "source_unavailable",
                              "detail": "The source resume is no longer available, so edits "
                                        "could not be checked against it."}],
                "llm": {"used": False, "accepted": 0, "rejected": 0}}

    internship = document.internship
    context = context_texts(internship) if internship else []
    pseudo = [Fact("skills", "skills", ", ".join(candidate.skills))]
    all_facts = {**candidate.by_id, **{f.id: f for f in pseudo}}
    all_ids = list(all_facts)

    warnings, checked = [], 0
    for location, text in _texts_with_locations(content):
        checked += 1
        problems = check_statement(text, all_ids, all_facts, candidate.skills, context)
        if content.get("type") == "cover_letter":
            # A letter may name internship skills in "currently learning" or
            # requirement sentences; flag only skills claimed outside those.
            lowered = text.casefold()
            if "learning" in lowered or "requires" in lowered:
                problems = [p for p in problems if p["code"] != "unsupported_skill"]
        for problem in problems:
            warnings.append({"code": problem["code"], "detail": f"{location}: {problem['detail']}"})

    return {"checked_statements": checked, "rejected_statements": [], "warnings": warnings,
            "llm": {"used": False, "accepted": 0, "rejected": 0}}


def warning_count(fact_check: dict[str, Any] | None) -> int:
    if not fact_check:
        return 0
    return len(fact_check.get("warnings", [])) + len(fact_check.get("rejected_statements", []))


__all__ = ["add_version", "check_edited_content", "warning_count", "skill_mentions"]
