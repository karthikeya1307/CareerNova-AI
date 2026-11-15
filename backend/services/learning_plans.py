"""Curated, versioned learning plans (backend/data/learning_plans.json).

Plans contain topic outlines, prerequisites (canonical skills), a level
and an approximate effort. They contain no external links or named
courses. Skills without a curated plan get a clearly labelled generic plan
(``curated: false``) instead of invented content.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.services.skill_normalizer import SKILL_CATALOG

PLANS_PATH = Path(__file__).resolve().parents[1] / "data" / "learning_plans.json"
LEVELS = {"beginner", "intermediate", "advanced"}


@lru_cache(maxsize=1)
def load_plans() -> dict[str, Any]:
    data = json.loads(PLANS_PATH.read_text(encoding="utf-8"))
    validate_plans(data)
    return data


def validate_plans(data: dict[str, Any]) -> None:
    """Raise ValueError if the plan file is malformed or cyclic."""
    if not isinstance(data.get("version"), str) or not isinstance(data.get("plans"), dict):
        raise ValueError("learning_plans.json needs 'version' and 'plans'")

    plans = data["plans"]
    for skill, plan in plans.items():
        if skill not in SKILL_CATALOG:
            raise ValueError(f"Plan for unknown skill: {skill}")
        if plan.get("level") not in LEVELS:
            raise ValueError(f"Invalid level for {skill}")
        if not isinstance(plan.get("estimated_hours"), int) or plan["estimated_hours"] <= 0:
            raise ValueError(f"Invalid estimated_hours for {skill}")
        if not plan.get("topics") or not all(isinstance(t, str) and t for t in plan["topics"]):
            raise ValueError(f"Missing topics for {skill}")
        for prerequisite in plan.get("prerequisites", []):
            if prerequisite not in SKILL_CATALOG:
                raise ValueError(f"Unknown prerequisite {prerequisite} for {skill}")
        text = json.dumps(plan).lower()
        if "http://" in text or "https://" in text or "www." in text:
            raise ValueError(f"Plans must not contain links ({skill})")

    # No prerequisite cycles.
    visiting, done = set(), set()

    def visit(skill: str) -> None:
        if skill in done:
            return
        if skill in visiting:
            raise ValueError(f"Prerequisite cycle at {skill}")
        visiting.add(skill)
        for prerequisite in plans.get(skill, {}).get("prerequisites", []):
            visit(prerequisite)
        visiting.discard(skill)
        done.add(skill)

    for skill in plans:
        visit(skill)


def plans_version() -> str:
    return load_plans()["version"]


def plan_for(skill: str) -> dict[str, Any]:
    """Return the learning plan for a skill (generic if not curated)."""
    plan = load_plans()["plans"].get(skill)
    if plan is not None:
        return {"skill": skill, "curated": True, **plan}
    return {
        "skill": skill,
        "curated": False,
        "level": None,
        "estimated_hours": None,
        "prerequisites": [],
        "topics": [
            f"Core concepts of {skill}",
            f"Hands-on practice with {skill}",
            f"Apply {skill} in a small portfolio project",
        ],
        "note": "No curated plan exists for this skill yet; this is a generic outline.",
    }


def learning_order(skills: list[str], known: set[str] | None = None) -> list[str]:
    """Order skills so that prerequisites come first (stable, deterministic).

    Only skills in ``skills`` are ordered; prerequisites already known by
    the candidate (``known``) are ignored. Ties keep the input order
    (which callers sort by priority).
    """
    known = {k.casefold() for k in (known or set())}
    wanted = {s: i for i, s in enumerate(skills)}
    plans = load_plans()["plans"]
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(skill: str) -> None:
        if skill in seen:
            return
        seen.add(skill)
        prerequisites = [
            p for p in plans.get(skill, {}).get("prerequisites", [])
            if p in wanted and p.casefold() not in known
        ]
        for prerequisite in sorted(prerequisites, key=wanted.get):
            visit(prerequisite)
        ordered.append(skill)

    for skill in skills:
        visit(skill)
    return ordered


def missing_prerequisites(skill: str, known: set[str]) -> list[str]:
    """Prerequisites of ``skill`` that the candidate does not have."""
    lowered = {k.casefold() for k in known}
    return [
        p for p in plan_for(skill).get("prerequisites", [])
        if p.casefold() not in lowered
    ]
