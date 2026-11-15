"""Internship-specific, ATS-friendly resume customization (Phase 5).

Deterministic mode (default): selects, orders and lightly tidies the
candidate's own facts for the internship. Nothing is added.

Optional LLM mode: the provider may rephrase the summary and the bullets
of selected entries. Every statement must cite fact ids and pass the fact
checker; anything unsupported is replaced by the deterministic text and
recorded in the fact-check log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.models import Internship
from backend.services.document_common import (
    COMMON_RULES,
    FactCheckLog,
    call_llm,
    context_texts,
    internship_context,
    matched_skills,
    oxford_join,
    polish,
    ranked_facts,
    validate_llm_statement,
)
from backend.services.fact_base import CandidateFacts, Fact
from backend.services.llm.base import LLMProvider


@dataclass(frozen=True)
class ResumeOptions:
    max_skills: int = 15
    max_projects: int = 3
    max_experience: int = 4
    max_bullets: int = 4


def _header(candidate: CandidateFacts, internship: Internship) -> dict[str, Any]:
    return {
        **{k: candidate.contact.get(k) for k in ("name", "email", "phone", "location", "linkedin", "github")},
        "target": f"{internship.title} at {internship.company}",
    }


def _item(fact: Fact, max_bullets: int, with_heading: bool = True) -> dict[str, Any]:
    if with_heading and len(fact.lines) > 1:
        return {"heading": polish(fact.title), "lines": [polish(l) for l in fact.body[:max_bullets]],
                "fact_ids": [fact.id]}
    return {"heading": None, "lines": [polish(l) for l in fact.lines[:max_bullets]], "fact_ids": [fact.id]}


def ordered_skills(candidate: CandidateFacts, internship: Internship, limit: int) -> list[str]:
    required, preferred = matched_skills(candidate, internship)
    seen, ordered = set(), []
    for skill in [*required, *preferred, *candidate.skills]:
        if skill.casefold() not in seen:
            seen.add(skill.casefold())
            ordered.append(skill)
    return ordered[:limit]


def deterministic_resume(
    candidate: CandidateFacts, internship: Internship, options: ResumeOptions
) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []

    summary = candidate.of_kind("summary")
    if summary:
        sentences = [s.strip() for s in summary[0].text.replace("\n", " ").split(". ") if s.strip()]
        text = ". ".join(sentences[:2]).rstrip(".") + "."
        sections.append({"key": "summary", "title": "Summary",
                         "items": [{"heading": None, "lines": [polish(text)], "fact_ids": [summary[0].id]}]})
    elif candidate.degree:
        education = candidate.of_kind("education")
        top = ordered_skills(candidate, internship, 4)
        text = f"{candidate.degree} student" + (f" with skills in {oxford_join(top)}." if top else ".")
        sections.append({"key": "summary", "title": "Summary",
                         "items": [{"heading": None, "lines": [text],
                                    "fact_ids": [education[0].id] if education else []}]})

    skills = ordered_skills(candidate, internship, options.max_skills)
    if skills:
        sections.append({"key": "skills", "title": "Skills",
                         "items": [{"heading": None, "lines": [", ".join(skills)], "fact_ids": ["skills"]}]})

    experience = ranked_facts(candidate.of_kind("experience", "internship"), internship)[: options.max_experience]
    if experience:
        sections.append({"key": "experience", "title": "Experience",
                         "items": [_item(f, options.max_bullets) for f in experience]})

    projects = ranked_facts(candidate.of_kind("project"), internship)[: options.max_projects]
    if projects:
        sections.append({"key": "projects", "title": "Projects",
                         "items": [_item(f, options.max_bullets) for f in projects]})

    resume_education = [f for f in candidate.of_kind("education") if f.id.startswith("edu-")]
    education = resume_education or candidate.of_kind("education")
    if education:
        sections.append({"key": "education", "title": "Education",
                         "items": [_item(f, options.max_bullets, with_heading=False) for f in education]})

    for key, title, kind in (("certifications", "Certifications", "certification"),
                             ("achievements", "Achievements", "achievement"),
                             ("languages", "Languages", "language")):
        facts = candidate.of_kind(kind)
        if facts:
            sections.append({"key": key, "title": title, "items": [
                {"heading": None, "lines": [polish(f.text)], "fact_ids": [f.id]} for f in facts]})

    return {"type": "resume", "header": _header(candidate, internship), "sections": sections}


RESUME_SYSTEM = COMMON_RULES + (
    ' Return {"summary": {"text": str, "fact_ids": [str]}, '
    '"bullets": [{"fact_id": str, "text": str}]}. '
    "Rewrite the summary to fit the internship in at most two sentences. "
    "Rewrite each entry's description lines as concise, achievement-oriented bullets that cite "
    "exactly one fact_id each, keeping every detail factual."
)


def customize_resume(
    candidate: CandidateFacts,
    internship: Internship,
    options: ResumeOptions,
    provider: LLMProvider | None,
) -> tuple[dict[str, Any], FactCheckLog]:
    content = deterministic_resume(candidate, internship, options)
    log = FactCheckLog()
    if provider is None:
        return content, log

    sections = {s["key"]: s for s in content["sections"]}
    selected_ids = [item["fact_ids"][0] for key in ("experience", "projects")
                    for item in sections.get(key, {}).get("items", [])]
    summary_fact = candidate.of_kind("summary")

    payload = {
        "internship": internship_context(internship),
        "candidate": {
            "skills": candidate.skills,
            "degree": candidate.degree,
            "summary": {"id": summary_fact[0].id, "text": summary_fact[0].text} if summary_fact else None,
            "entries": [{"id": fid, "kind": candidate.by_id[fid].kind, "text": candidate.by_id[fid].text}
                        for fid in selected_ids],
        },
        "max_bullets_per_entry": options.max_bullets,
    }
    result = call_llm(provider, RESUME_SYSTEM, payload, candidate, log)
    if result is None:
        return content, log

    summary = result.get("summary")
    if isinstance(summary, dict) and "summary" in sections:
        text = validate_llm_statement(log, "summary", summary.get("text"), summary.get("fact_ids"),
                                      candidate, context_texts(internship))
        if text:
            sections["summary"]["items"][0] = {"heading": None, "lines": [text],
                                               "fact_ids": summary["fact_ids"]}

    accepted: dict[str, list[str]] = {}
    for index, bullet in enumerate(result.get("bullets") or []):
        if not isinstance(bullet, dict):
            continue
        fact_id = bullet.get("fact_id")
        location = f"bullet {index + 1} ({fact_id})"
        if fact_id not in selected_ids:
            log.checked += 1
            log.rejected.append({"location": location, "text": str(bullet.get("text"))[:200],
                                 "problems": [{"code": "unknown_fact",
                                               "detail": f"Cites '{fact_id}', which is not a selected entry."}]})
            continue
        text = validate_llm_statement(log, location, bullet.get("text"), [fact_id], candidate, [])
        if text:
            accepted.setdefault(fact_id, []).append(text)

    for key in ("experience", "projects"):
        for item in sections.get(key, {}).get("items", []):
            fact_id = item["fact_ids"][0]
            if accepted.get(fact_id):
                item["lines"] = accepted[fact_id][: options.max_bullets]

    return content, log
