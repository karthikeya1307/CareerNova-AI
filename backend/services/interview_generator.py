"""Deterministic interview question generation (Phase 6).

Sources:
  technical   curated bank, ordered by the internship's needs then the
              candidate's own skills; labelled with whether the
              candidate lists the skill
  project     templates filled ONLY with a candidate fact's title and the
              skills that fact names (cites the fact id)
  behavioral  curated bank (recently used questions avoided)
  internship  templates filled ONLY from the internship record

Selection is reproducible: the same seed gives the same questions.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

from backend.models import Internship
from backend.services.document_common import matched_skills, oxford_join, ranked_facts
from backend.services.fact_base import CandidateFacts, Fact
from backend.services.fact_check import skill_mentions
from backend.services.internship_text import internship_skill_names
from backend.services.learning_plans import plan_for
from backend.services.question_bank import behavioral_bank, questions_for_skill

CATEGORIES = ("technical", "project", "behavioral", "internship")
DEFAULT_MIX = {"technical": 3, "project": 2, "behavioral": 2, "internship": 1}
MAX_QUESTIONS = 15

ROLE_KEYWORDS = ["i ", "my role", "i built", "i implemented", "i designed", "i developed",
                 "i created", "i wrote", "responsib", "i was"]
OUTCOME_KEYWORDS = ["result", "outcome", "learn", "improv", "impact", "users", "reduc",
                    "increas", "achiev", "deliver", "finished", "completed"]


@dataclass(frozen=True)
class GenerationRequest:
    mix: dict[str, int]
    difficulty: str = "mixed"               # mixed | easy | medium | hard
    seed: int = 0
    exclude_behavioral: frozenset[str] = frozenset()


def _title_keywords(title: str) -> list[str]:
    stop = {"with", "from", "using", "the", "and", "for", "intern", "internship", "project"}
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{3,}", title)]
    return [w for w in words if w not in stop][:4] or [title.lower()[:20]]


# ------------------------------------------------------------------
# Technical
# ------------------------------------------------------------------

def _technical_skill_order(candidate: CandidateFacts, internship: Internship | None) -> list[tuple[str, str]]:
    """(skill, status) where status is have | required_missing | preferred_missing."""
    have = {s.casefold() for s in candidate.skills}
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(skill: str, status: str) -> None:
        if skill.casefold() not in seen and questions_for_skill(skill):
            seen.add(skill.casefold())
            ordered.append((skill, status))

    if internship is not None:
        required, preferred = internship_skill_names(internship)
        for skill in required:
            if skill.casefold() in have:
                add(skill, "have")
        for skill in required:
            add(skill, "have" if skill.casefold() in have else "required_missing")
        for skill in preferred:
            if skill.casefold() in have:
                add(skill, "have")
    for skill in candidate.skills:
        add(skill, "have")
    return ordered


def _pick_difficulty(index: int, difficulty: str) -> str:
    return ("easy", "medium", "hard")[index % 3] if difficulty == "mixed" else difficulty


def technical_questions(
    candidate: CandidateFacts, internship: Internship | None, count: int, difficulty: str, rng: random.Random
) -> list[dict[str, Any]]:
    skills = _technical_skill_order(candidate, internship)
    result: list[dict[str, Any]] = []
    used: set[str] = set()
    rounds = 0
    while len(result) < count and skills and rounds < 3:
        for skill, status in skills:
            if len(result) >= count:
                break
            wanted = _pick_difficulty(len(result), difficulty)
            options = [q for q in questions_for_skill(skill) if q["id"] not in used]
            preferred = [q for q in options if q["difficulty"] == wanted] or options
            if not preferred:
                continue
            q = rng.choice(sorted(preferred, key=lambda x: x["id"]))
            used.add(q["id"])
            result.append({
                "category": "technical",
                "text": q["question"],
                "difficulty": q["difficulty"],
                "skill": skill,
                "bank_question_id": q["id"],
                "key_points": q["key_points"],
                "explanation": q["explanation"],
                "source_fact_ids": [],
                "context": {"skill_status": status},
                "suggested_answer": {
                    "type": "key_points",
                    "points": [p["point"] for p in q["key_points"]],
                    "explanation": q["explanation"],
                    "note": ("This skill is required by the internship but is not on your resume; "
                             "answer honestly about your level." if status == "required_missing" else None),
                },
            })
        rounds += 1
    return result


# ------------------------------------------------------------------
# Project / experience
# ------------------------------------------------------------------

def _project_question(fact: Fact, variant: int) -> dict[str, Any]:
    title = fact.title.strip().rstrip(".")
    skills = sorted(skill_mentions(fact.text))
    if fact.kind in ("experience", "internship"):
        text = f'Tell me about your role in "{title}". What were your main responsibilities and contributions?'
    elif skills and variant % 2 == 1:
        text = (f'In your project "{title}", you used {oxford_join(skills)}. '
                "Why did you choose them, and what challenges did you face?")
    else:
        text = f'Walk me through your project "{title}". What problem did it solve, and what was your role?'

    key_points = [
        {"point": f'Describe the context and goal of "{title}"', "keywords": _title_keywords(title)},
        {"point": "Explain your own role and actions", "keywords": ROLE_KEYWORDS},
        {"point": "Share the result or what you learned", "keywords": OUTCOME_KEYWORDS},
    ]
    if skills:
        key_points.insert(2, {"point": f"Explain how you used {oxford_join(skills)}",
                              "keywords": [s.lower() for s in skills]})

    return {
        "category": "project",
        "text": text,
        "difficulty": "medium",
        "skill": None,
        "bank_question_id": None,
        "key_points": key_points,
        "explanation": "Interviewers check that you understand your own work and can explain your decisions.",
        "source_fact_ids": [fact.id],
        "context": {"fact_title": title, "fact_skills": skills},
        "suggested_answer": {
            "type": "outline",
            "points": [
                f'Context: what "{title}" was and why it was needed',
                "Your role: what you personally did",
                (f"Technologies: how you used {oxford_join(skills)}" if skills
                 else "Technologies: the tools you actually used"),
                "Outcome: the result or what you learned (use real numbers only if you have them)",
            ],
            "from_your_resume": fact.lines[:4],
        },
    }


def project_questions(candidate: CandidateFacts, internship: Internship | None, count: int) -> list[dict[str, Any]]:
    facts = candidate.of_kind("experience", "internship", "project")
    if internship is not None:
        facts = ranked_facts(facts, internship)
    return [_project_question(fact, i) for i, fact in enumerate(facts[:count])]


# ------------------------------------------------------------------
# Behavioral
# ------------------------------------------------------------------

STAR_POINTS = [
    {"point": "Situation: set the scene briefly", "keywords": ["when i", "at my", "during", "in my", "situation", "once", "while"]},
    {"point": "Task: what you needed to achieve", "keywords": ["task", "goal", "needed to", "had to", "responsib", "objective"]},
    {"point": "Action: what you did, in the first person", "keywords": ["i decided", "i organi", "i spoke", "i built", "i created", "i led", "i worked", "i suggested", "i set"]},
    {"point": "Result: the outcome and what you learned", "keywords": ["result", "outcome", "in the end", "finally", "learn", "improv", "led to"]},
]


def behavioral_questions(
    candidate: CandidateFacts, count: int, rng: random.Random, exclude: frozenset[str]
) -> list[dict[str, Any]]:
    bank = sorted(behavioral_bank()["questions"], key=lambda q: q["id"])
    fresh = [q for q in bank if q["id"] not in exclude]
    pool = fresh if len(fresh) >= count else bank
    chosen = rng.sample(pool, min(count, len(pool)))
    stories = [f.id for f in candidate.of_kind("experience", "internship", "project")][:2]

    return [{
        "category": "behavioral",
        "text": q["question"],
        "difficulty": q["difficulty"],
        "skill": None,
        "bank_question_id": q["id"],
        "key_points": STAR_POINTS,
        "explanation": "Use the STAR method: Situation, Task, Action, Result.",
        "source_fact_ids": stories,
        "context": {"theme": q["theme"], "theme_keywords": q["theme_keywords"]},
        "suggested_answer": {
            "type": "star",
            "points": [p["point"] for p in STAR_POINTS],
            "tips": q["tips"],
            "possible_stories": [candidate.by_id[f].title for f in stories],
        },
    } for q in chosen]


# ------------------------------------------------------------------
# Internship-specific
# ------------------------------------------------------------------

def internship_questions(
    candidate: CandidateFacts, internship: Internship | None, count: int
) -> list[dict[str, Any]]:
    if internship is None or count <= 0:
        return []
    title, company, domain = internship.title, internship.company, internship.domain
    required, _ = internship_skill_names(internship)
    have = {s.casefold() for s in candidate.skills}
    matched_req, matched_pref = matched_skills(candidate, internship)
    matched = [*matched_req, *matched_pref][:4]
    missing = [s for s in required if s.casefold() not in have]
    base_context = {"company": company, "title": title, "domain": domain}
    company_kw = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", company)][:2] + _title_keywords(title)[:2]

    candidates: list[dict[str, Any]] = [{
        "text": f"Why do you want to join {company} as a {title}?",
        "key_points": [
            {"point": f"Refer to {company} or the {title} role specifically", "keywords": company_kw},
            {"point": "Connect the role to your real skills", "keywords": [s.lower() for s in candidate.skills] or ["skill"]},
            {"point": "Say what you want to learn or contribute", "keywords": ["learn", "contribut", "grow", "gain", "experience"]},
        ],
        "suggested_answer": {"type": "outline", "points": [
            f"What attracts you to {company} and this role",
            f"Skills you already have that fit: {oxford_join(matched) if matched else 'name your most relevant skills'}",
            "What you hope to learn and contribute"]},
        "context": {**base_context, "kind": "motivation"},
    }]
    if missing:
        skill = missing[0]
        plan = plan_for(skill)
        candidates.append({
            "text": f"This role requires {skill}, which is not on your resume yet. How would you get up to speed with it?",
            "skill": skill,
            "key_points": [
                {"point": "Be honest about your current level", "keywords": ["honest", "not yet", "haven't", "have not", "new to", "beginner", "currently learning"]},
                {"point": f"Give a concrete plan to learn {skill}", "keywords": [skill.lower(), "plan", "course", "practice", "project", "documentation", "learn"]},
                {"point": "Mention related skills or experience you already have", "keywords": [s.lower() for s in candidate.skills] or ["similar"]},
            ],
            "suggested_answer": {"type": "outline", "points": [
                f"Acknowledge that {skill} is new to you",
                f"Plan: {', '.join(plan['topics'][:3])}",
                "Connect it to skills you already have"]},
            "context": {**base_context, "kind": "missing_skill", "skill": skill},
        })
    candidates.append({
        "text": f"Which of your skills make you a good fit for the {title} role?",
        "key_points": [
            {"point": "Name specific skills the role needs that you have", "keywords": [s.lower() for s in matched] or ["skill"]},
            {"point": "Support them with an example from your experience or projects", "keywords": ["project", "experience", "example", "built", "worked"]},
            {"point": "Link them to the role's work", "keywords": company_kw + ["role", "team", "help"]},
        ],
        "suggested_answer": {"type": "outline", "points": [
            f"Matching skills from your resume: {oxford_join(matched) if matched else 'none matched directly - focus on related skills'}",
            "One concrete example where you used them",
            "How they would help in this role"]},
        "context": {**base_context, "kind": "fit"},
    })
    if domain:
        candidates.append({
            "text": f"What interests you about working in {domain}?",
            "key_points": [
                {"point": f"Show genuine interest in {domain}", "keywords": [w.lower() for w in re.findall(r"[A-Za-z]{3,}", domain)] + ["interest", "enjoy"]},
                {"point": "Mention something you have done or learned in this area", "keywords": ["project", "course", "learn", "built", "experience"]},
                {"point": "Describe where you want to grow", "keywords": ["grow", "learn", "future", "career", "goal"]},
            ],
            "suggested_answer": {"type": "outline", "points": [
                f"What draws you to {domain}", "Related work you have actually done", "Where you want to grow"]},
            "context": {**base_context, "kind": "domain"},
        })

    result = []
    for item in candidates[:count]:
        result.append({
            "category": "internship",
            "text": item["text"],
            "difficulty": "medium",
            "skill": item.get("skill"),
            "bank_question_id": None,
            "key_points": item["key_points"],
            "explanation": "Interviewers check your motivation and how well you understand the role.",
            "source_fact_ids": [],
            "context": item["context"],
            "suggested_answer": item["suggested_answer"],
        })
    return result


# ------------------------------------------------------------------
# Session question set
# ------------------------------------------------------------------

def generate_questions(
    candidate: CandidateFacts, internship: Internship | None, request: GenerationRequest
) -> list[dict[str, Any]]:
    mix = {c: max(0, int(request.mix.get(c, 0))) for c in CATEGORIES}
    if internship is None:
        mix["behavioral"] += mix["internship"]
        mix["internship"] = 0

    rng = random.Random(request.seed)
    questions = (
        technical_questions(candidate, internship, mix["technical"], request.difficulty, rng)
        + project_questions(candidate, internship, mix["project"])
        + internship_questions(candidate, internship, mix["internship"])
        + behavioral_questions(candidate, mix["behavioral"], rng, request.exclude_behavioral)
    )

    seen, unique = set(), []
    for q in questions:
        if q["text"] not in seen:
            seen.add(q["text"])
            unique.append(q)
    return unique[:MAX_QUESTIONS]


def generation_notices(
    candidate: CandidateFacts, internship: Internship | None, request: GenerationRequest,
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Explain when the generated set differs from the requested mix."""
    requested = {c: max(0, int(request.mix.get(c, 0))) for c in CATEGORIES}
    effective = dict(requested)
    notices: list[dict[str, Any]] = []
    if internship is None and requested["internship"]:
        effective["behavioral"] += effective["internship"]
        effective["internship"] = 0
        notices.append({
            "code": "internship_questions_replaced", "category": "internship",
            "requested": requested["internship"], "generated": 0,
            "detail": "No internship was selected, so internship-specific questions were replaced with "
                      "behavioral questions."})

    counts = {c: sum(1 for q in questions if q["category"] == c) for c in CATEGORIES}
    projects = len(candidate.of_kind("experience", "internship", "project"))
    skills = len(_technical_skill_order(candidate, internship))
    reasons = {
        "technical": f"Only {skills} skill(s) from your resume and the internship have questions in the bank.",
        "project": f"Your resume has {projects} project or experience entr{'y' if projects == 1 else 'ies'} "
                   "to ask about. Add projects to your resume for more questions.",
        "internship": "Fewer internship-specific questions apply to this internship.",
        "behavioral": "Not enough new behavioral questions were available.",
    }
    for category in CATEGORIES:
        if counts[category] < effective[category]:
            notices.append({"code": "fewer_questions", "category": category, "requested": effective[category],
                            "generated": counts[category], "detail": reasons[category]})
    return notices
