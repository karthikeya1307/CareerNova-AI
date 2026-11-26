"""Career tracks for 14 roles (backend/data/career_tracks.json, ``tracks-v2``).

Each track has a summary, core and advanced skills, a staged roadmap, exercises, projects and
resume advice (curated text), plus - assembled at request time from existing curated data -
learning topics (learning_plans.json), official documentation links (only where curated),
interview questions (interview_question_bank.json) and the student's own skill coverage and
progress. Relevant jobs come from the listings in the database, ranked by how many of the track's
skills each job asks for. Nothing is AI-generated and no job or link is invented.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.models import Internship
from backend.services.internship_text import internship_skill_names
from backend.services.learning_plans import plan_for
from backend.services.question_bank import questions_for_skill
from backend.services.skill_progress import LABELS, official_resources

PATH = Path(__file__).resolve().parents[1] / "data" / "career_tracks.json"
EXPECTED_SLUGS = {
    "software-developer", "ai-engineer", "machine-learning-engineer", "data-scientist", "data-analyst",
    "web-developer", "java-developer", "python-developer", "cybersecurity-analyst", "cloud-engineer",
    "devops-engineer", "frontend-developer", "backend-developer", "full-stack-developer",
}


@lru_cache(maxsize=1)
def load_tracks() -> list[dict[str, Any]]:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    tracks = data["tracks"]
    slugs = {t["slug"] for t in tracks}
    assert slugs == EXPECTED_SLUGS, f"career tracks mismatch: {sorted(slugs ^ EXPECTED_SLUGS)}"
    for track in tracks:
        for key in ("title", "summary", "core_skills", "roadmap", "exercises", "projects", "resume_advice"):
            assert track.get(key), f"{track['slug']} is missing {key}"
    return tracks


def get_track(slug: str) -> dict[str, Any] | None:
    return next((t for t in load_tracks() if t["slug"] == slug), None)


def summary(track: dict[str, Any]) -> dict[str, Any]:
    return {"slug": track["slug"], "title": track["title"], "summary": track["summary"],
            "core_skills": track["core_skills"], "domains": track.get("domains", [])}


def all_skills(track: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(track["core_skills"] + track.get("advanced_skills", [])))


def detail(track: dict[str, Any], candidate_skills: list[str] | None = None,
           progress: dict[str, dict] | None = None) -> dict[str, Any]:
    have = {s.casefold() for s in (candidate_skills or [])}
    progress = progress or {}
    resources = official_resources()

    def skill_entry(name: str, tier: str) -> dict[str, Any]:
        plan = plan_for(name)
        status = progress.get(name, {}).get("status", "not_started")
        return {
            "skill": name, "tier": tier,
            "on_resume": name.casefold() in have if candidate_skills is not None else None,
            "status": status, "status_label": LABELS[status],
            "level": plan.get("level"), "estimated_hours": plan.get("estimated_hours"),
            "topics": plan.get("topics", []), "curated_plan": plan.get("curated", False),
            "resource": resources.get(name),
        }

    skills = [skill_entry(s, "core") for s in track["core_skills"]] + \
             [skill_entry(s, "advanced") for s in track.get("advanced_skills", [])]
    questions = []
    for name in all_skills(track):
        for q in questions_for_skill(name)[:2]:
            questions.append({"skill": name, "difficulty": q.get("difficulty"), "question": q["question"]})
    covered = [s for s in skills if s["on_resume"]]
    return {
        **summary(track),
        "advanced_skills": track.get("advanced_skills", []),
        "skills": skills,
        "roadmap": track["roadmap"],
        "exercises": track["exercises"],
        "projects": track["projects"],
        "resume_advice": track["resume_advice"],
        "interview_questions": questions[:12],
        "coverage": ({"on_resume": len(covered), "total": len(skills),
                      "percent": round(100 * len(covered) / len(skills)) if skills else 0}
                     if candidate_skills is not None else None),
        "resources_note": "Links point to official documentation; CareerNova does not host or vouch for third-party courses.",
    }


def relevant_jobs(track: dict[str, Any], internships: list[Internship], limit: int = 10) -> list[tuple[Internship, int]]:
    """Jobs ranked by how many track skills they ask for (+1 when the domain matches). At least 2."""
    wanted = {s.casefold() for s in all_skills(track)}
    domains = {d.casefold() for d in track.get("domains", [])}
    scored = []
    for internship in internships:
        required, preferred = internship_skill_names(internship)
        overlap = len(wanted & {s.casefold() for s in required + preferred})
        score = overlap + (1 if (internship.domain or "").casefold() in domains else 0)
        if score >= 2:
            scored.append((internship, score))
    scored.sort(key=lambda pair: (-pair[1], pair[0].internship_id))
    return scored[:limit]
