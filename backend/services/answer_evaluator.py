"""Deterministic answer evaluation for interview practice (Phase 6).

Scores are 0-100 and labelled Excellent >= 80, Good >= 65, Fair >= 45,
otherwise Needs work. Feedback is automated guidance, not a hiring verdict.

technical    KEY-POINT COVERAGE, not verified correctness:
             80% key-point coverage + 20% length/clarity. A key point is
             covered by its curated keywords, or (optional) by local
             semantic similarity >= SEMANTIC_THRESHOLD (0.50) using the
             pinned MiniLM model. Safeguards:
             * curated common incorrect statements ("misconceptions") void
               the key point they contradict and cap the score
               (55 for one, 35 for two or more);
             * sentences that express not knowing ("I don't know ...")
               earn no credit; mostly-uncertain answers are capped at 25;
             * answers that are only a list of keywords (no real
               sentences) are capped at 30.
behavioral   STAR structure 50%, addresses the question's theme 20%,
             first-person ownership 15%, length 15%. STAR parts only count
             in real sentences; fewer than 3 real sentences, or every part
             found in a single sentence, halves the STAR credit and caps the
             score at 40. Off-theme answers are capped at 50.
project      mentions the project 25%, its technologies 30%, own role 20%,
             outcome 15%, length 10%.
internship   mentions the company/role 30%, real skills (or a learning plan
             for a missing skill) 30%, specificity 20%, length 20%.

All categories: keyword-only answers are capped at 30, answers under 10
words at 20, and empty answers score 0. Mentions of skills that are not on
the resume produce advisory notes only.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from backend.services.fact_check import skill_mentions

LABELS = [(80.0, "Excellent"), (65.0, "Good"), (45.0, "Fair"), (0.0, "Needs work")]
# Calibrated with the real model on 60 key-point/answer pairs:
#   relevant paraphrases (no keywords)  0.32-0.65 (median 0.55)
#   on-topic but vague "near misses"    max 0.43
#   off-topic technical answers         max 0.04
#   generic fluff                       max 0.13
# 0.50 gives 0% false credit with a 0.07 margin over the worst near miss.
# Embeddings cannot tell a statement from its inversion ("lists are
# immutable" scores 0.97 against "lists are mutable"), which is why curated
# misconception checks run before any keyword or semantic credit.
SEMANTIC_THRESHOLD = 0.50
MIN_WORDS_FOR_SEMANTIC = 8
SHORT_ANSWER_WORDS = 10
SHORT_ANSWER_CAP = 20.0
OFF_THEME_CAP = 50.0
KEYWORD_LIST_CAP = 30.0
UNCERTAIN_CAP = 25.0
ONE_MISCONCEPTION_CAP = 55.0
MANY_MISCONCEPTIONS_CAP = 35.0
THIN_STAR_CAP = 40.0
MIN_STAR_SENTENCES = 3

SCORE_BASIS_TECHNICAL = "key_point_coverage"
COVERAGE_DISCLAIMER = ("This technical score measures key-point coverage. It flags common mistakes but does not "
                       "verify that every statement is technically correct.")

WORD_RE = re.compile(r"[a-z0-9+#']+")
FIRST_PERSON_RE = re.compile(r"\b(i|my|me|i'm|i've)\b")
ACTION_RE = re.compile(r"\bi (?:\w+ed|led|built|made|took|wrote|spoke|set|ran|chose|did|met|began)\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+|;\s+")
SPECIFIC_STOP = {"the", "and", "with", "for", "our", "your", "this", "that", "will", "from", "into", "work"}

# Words that glue real sentences together. A "sentence" without them is a
# keyword list ("mutable immutable hashable dictionary keys ...").
FUNCTION_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "to", "of", "in", "on", "for", "with", "and",
    "or", "but", "it", "its", "it's", "that", "this", "these", "those", "which", "when", "so", "can", "by", "as",
    "because", "you", "they", "we", "i", "my", "our", "not", "from", "at", "if", "then", "than", "has", "have",
    "had", "do", "does", "did", "will", "would", "should", "could", "there", "their", "them", "me", "us", "he",
    "she", "his", "her", "while", "where", "how", "what", "who", "also", "into", "each", "one", "only", "all",
}
MIN_SENTENCE_WORDS = 5
MIN_FUNCTION_WORDS = 2
MIN_FUNCTION_SHARE = 0.2      # ordinary English sentences are roughly 30-50% function words
# Keyword-list detection, tuned on the bank: catches all sample keyword dumps
# while flagging none of the 414 terse key-point summaries and explanations.
KEYWORD_RUN_MIN_ANSWER = 10
KEYWORD_RUN_WORDS = 10
KEYWORD_RUN_MAX_SHARE = 0.18

# "I don't know" style statements. Their keywords earn no credit.
UNCERTAIN_RE = re.compile(
    r"\b(?:i (?:do not|don't|dont) (?:really )?(?:know|understand|remember)"
    r"|(?:i'm|i am) (?:not sure|unsure|not certain|not familiar)"
    r"|not sure (?:if|whether|what|how|about)"
    r"|no idea|i have no clue|no clue"
    r"|i (?:have )?never (?:understood|learned|learnt|studied|heard of)"
    r"|i (?:can't|cannot|can not) (?:remember|recall)"
    r"|i forgot|i have forgotten"
    r"|(?:i'm|i am) (?:just )?guessing)\b"
)

# A negation just before a misconception match means the student is
# rejecting the wrong statement ("it is a myth that lists are immutable").
NEGATION_BEFORE_RE = re.compile(
    r"(?:\b(?:not|never|avoid|avoiding|instead of|rather than|no need to|myth|misconception|mistake|wrong|"
    r"incorrect|false|untrue|common error)\b|n't\b)[^.!?]{0,30}$"
)


def label_for(score: float) -> str:
    return next(name for threshold, name in LABELS if score >= threshold)


def _normalize(text: str) -> str:
    return " " + re.sub(r"\s+", " ", (text or "").lower()) + " "


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text or "") if s and s.strip()]


def is_real_sentence(sentence: str) -> bool:
    words = WORD_RE.findall(sentence.lower())
    function = sum(w in FUNCTION_WORDS for w in words)
    return (len(words) >= MIN_SENTENCE_WORDS and function >= MIN_FUNCTION_WORDS
            and function / len(words) >= MIN_FUNCTION_SHARE)


def _function_share(text: str) -> tuple[float, int]:
    words = WORD_RE.findall(text.lower())
    return (sum(w in FUNCTION_WORDS for w in words) / len(words) if words else 0.0), len(words)


def is_keyword_list(answer: str) -> bool:
    """True for answers that are a run of keywords rather than sentences.

    The answer has no real sentence AND contains an unbroken run of at least
    KEYWORD_RUN_WORDS words with almost no joining words (parenthesised
    examples are ignored). Terse but punctuated answers such as "Pooling
    reduces spatial size. Deeper layers learn features." are not flagged.
    """
    if len(WORD_RE.findall((answer or "").lower())) < KEYWORD_RUN_MIN_ANSWER:
        return False
    sentences = [re.sub(r"\([^)]*\)", " ", s) for s in split_sentences(answer)]
    if any(is_real_sentence(s) for s in sentences):
        return False
    return any(n >= KEYWORD_RUN_WORDS and share < KEYWORD_RUN_MAX_SHARE
               for share, n in map(_function_share, sentences))


def is_uncertain(sentence: str) -> bool:
    return bool(UNCERTAIN_RE.search(sentence.lower()))


def keyword_hit(text: str, keywords: list[str]) -> list[str]:
    """Keywords found in text (prefix match at a word start)."""
    hits = []
    for keyword in keywords:
        keyword = keyword.strip().lower()
        if not keyword:
            continue
        if keyword[0].isalnum():
            if re.search(r"(?<![a-z0-9])" + re.escape(keyword), text):
                hits.append(keyword)
        elif keyword in text:
            hits.append(keyword)
    return hits


def misconception_hits(sentence: str, misconceptions: list[dict[str, Any]]) -> list[str]:
    """Correction notes for curated wrong statements made (not negated) in this sentence."""
    text = re.sub(r"\s+", " ", sentence.lower())
    def asserted(pattern: str) -> bool:
        return any(not NEGATION_BEFORE_RE.search(text[:m.start()]) for m in re.finditer(pattern, text))

    return [entry["note"] for entry in misconceptions or []
            if any(asserted(pattern) for pattern in entry.get("patterns", []))]


def _length_score(words: int, good: int = 40) -> float:
    if words >= good:
        return 1.0
    if words >= good // 2:
        return 0.6
    if words >= SHORT_ANSWER_WORDS:
        return 0.3
    return 0.0


class SemanticMatcher:
    """Local semantic similarity with the pinned embedding model."""

    def __init__(self, embedder):
        self.embedder = embedder

    def max_similarity(self, point: str, answer: str) -> float:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", answer) if len(s.split()) >= 3][:20]
        if not sentences:
            return 0.0
        vectors = self.embedder.embed([point, *sentences])
        return float(np.max(vectors[1:] @ vectors[0]))


def default_semantic_matcher() -> SemanticMatcher | None:
    """The configured local model, or None (keyword-only evaluation)."""
    try:
        from backend.services import embeddings

        embedder = embeddings.get_embedder()
        if embedder.model_name != embeddings.embedding_settings()["model_name"]:
            return None  # e.g. a test embedder: stay deterministic
        return SemanticMatcher(embedder)
    except Exception:
        return None


def _advisories(answer: str, candidate_skills: list[str], allowed: set[str]) -> list[str]:
    have = {s.casefold() for s in candidate_skills} | {s.casefold() for s in allowed}
    return [
        f"You mentioned {skill}, which is not on your resume. Only claim skills you can back up."
        for skill in sorted(skill_mentions(answer)) if skill.casefold() not in have
    ]


def _finish(score: float, words: int, components: dict[str, float], extra: dict[str, Any],
            keyword_list: bool = False) -> dict[str, Any]:
    caps = extra.setdefault("caps_applied", [])
    if keyword_list and words >= SHORT_ANSWER_WORDS and score > KEYWORD_LIST_CAP:
        score = KEYWORD_LIST_CAP
        caps.append("keyword_list")
    if keyword_list:
        extra.setdefault("tips", []).insert(
            0, "Write full sentences that explain the ideas; a list of keywords is not an answer.")
    if words == 0:
        score = 0.0
    elif words < SHORT_ANSWER_WORDS:
        if score > SHORT_ANSWER_CAP:
            caps.append("short_answer")
        score = min(score, SHORT_ANSWER_CAP)
        extra.setdefault("tips", []).insert(0, "Your answer is very short. Aim for several complete sentences.")
    score = round(min(100.0, max(0.0, score)), 1)
    return {"score": score, "label": label_for(score), "word_count": words,
            "components": {k: round(v, 3) for k, v in components.items()}, **extra}


# ------------------------------------------------------------------
# Category evaluators
# ------------------------------------------------------------------

def evaluate_technical(answer, key_points, semantic=None):
    words = len(WORD_RE.findall(answer.lower()))
    sentences = split_sentences(answer)
    uncertain = [s for s in sentences if is_uncertain(s)]
    confident = [s for s in sentences if not is_uncertain(s)]
    confident_answer = " ".join(confident)
    text = _normalize(confident_answer)
    confident_words = len(WORD_RE.findall(confident_answer.lower()))

    incorrect: list[dict[str, Any]] = []
    covered, missed = [], []
    for index, point in enumerate(key_points):
        notes = []
        for sentence in confident:
            for note in misconception_hits(sentence, point.get("misconceptions", [])):
                if note not in notes:
                    notes.append(note)
        if notes:
            incorrect.append({"point": point["point"], "corrections": notes})
            missed.append({"point": point["point"], "similarity": None, "reason": "incorrect_statement"})
            continue
        hits = keyword_hit(text, point.get("keywords", []))
        similarity = None
        if not hits and semantic is not None and confident_words >= MIN_WORDS_FOR_SEMANTIC:
            similarity = semantic.max_similarity(point["point"], confident_answer)
        if hits or (similarity is not None and similarity >= SEMANTIC_THRESHOLD):
            covered.append({"point": point["point"], "matched_by": "keyword" if hits else "semantic",
                            "similarity": None if similarity is None else round(similarity, 3)})
        else:
            missed.append({"point": point["point"],
                           "similarity": None if similarity is None else round(similarity, 3),
                           "reason": "not_covered"})

    coverage = len(covered) / len(key_points) if key_points else 0.0
    length = _length_score(words)
    score = 100 * (0.8 * coverage + 0.2 * length)
    caps: list[str] = []

    tips = []
    for item in incorrect:
        tips += [f"Check this: {note}" for note in item["corrections"]]
    tips += [f"Cover: {m['point']}." for m in missed if m["reason"] == "not_covered"]
    if incorrect:
        cap = ONE_MISCONCEPTION_CAP if len(incorrect) == 1 else MANY_MISCONCEPTIONS_CAP
        if score > cap:
            score = cap
            caps.append("incorrect_statements")

    uncertain_words = sum(len(WORD_RE.findall(s.lower())) for s in uncertain)
    mostly_uncertain = bool(uncertain) and (not confident or uncertain_words * 2 >= words)
    if uncertain:
        tips.append("It is fine to say you are unsure, but then explain what you do know or how you would "
                    "find out. Sentences that say you don't know earn no credit.")
    if mostly_uncertain and score > UNCERTAIN_CAP:
        score = UNCERTAIN_CAP
        caps.append("mostly_uncertain")
    if length < 1:
        tips.append("Add a short example or more detail to show understanding.")

    return _finish(score, words,
                   {"key_point_coverage": coverage, "length": length},
                   {"covered_points": covered, "missed_points": missed, "incorrect_statements": incorrect,
                    "uncertain_sentences": len(uncertain), "tips": tips, "caps_applied": caps,
                    "score_basis": SCORE_BASIS_TECHNICAL, "correctness_verified": False,
                    "method": "keyword+semantic" if semantic else "keyword"},
                   keyword_list=is_keyword_list(answer))


def evaluate_behavioral(answer, key_points, theme_keywords):
    words = len(WORD_RE.findall(answer.lower()))
    real = [s for s in split_sentences(answer) if is_real_sentence(s)]
    star: dict[str, bool] = {}
    sources: set[int] = set()
    for point, name in zip(key_points, ("situation", "task", "action", "result")):
        found_in = None
        for index, sentence in enumerate(real):
            normalized = _normalize(sentence)
            if keyword_hit(normalized, point["keywords"]) or (name == "action" and ACTION_RE.search(normalized)):
                found_in = index
                break
        star[name] = found_in is not None
        if found_in is not None:
            sources.add(found_in)
    star_fraction = sum(star.values()) / 4
    real_text = _normalize(" ".join(real))
    on_theme = bool(keyword_hit(real_text, theme_keywords))
    first_person = len(FIRST_PERSON_RE.findall(real_text)) >= 2
    if words > 300:
        length = 0.8
    elif words >= 60:
        length = 1.0
    elif words >= 30:
        length = 0.6
    else:
        length = 0.3 if words >= SHORT_ANSWER_WORDS else 0.0

    thin_story = len(real) < MIN_STAR_SENTENCES or (star_fraction > 0 and len(sources) < 2)
    if thin_story:
        star_fraction = min(star_fraction, 0.5)

    score = 100 * (0.5 * star_fraction + 0.2 * on_theme + 0.15 * first_person + 0.15 * length)
    caps: list[str] = []
    tips = [f"Add the {part} part of STAR." for part, ok in star.items() if not ok]
    if thin_story:
        tips.insert(0, "Tell it as a short story in several sentences: the situation, your task, what you did "
                       "and the result. Listing STAR words is not enough.")
        if score > THIN_STAR_CAP:
            score = THIN_STAR_CAP
            caps.append("thin_story")
    if not on_theme:
        if score > OFF_THEME_CAP:
            caps.append("off_theme")
        score = min(score, OFF_THEME_CAP)
        tips.insert(0, "Make sure your example directly answers the question asked.")
    if not first_person:
        tips.append('Describe what *you* did ("I ...").')
    if words > 300:
        tips.append("Keep it focused: about 1-2 minutes when spoken.")
    return _finish(score, words,
                   {"star": star_fraction, "on_theme": float(on_theme), "first_person": float(first_person),
                    "length": length},
                   {"star": star, "real_sentences": len(real), "tips": tips, "caps_applied": caps,
                    "method": "rubric"},
                   keyword_list=is_keyword_list(answer))


def evaluate_project(answer, key_points, context):
    text, words = _normalize(answer), len(WORD_RE.findall(answer.lower()))
    title_hit = bool(keyword_hit(text, key_points[0]["keywords"]))
    skills = [s.lower() for s in context.get("fact_skills", [])]
    tech = len(keyword_hit(text, skills)) / len(skills) if skills else None
    role = bool(ACTION_RE.search(text)) or bool(keyword_hit(text, ["my role", "responsib", "i was"]))
    outcome = bool(keyword_hit(text, key_points[-1]["keywords"]))
    length = _length_score(words)

    if tech is None:
        score = 100 * (0.55 * title_hit + 0.2 * role + 0.15 * outcome + 0.1 * length)
    else:
        score = 100 * (0.25 * title_hit + 0.3 * tech + 0.2 * role + 0.15 * outcome + 0.1 * length)
    tips = []
    if not title_hit:
        tips.append("Name the project and explain what it was for.")
    if tech is not None and tech < 1:
        tips.append(f"Explain how you used {', '.join(context.get('fact_skills', []))}.")
    if not role:
        tips.append("Make your personal contribution clear.")
    if not outcome:
        tips.append("Finish with the result or what you learned.")
    return _finish(score, words,
                   {"mentions_project": float(title_hit), "technologies": tech if tech is not None else 0.0,
                    "own_role": float(role), "outcome": float(outcome), "length": length},
                   {"tips": tips, "method": "rubric"},
                   keyword_list=is_keyword_list(answer))


def evaluate_internship(answer, key_points, context, candidate_skills):
    text, words = _normalize(answer), len(WORD_RE.findall(answer.lower()))
    mentions_role = bool(keyword_hit(text, key_points[0]["keywords"]))
    if context.get("kind") == "missing_skill":
        mentions_role = bool(keyword_hit(text, key_points[1]["keywords"]))      # plan to learn the skill
        skills_ok = bool(keyword_hit(text, key_points[0]["keywords"])) or \
            bool(keyword_hit(text, [s.lower() for s in candidate_skills]))
    else:
        skills_ok = bool(keyword_hit(text, [s.lower() for s in candidate_skills]))
    vocabulary = {w for w in WORD_RE.findall(" ".join(str(v) for v in context.values() if v).lower())
                  if len(w) > 3 and w not in SPECIFIC_STOP}
    specific = bool(vocabulary & set(WORD_RE.findall(text)))
    length = _length_score(words)

    score = 100 * (0.3 * mentions_role + 0.3 * skills_ok + 0.2 * specific + 0.2 * length)
    tips = []
    if not mentions_role:
        tips.append("Refer specifically to this company or role (or your learning plan).")
    if not skills_ok:
        tips.append("Connect your answer to skills that are actually on your resume.")
    if not specific:
        tips.append("Be specific to this internship rather than generic.")
    return _finish(score, words,
                   {"specific_to_role": float(mentions_role), "real_skills": float(skills_ok),
                    "specificity": float(specific), "length": length},
                   {"tips": tips, "method": "rubric"},
                   keyword_list=is_keyword_list(answer))


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def evaluate_answer(
    question: dict[str, Any],
    answer: str,
    candidate_skills: list[str],
    semantic: SemanticMatcher | None = None,
) -> dict[str, Any]:
    category = question["category"]
    key_points = question.get("key_points") or []
    context = question.get("context") or {}
    answer = answer or ""

    if category == "technical":
        result = evaluate_technical(answer, key_points, semantic)
    elif category == "behavioral":
        result = evaluate_behavioral(answer, key_points, context.get("theme_keywords", []))
    elif category == "project":
        result = evaluate_project(answer, key_points, context)
    else:
        result = evaluate_internship(answer, key_points, context, candidate_skills)

    allowed = {question["skill"]} if question.get("skill") else set()
    result["advisories"] = _advisories(answer, candidate_skills, allowed)
    result["category"] = category
    result["feedback"] = render_feedback(result)
    return result


def render_feedback(result: dict[str, Any]) -> str:
    if result.get("score_basis") == SCORE_BASIS_TECHNICAL:
        lines = [f"Key-point coverage {result['score']}/100 ({result['label']}). Automated guidance, not a "
                 "hiring decision.", COVERAGE_DISCLAIMER]
    else:
        lines = [f"Score {result['score']}/100 ({result['label']}). Automated guidance, not a hiring decision."]
    if result.get("incorrect_statements"):
        lines.append("Possible mistakes: " + " ".join(
            note for item in result["incorrect_statements"] for note in item["corrections"]))
    if result.get("covered_points"):
        lines.append("Covered: " + "; ".join(p["point"] for p in result["covered_points"]) + ".")
    missing = [p["point"] for p in result.get("missed_points", []) if p.get("reason") != "incorrect_statement"]
    if missing:
        lines.append("Missing: " + "; ".join(missing) + ".")
    if result.get("star"):
        present = [k for k, v in result["star"].items() if v]
        lines.append("STAR parts present: " + (", ".join(present) if present else "none") + ".")
    lines += [tip for tip in result.get("tips", []) if not tip.startswith("Check this: ")]
    lines += result.get("advisories", [])
    return "\n".join(lines)
