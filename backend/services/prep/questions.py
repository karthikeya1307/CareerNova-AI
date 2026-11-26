"""Role-specific technical and HR interview questions, personalised with the student's resume.

Technical questions come from the curated bank (``interview_question_bank.json``); beginner /
intermediate / advanced map to the bank's easy / medium / hard. Skills are ordered: role skills on the
resume first (so the student can show real evidence), then the role's missing core skills (expected
in interviews), then other resume skills. Project questions name the student's own projects. HR
questions come from ``hr_question_guide.json`` and are personalised only with resume facts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.services.prep.context import ResumeContext, short_title
from backend.services.question_bank import questions_for_skill, technical_bank

LEVELS = {"beginner": "easy", "intermediate": "medium", "advanced": "hard"}
LEVEL_OF = {v: k for k, v in LEVELS.items()}
HR_PATH = Path(__file__).resolve().parents[2] / "data" / "hr_question_guide.json"


@lru_cache(maxsize=1)
def hr_guide() -> dict[str, Any]:
    data = json.loads(HR_PATH.read_text(encoding="utf-8"))
    ids = [q["id"] for q in data["questions"]]
    assert len(ids) == len(set(ids)), "duplicate HR question ids"
    for q in data["questions"]:
        for key in ("question", "expects", "points", "structure", "mistakes"):
            assert q.get(key), f"{q['id']} is missing {key}"
    text = json.dumps(data).lower()
    assert "http://" not in text and "https://" not in text, "HR guide must not contain links"
    return data


@lru_cache(maxsize=1)
def bank_index() -> dict[str, dict[str, Any]]:
    """Bank question id -> question (with its skill)."""
    index = {}
    for skill, questions in technical_bank()["technical"].items():
        for q in questions:
            index[q["id"]] = {**q, "skill": skill}
    return index


def skill_order(track: dict[str, Any], ctx: ResumeContext) -> list[tuple[str, str]]:
    """(skill, status) with status on_resume | role_missing | resume_only; only skills with bank questions."""
    role_skills = track["core_skills"] + track.get("advanced_skills", [])
    ordered, seen = [], set()

    def add(skill: str, status: str) -> None:
        if skill.casefold() not in seen and questions_for_skill(skill):
            seen.add(skill.casefold())
            ordered.append((skill, status))

    for skill in role_skills:
        if ctx.has(skill):
            add(skill, "on_resume")
    for skill in track["core_skills"]:
        add(skill, "role_missing")
    for skill in ctx.skills:
        add(skill, "resume_only")
    return ordered


def technical_questions(track: dict[str, Any], ctx: ResumeContext, level: str | None = None,
                        per_level: int = 3) -> dict[str, Any]:
    """{level: [question]} for beginner/intermediate/advanced (or one level), plus project questions."""
    levels = [level] if level in LEVELS else list(LEVELS)
    skills = skill_order(track, ctx)
    # Each level keeps one slot for a core skill the role needs but the resume lacks (interviewers ask
    # about required skills too); the other slots use skills the student can back with evidence.
    missing = [pair for pair in skills if pair[1] == "role_missing"]
    if missing and per_level > 1:
        rest = [pair for pair in skills if pair[1] != "role_missing"]
        skills = rest[: per_level - 1] + missing[:1] + rest[per_level - 1:] + missing[1:]
    out: dict[str, list[dict[str, Any]]] = {}
    for name in levels:
        difficulty, picked = LEVELS[name], []
        for skill, status in skills:
            if len(picked) >= per_level:
                break
            q = next((q for q in questions_for_skill(skill) if q["difficulty"] == difficulty), None)
            if q is not None:
                picked.append({"id": q["id"], "kind": "technical", "level": name, "skill": skill,
                               "skill_status": status, "question": q["question"]})
        out[name] = picked
    projects = []
    role_skills = {s.casefold() for s in track["core_skills"] + track.get("advanced_skills", [])}
    for fact in ctx.facts.of_kind("project", "internship", "experience"):
        used = [s for s in ctx.skills if fact.id in ctx.locations.get(s.casefold(), [])]
        relevant = [s for s in used if s.casefold() in role_skills] or used
        if not relevant and len(projects) >= 1:
            continue
        skill_text = f" using {', '.join(relevant[:3])}" if relevant else ""
        projects.append({
            "id": f"proj-{fact.id}", "kind": "project", "level": "intermediate", "skill": relevant[0] if relevant else None,
            "question": f"In \"{short_title(fact.title)}\"{skill_text}, what problem did you solve, what were the key design "
                        f"decisions, and what would you improve?",
            "fact_id": fact.id,
        })
        if len(projects) >= 2:
            break
    return {"role": track["title"], "slug": track["slug"], "levels": out, "project_questions": projects,
            "resume_id": ctx.resume.resume_id}


def hr_questions(track: dict[str, Any], ctx: ResumeContext) -> dict[str, Any]:
    items = []
    project = next(iter(ctx.facts.of_kind("project", "internship", "experience")), None)
    for q in hr_guide()["questions"]:
        text = q["question"]
        personalised = False
        if q["id"] == "hr-why-role":
            text, personalised = f"Why are you interested in the {track['title']} role?", True
        elif q["id"] == "hr-project" and project is not None:
            text, personalised = f"Walk me through \"{short_title(project.title)}\" from your resume.", True
        items.append({"id": q["id"], "kind": "hr", "theme": q["theme"], "question": text, "personalised": personalised})
    return {"role": track["title"], "slug": track["slug"], "questions": items, "resume_id": ctx.resume.resume_id}
