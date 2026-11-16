"""Claim-level verification of AI-reworded answers.

A sentence is accepted only if every factual claim in it is supported by
the facts it cites. Checks (all must pass):

1. it cites at least one fact, only known facts, and not too many;
2. numbers, skills and capitalised names appear in the CITED facts
   (``fact_check.check_statement`` with no extra allowed skills);
3. skill polarity: a skill a cited fact marks as missing must be described
   as missing (and vice versa) - "you have Docker" is rejected when the
   fact says Docker is missing;
4. status words (applied, rejected, selected, ...) must appear in the cited
   facts; a negated status ("not rejected") is treated as uncertain;
5. overclaiming words (guaranteed, definitely, best, will get, ...) that the
   facts do not contain are rejected as uncertain;
6. no "[removed]" placeholders.

The whole AI answer is rejected if ANY sentence fails or is uncertain; the
deterministic answer is used instead.
"""

from __future__ import annotations

import re
from typing import Any

from backend.services.assistant.facts import AssistantFact
from backend.services.fact_check import check_statement, skill_mentions
from backend.services.llm_privacy import REMOVED

MAX_SENTENCES = 12
MAX_SENTENCE_CHARS = 400
MAX_CITATIONS = 6

NEGATIVE_CUES = re.compile(r"\b(missing|lack|lacking|lacks|not|no|don't|do not|doesn't|does not|haven't|have not|"
                           r"without|need to learn|needs? to (?:learn|add|improve)|gap|gaps|absent|isn't|aren't)\b")
STATUS_WORDS = re.compile(r"\b(saved|applied|shortlisted|interview[_ ]scheduled|selected|rejected|withdrawn|"
                          r"pending|completed|overdue|cancelled|passed|failed|offer|offered|hired|accepted)\b")
NEGATED_STATUS = re.compile(r"\b(not|never|no longer|isn't|wasn't|haven't|hasn't)\b[^.]{0,25}\b(saved|applied|"
                            r"shortlisted|selected|rejected|withdrawn|accepted|hired|offered)\b")
OVERCLAIM = re.compile(r"\b(guarantee[ds]?|definitely|certainly|surely|will (?:get|be (?:selected|hired|accepted))|"
                       r"best|worst|perfect|always|never|100%|ensure[sd]?)\b")


# fact_check skips the first capitalised word of a sentence (ordinary capitalisation); a name there
# ("Google liked your profile") must still come from the cited facts unless it is a common starter.
SENTENCE_STARTERS = {
    "you", "your", "you're", "yours", "the", "a", "an", "this", "that", "these", "those", "it", "its", "it's",
    "there", "here", "based", "according", "great", "good", "overall", "however", "also", "in", "on", "for",
    "with", "as", "we", "i", "my", "our", "to", "at", "by", "from", "since", "because", "so", "and", "but", "yes",
    "no", "note", "unfortunately", "currently", "next", "first", "second", "third", "finally", "then", "one",
    "two", "three", "both", "each", "all", "some", "several", "while", "if", "when", "once", "after", "before",
    "right", "now", "today", "keep", "consider", "try", "start", "learn", "focus", "remember", "please", "nice",
    "well", "sure", "ok", "okay", "nothing", "none", "only", "just", "still", "already",
}
FIRST_WORD = re.compile(r"(?:^|[.!?]\s+)([A-Z][A-Za-z0-9&+#.'-]*)")


def _problem(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def verify_sentence(text: str, fact_ids: list[str], facts: dict[str, AssistantFact]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if not isinstance(text, str) or not text.strip():
        return [_problem("empty", "Empty sentence.")]
    if len(text) > MAX_SENTENCE_CHARS:
        problems.append(_problem("too_long", "Sentence is too long to verify."))
    if REMOVED in text:
        problems.append(_problem("privacy_placeholder", "Repeats a removed personal detail."))
    if not isinstance(fact_ids, list) or not fact_ids or not all(isinstance(f, str) for f in fact_ids):
        return problems + [_problem("no_citation", "Sentence cites no facts.")]
    if len(fact_ids) > MAX_CITATIONS:
        problems.append(_problem("too_many_citations", "Cites too many facts to verify."))
    unknown = [f for f in fact_ids if f not in facts]
    if unknown:
        return problems + [_problem("unknown_fact", f"Cites unknown fact(s) {', '.join(unknown)}.")]

    cited = [facts[f] for f in fact_ids]
    cited_text = " ".join(f.text for f in cited)
    lower, cited_lower = text.lower(), cited_text.lower()

    # 2. numbers, skills, names (strict: only what the cited facts contain)
    problems += check_statement(text, fact_ids, facts, candidate_skills=[], context_texts=[])
    cited_words = set(re.findall(r"[a-z0-9+#.'-]+", cited_lower))
    for word in FIRST_WORD.findall(text):
        key = word.lower().strip(".'-")
        if key not in SENTENCE_STARTERS and key not in cited_words and not skill_mentions(word):
            problems.append(_problem("unsupported_term", f"Mentions '{word}', which does not appear in the cited facts."))

    # 3. skill polarity
    has_negative = bool(NEGATIVE_CUES.search(lower))
    for skill in skill_mentions(text):
        polarities = {f.polarity[skill] for f in cited if skill in f.polarity}
        if len(polarities) > 1:
            problems.append(_problem("uncertain_polarity", f"The cited facts disagree about {skill}."))
        elif polarities == {"missing"} and not has_negative:
            problems.append(_problem("polarity", f"Says or implies you have {skill}, but the facts list it as missing."))
        elif polarities == {"have"} and has_negative:
            problems.append(_problem("polarity", f"Says {skill} is missing, but the facts list it as a skill you have."))
        elif polarities == {"partial"} and not has_negative and "partly" not in lower and "related" not in lower:
            problems.append(_problem("polarity", f"Overstates {skill}, which the facts list as only partly covered."))

    # 4. statuses
    if NEGATED_STATUS.search(lower):
        problems.append(_problem("uncertain_status", "Negated status claims cannot be verified."))
    for word in set(STATUS_WORDS.findall(lower)):
        normalized = word.replace("_", " ")
        if normalized not in cited_lower.replace("_", " "):
            problems.append(_problem("unsupported_status", f"Mentions '{word}', which the cited facts don't state."))

    # 5. overclaiming
    for word in set(OVERCLAIM.findall(lower)):
        if word not in cited_lower:
            problems.append(_problem("overclaim", f"Uses '{word}', which the facts don't support."))
    return problems


def verify_answer(response: Any, facts: list[AssistantFact]) -> tuple[list[dict[str, Any]] | None, list[dict]]:
    """Return (accepted sentences, problems). Sentences are None when anything fails."""
    by_id = {f.id: f for f in facts}
    if not isinstance(response, dict) or not isinstance(response.get("sentences"), list):
        return None, [_problem("invalid_output", "The AI response was not in the expected format.")]
    sentences = response["sentences"]
    if not sentences or len(sentences) > MAX_SENTENCES:
        return None, [_problem("invalid_output", "The AI response had no sentences or too many.")]
    accepted, problems = [], []
    for index, item in enumerate(sentences, start=1):
        if not isinstance(item, dict):
            problems.append({"sentence": index, **_problem("invalid_output", "Not a sentence object.")})
            continue
        found = verify_sentence(item.get("text"), item.get("fact_ids"), by_id)
        if found:
            problems += [{"sentence": index, **p} for p in found]
        else:
            accepted.append({"text": item["text"].strip(), "fact_ids": item["fact_ids"]})
    return (None if problems else accepted), problems
