"""Fact checking for generated or edited document text (Phase 5).

A statement is supported only if:
  * every technical skill it names is one of the candidate's skills;
  * every number it contains appears in the cited facts;
  * every capitalised name/term (not at the start of a sentence) appears in
    the cited facts, the internship record or the candidate's skills;
  * every cited fact ID exists.

LLM statements that fail are replaced by deterministic content. Student
edits are saved but the same checks produce visible warnings.

Known limitation: soft skills and ordinary words are not checked, and
ambiguous short words (e.g. "Go", "Excel", "C") count as skills only when
written exactly in their canonical form mid-sentence.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from backend.services.skill_normalizer import CATEGORY_OTHER, normalize_skill

AMBIGUOUS_SKILL_WORDS = {
    "c", "r", "go", "excel", "rest", "spring", "express", "node", "os", "swift",
    "agile", "monitoring", "networking", "statistics", "ml", "py", "js", "ts",
    "vue", "oracle", "redis", "keras", "flask", "dsa", "dl", "spring boot",
}
UNCHECKED_CATEGORIES = {"soft_skill", CATEGORY_OTHER}

COMMON_CAPITALISED = {
    "i", "i'm", "i've", "my", "me", "we", "our", "the", "a", "an", "in", "at", "for", "and",
    "dear", "team", "hiring", "sincerely", "regards", "thank", "you", "internship", "intern",
    "role", "summary", "skills", "experience", "projects", "education", "certifications",
    "achievements", "languages", "objective", "january", "february", "march", "april", "may",
    "june", "july", "august", "september", "october", "november", "december", "present",
    "currently", "relevant", "seeking", "for", "example",
}

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
CAPITAL_RE = re.compile(r"\b[A-Z][A-Za-z0-9&+#.'-]*[A-Za-z0-9+#]|\b[A-Z]\b")
TOKEN_RE = re.compile(r"[A-Za-z0-9+#./-]+")


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def skill_mentions(text: str) -> set[str]:
    """Canonical technical skills mentioned in text."""
    found: set[str] = set()
    for sentence in _sentences(text):
        words = TOKEN_RE.findall(sentence)
        for size in (3, 2, 1):
            for start in range(len(words) - size + 1):
                phrase = " ".join(words[start:start + size]).strip(".-/")
                if not phrase:
                    continue
                skill = normalize_skill(phrase)
                if skill is None or skill.category in UNCHECKED_CATEGORIES:
                    continue
                if phrase.casefold() in AMBIGUOUS_SKILL_WORDS or skill.name.casefold() in AMBIGUOUS_SKILL_WORDS:
                    # Ambiguous words count only when written exactly as the
                    # canonical name and not at the start of the sentence.
                    if phrase != skill.name or start == 0:
                        continue
                found.add(skill.name)
    return found


def _vocabulary(texts: Iterable[str]) -> set[str]:
    words: set[str] = set()
    for text in texts:
        for token in TOKEN_RE.findall(text or ""):
            words.add(token.casefold().strip(".-/"))
    return words


def check_statement(
    text: str,
    cited_fact_ids: list[str],
    facts_by_id: dict[str, Any],
    candidate_skills: Iterable[str],
    context_texts: Iterable[str] = (),
) -> list[dict[str, str]]:
    """Return a list of problems; an empty list means the statement is supported.

    ``context_texts`` are non-candidate sources the text may refer to
    (internship title, company, description).
    """
    problems: list[dict[str, str]] = []

    unknown_ids = [fid for fid in cited_fact_ids if fid not in facts_by_id]
    for fid in unknown_ids:
        problems.append({"code": "unknown_fact", "detail": f"Cites unknown fact '{fid}'."})
    cited_texts = [facts_by_id[fid].text for fid in cited_fact_ids if fid in facts_by_id]

    # Supported skills: the candidate's skills plus any skill named in the
    # cited facts themselves (e.g. "REST APIs" in their own summary).
    have = {s.casefold() for s in candidate_skills}
    have |= {s.casefold() for s in skill_mentions(" ".join(cited_texts))}
    for skill in sorted(skill_mentions(text)):
        if skill.casefold() not in have:
            problems.append({"code": "unsupported_skill",
                             "detail": f"Mentions {skill}, which is not one of your skills."})

    source_numbers = set(NUMBER_RE.findall(" ".join(cited_texts)))
    for number in NUMBER_RE.findall(text):
        if number not in source_numbers:
            problems.append({"code": "unsupported_number",
                             "detail": f"Contains the number {number}, which is not in the cited facts."})

    vocabulary = _vocabulary([*cited_texts, *context_texts, *candidate_skills]) | COMMON_CAPITALISED
    for sentence in _sentences(text):
        first = True
        for match in CAPITAL_RE.finditer(sentence):
            token = match.group(0)
            if first and match.start() <= 1:
                first = False
                continue
            first = False
            known = normalize_skill(token)
            if known is not None and known.category != CATEGORY_OTHER:
                continue  # skills are handled by the skill check above
            parts = [p.casefold().strip(".-/'") for p in TOKEN_RE.findall(token)]
            if parts and not all(p in vocabulary for p in parts if p):
                problems.append({"code": "unsupported_term",
                                 "detail": f"Mentions '{token}', which does not appear in the cited facts."})

    # De-duplicate while keeping order.
    unique, seen = [], set()
    for problem in problems:
        key = (problem["code"], problem["detail"])
        if key not in seen:
            seen.add(key)
            unique.append(problem)
    return unique
