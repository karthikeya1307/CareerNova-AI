"""Cover-letter generation (Phase 5).

Deterministic paragraphs are built only from the internship record and
the candidate's facts. The letter never claims a skill the candidate does
not have; it may say the candidate is *learning* a missing skill only
when that skill is marked ``in_progress`` in their Phase 4 skill-gap plan.

Optional LLM mode may rephrase the opening, fit, motivation and closing
paragraphs; each must cite facts and pass the fact checker, otherwise the
deterministic paragraph is kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

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
from backend.services.fact_base import CandidateFacts
from backend.services.fact_check import skill_mentions
from backend.services.internship_text import internship_skill_names
from backend.services.llm.base import LLMProvider

Tone = Literal["formal", "concise"]
LLM_PARAGRAPHS = ("opening", "fit", "motivation", "closing")


class InvalidEmphasisError(ValueError):
    """Requested emphasis skills are not on the resume."""


@dataclass(frozen=True)
class CoverLetterOptions:
    tone: Tone = "formal"
    emphasize_skills: tuple[str, ...] = ()


def _sentence(text: str) -> str:
    text = polish(text)
    return text if text.endswith((".", "!", "?")) else text + "."


def _role_phrase(title: str) -> str:
    """'Backend Developer Intern' -> 'the Backend Developer Intern position'."""
    lowered = title.strip().casefold()
    if lowered.endswith(("intern", "internship", "trainee")):
        return f"the {title} position"
    return f"the {title} internship"


def _possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


# Degree abbreviations recognised in a posting's education requirement and the candidate's degree.
# Dots are required for the two-letter ones (B.E./M.E.) so the English word "be" never matches.
DEGREE_PATTERNS = {
    "btech": r"\bb\.?\s?tech\b", "mtech": r"\bm\.?\s?tech\b", "be": r"\bb\.e\b", "me": r"\bm\.e\b",
    "bsc": r"\bb\.?\s?sc\b", "msc": r"\bm\.?\s?sc\b", "bca": r"\bbca\b", "mca": r"\bmca\b",
    "bcom": r"\bb\.?\s?com\b", "bba": r"\bbba\b", "mba": r"\bmba\b", "phd": r"\bph\.?\s?d\b",
}


def degree_codes(text: str | None) -> set[str]:
    value = (text or "").lower()
    return {code for code, pattern in DEGREE_PATTERNS.items() if re.search(pattern, value)}


def first_sentence(text: str | None, limit: int = 300) -> str:
    """The posting's first sentence (its main responsibility), trimmed to a readable length."""
    value = " ".join((text or "").split())
    if not value:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", value, maxsplit=1)[0]
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0] + "…"
    return sentence


def role_paragraph(candidate: CandidateFacts, internship: Internship) -> dict[str, Any] | None:
    """What the posting asks for, quoted from the internship record.

    The responsibilities are attributed to the posting ("Your posting says the role requires …"), so
    the letter never presents them as the candidate's own experience. They are quoted only when every
    skill they name is on the candidate's resume, so the letter never mentions a skill the candidate
    lacks. The education requirement is mentioned only when the candidate's degree matches it.
    """
    duties = first_sentence(internship.description)
    have = {s.casefold() for s in candidate.skills}
    sentences, fact_ids = [], []
    if duties and all(s.casefold() in have for s in skill_mentions(duties)):
        sentences.append(f"Your posting says the role requires the following: “{duties.rstrip('.')}.”")
        fact_ids.append("internship")
    requirement = (internship.min_education or "").strip()
    education = candidate.of_kind("education")
    if requirement and candidate.degree and education and degree_codes(requirement) & degree_codes(candidate.degree):
        sentences.append(f"My {candidate.degree} studies match the education it asks for ({requirement}).")
        fact_ids += ["internship", education[0].id]
    if not sentences:
        return None
    return {"key": "role", "text": " ".join(sentences), "fact_ids": sorted(set(fact_ids))}


