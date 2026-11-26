"""Personalised interview preparation roadmap for one role, from the resume and the role's track.

Priorities: missing core skill = high, missing advanced skill = medium, skill already on the resume =
low (revise and prepare examples). The sequence follows the track's stages; within a stage, high
priority first. Hours come from the curated learning plans (estimates, not guarantees).
"""

from __future__ import annotations

from typing import Any

from backend.services.learning_plans import plan_for
from backend.services.question_bank import questions_for_skill
from backend.services.prep.context import ResumeContext, short_title
from backend.services.prep.roles import assess
from backend.services.skill_progress import official_resources

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def roadmap(track: dict[str, Any], ctx: ResumeContext, progress: dict[str, str] | None = None) -> dict[str, Any]:
    progress = progress or {}
    fit = assess(track, ctx)
    core = {s.casefold() for s in track["core_skills"]}
    resources = official_resources()

    def topic(skill: str) -> dict[str, Any]:
        have = ctx.has(skill)
        priority = "low" if have else ("high" if skill.casefold() in core else "medium")
        plan = plan_for(skill)
        return {
            "skill": skill, "on_resume": have, "priority": priority,
            "action": ("Revise it and prepare one example from your resume" if have else "Learn it and build something small with it"),
            "topics": plan.get("topics", [])[:4], "estimated_hours": None if have else plan.get("estimated_hours"),
            "resource": resources.get(skill), "progress": progress.get(skill, "not_started"),
        }

    stages, seen = [], set()
    for number, stage in enumerate(track["roadmap"], start=1):
        items = [topic(s) for s in stage["skills"] if s.casefold() not in seen]
        seen |= {s.casefold() for s in stage["skills"]}
        items.sort(key=lambda t: PRIORITY_ORDER[t["priority"]])
        stages.append({"step": number, "stage": stage["stage"], "goal": stage["goal"], "topics": items})
    leftovers = [s for s in track["core_skills"] + track.get("advanced_skills", []) if s.casefold() not in seen]
    if leftovers:
        stages.append({"step": len(stages) + 1, "stage": "Also expected", "goal": "Other skills this role uses.",
                       "topics": sorted((topic(s) for s in leftovers), key=lambda t: PRIORITY_ORDER[t["priority"]])})

    project_improvements = []
    for fact in ctx.facts.of_kind("project")[:3]:
        missing = fit["core"]["missing"]
        extra = f" or extend it with {missing[0]}" if missing else ""
        project_improvements.append(
            f"\"{short_title(fact.title)}\": add a README with the problem, your role and how to run it, tests for the main "
            f"logic{extra}; quote results only where you measured them.")
    if not project_improvements:
        project_improvements.append("Your resume lists no projects yet - build one of the project ideas below and add it.")

    hours = sum(t["estimated_hours"] or 0 for s in stages for t in s["topics"] if t["priority"] != "low")
    # Interview questions to practise: one per high/medium priority skill (beginner first), from the curated bank.
    practice_questions = []
    for s in stages:
        for t in s["topics"]:
            if t["priority"] == "low" or len(practice_questions) >= 6:
                continue
            bank = questions_for_skill(t["skill"])
            q = next((q for q in bank if q["difficulty"] == "easy"), bank[0] if bank else None)
            if q is not None:
                practice_questions.append({"skill": t["skill"], "question": q["question"], "id": q["id"]})
    return {
        "role": track["title"], "slug": track["slug"], "fit": {"score": fit["score"], "readiness": fit["readiness"]},
        "summary": (f"{fit['readiness']['label']} ({fit['score']}/100). Focus first on: "
                    f"{', '.join(fit['improve'][:3]) or 'revising your existing skills and examples'}."),
        "stages": stages,
        "skill_gaps": {"core_missing": fit["core"]["missing"], "advanced_missing": fit["advanced"]["missing"]},
        "estimated_learning_hours": hours or None,
        "coding_exercises": track["exercises"],
        "practice_questions": practice_questions,
        "project_improvements": project_improvements,
        "project_ideas": track["projects"],
        "interview_practice": [
            f"Answer the beginner and intermediate {track['title']} technical questions out loud, then check them against the key points.",
            "Prepare STAR stories for teamwork, a deadline, a mistake you learned from and a project you are proud of.",
            f"Run a mock interview for {track['title']} in Interview practice and repeat the weakest category.",
            "Practise \"Tell me about yourself\" until it takes under two minutes.",
        ],
        "resume_advice": track["resume_advice"],
        "resume_id": ctx.resume.resume_id,
    }