def deterministic_cover_letter(
    candidate: CandidateFacts,
    internship: Internship,
    options: CoverLetterOptions,
    learning_skills: list[str],
) -> dict[str, Any]:
    have = {s.casefold(): s for s in candidate.skills}
    unknown = [s for s in options.emphasize_skills if s.casefold() not in have]
    if unknown:
        raise InvalidEmphasisError(f"These skills are not on your resume: {', '.join(unknown)}")

    company, title = internship.company, internship.title
    education = candidate.of_kind("education")
    paragraphs: list[dict[str, Any]] = [
        {"key": "greeting", "text": f"Dear Hiring Team at {company},", "fact_ids": []},
    ]

    opening = f"I am writing to apply for {_role_phrase(title)} at {company}."
    opening_ids: list[str] = []
    if candidate.degree and education:
        opening += f" I bring a background in {candidate.degree}."
        opening_ids = [education[0].id]
    paragraphs.append({"key": "opening", "text": opening, "fact_ids": opening_ids})

    role = role_paragraph(candidate, internship)
    if role is not None:
        paragraphs.append(role)

    required, preferred = matched_skills(candidate, internship)
    focus = [have[s.casefold()] for s in options.emphasize_skills] or [*required, *preferred][:5]
    if focus:
        fit = f"My skills in {oxford_join(focus)} match what this role asks for."
    else:
        fit = f"I am eager to apply my skills in {oxford_join(candidate.skills[:4])} to this role."
    fit_ids = ["skills"]
    examples = ranked_facts(candidate.of_kind("experience", "internship", "project"), internship)
    for fact in examples[: 1 if options.tone == "concise" else 2]:
        detail = fact.body[0] if fact.body and fact.body[0] != fact.title else ""
        fit += " " + _sentence(f"Relevant work includes {polish(fact.title)}" + (f": {detail}" if detail else ""))
        fit_ids.append(fact.id)
    paragraphs.append({"key": "fit", "text": fit, "fact_ids": fit_ids})

    if learning_skills:
        paragraphs.append({
            "key": "learning",
            "text": f"I am currently learning {oxford_join(learning_skills)} to strengthen my fit for this role.",
            "fact_ids": ["skill_gap_plan"],
        })

    if options.tone == "formal":
        motivation = (f"I am motivated by the opportunity to contribute to {_possessive(company)} work in "
                      f"{internship.domain}." if internship.domain
                      else f"I am motivated by the opportunity to contribute to {company}.")
        paragraphs.append({"key": "motivation", "text": motivation, "fact_ids": []})

    paragraphs.append({
        "key": "closing",
        "text": "Thank you for considering my application. I would welcome the opportunity "
                "to discuss how I can contribute to your team.",
        "fact_ids": [],
    })

    return {
        "type": "cover_letter",
        "header": {k: candidate.contact.get(k) for k in ("name", "email", "phone", "location")},
        "recipient": {"company": company, "title": title},
        "paragraphs": paragraphs,
        "signoff": "Sincerely,",
        "signature": candidate.contact.get("name"),
    }


COVER_SYSTEM = COMMON_RULES + (
    ' Return {"paragraphs": [{"key": "opening"|"fit"|"motivation"|"closing", '
    '"text": str, "fact_ids": [str]}]}. Write a warm, specific cover letter for the internship. '
    'Cite "skills" when referring to the candidate skills list. The closing and motivation may '
    'cite "internship" when they refer only to the internship.'
)


def generate_cover_letter(
    candidate: CandidateFacts,
    internship: Internship,
    options: CoverLetterOptions,
    learning_skills: list[str],
    provider: LLMProvider | None,
) -> tuple[dict[str, Any], FactCheckLog]:
    content = deterministic_cover_letter(candidate, internship, options, learning_skills)
    log = FactCheckLog()
    if provider is None:
        return content, log

    relevant = ranked_facts(candidate.of_kind("experience", "internship", "project"), internship)[:3]
    required, preferred = matched_skills(candidate, internship)
    payload = {
        "internship": internship_context(internship),
        "tone": options.tone,
        "candidate": {
            "skills": candidate.skills,
            "matched_skills": [*required, *preferred],
            "degree": candidate.degree,
            "facts": [{"id": f.id, "kind": f.kind, "text": f.text}
                      for f in [*candidate.of_kind("summary"), *candidate.of_kind("education")[:1], *relevant]],
        },
    }
    result = call_llm(provider, COVER_SYSTEM, payload, candidate, log)
    if result is None:
        return content, log

    # "skills" and "internship" are pseudo-facts the model may cite.
    from backend.services.fact_base import Fact
    extended = CandidateFacts(candidate.resume_id, candidate.contact,
                              [*candidate.facts,
                               Fact("skills", "skills", ", ".join(candidate.skills)),
                               Fact("internship", "internship_record", " ".join(context_texts(internship)))],
                              candidate.skills, candidate.degree)

    by_key = {p["key"]: p for p in content["paragraphs"]}
    for item in result.get("paragraphs") or []:
        if not isinstance(item, dict) or item.get("key") not in LLM_PARAGRAPHS or item["key"] not in by_key:
            continue
        text = validate_llm_statement(log, f"paragraph '{item['key']}'", item.get("text"),
                                      item.get("fact_ids"), extended, context_texts(internship))
        if text:
            by_key[item["key"]]["text"] = text
            by_key[item["key"]]["fact_ids"] = item["fact_ids"]

    return content, log


def learning_skills_for(db, resume_id: int, internship: Internship) -> list[str]:
    """Missing internship skills the student marked in_progress (Phase 4)."""
    from sqlalchemy import select

    from backend.models import SkillGapRecommendation

    required, preferred = internship_skill_names(internship)
    wanted = {s.casefold(): s for s in [*required, *preferred]}
    names = [rec.skill.name for rec in db.scalars(
        select(SkillGapRecommendation).where(
            SkillGapRecommendation.resume_id == resume_id,
            SkillGapRecommendation.status == "in_progress",
        )
    )]
    return sorted({wanted[n.casefold()] for n in names if n.casefold() in wanted})
