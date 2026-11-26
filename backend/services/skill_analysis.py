"""Role-specific skills and gaps analysis (Skills & Gaps page).

For the student's preferred (else newest parsed) resume and a chosen target role (one of the 14 curated career
tracks: Java Developer, Frontend Developer, Python Developer, AI Engineer, Full Stack Developer, ...):

* current skills grouped into Programming languages / Frontend / Backend / Databases / AI/ML / Cloud & DevOps /
  Tools & frameworks / CS fundamentals / Other;
* for every skill: **demonstrated** (a project, job, internship, certification or achievement mentions it),
  **listed** (only in the skills list) or, for role skills, **not found in your resume** - which is NOT the same as
  "you don't have it";
* the role's requirements (core = must-have, advanced = strengthens the application) with their status;
* gaps with a priority, why the skill matters for this role, what to learn (the role roadmap), a practical task (the
  role's own exercises/projects) and how to add it to the resume after genuinely completing it.

Everything comes from the resume and the curated role data; nothing is scored by hand or inflated. Without a target
role the analysis is clearly labelled "general" and lists no gaps.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.services import career_tracks
from backend.services.prep.context import load_context
from backend.services.prep.roles import assess
from backend.services.skill_normalizer import normalize_skill

GROUPS = ["Programming languages", "Frontend", "Backend", "Databases", "AI/ML", "Cloud & DevOps",
          "Tools & frameworks", "CS fundamentals", "Other"]
FRONTEND = {"react", "angular", "next.js", "vue.js", "vue", "bootstrap", "react native", "flutter", "tailwind css",
            "html", "css", "redux", "typescript"}
BACKEND = {"node.js", "express.js", "django", "flask", "fastapi", "spring boot", "spring", ".net", "rest api",
           "graphql", "microservices", "laravel"}
CATEGORY_GROUP = {"programming_language": "Programming languages", "database": "Databases", "data_ml": "AI/ML",
                  "cloud_devops": "Cloud & DevOps", "tool": "Tools & frameworks", "testing": "Tools & frameworks",
                  "framework": "Tools & frameworks", "web": "Frontend", "cs_fundamentals": "CS fundamentals"}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class AnalysisError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def group_of(skill: str) -> str:
    key = skill.casefold()
    if key in FRONTEND:
        return "Frontend"
    if key in BACKEND:
        return "Backend"
    normalized = normalize_skill(skill)
    category = normalized.category if normalized else "other"
    if category == "programming_language" and key in ("typescript",):
        return "Frontend"
    return CATEGORY_GROUP.get(category, "Other")


def _status(ctx, skill: str) -> tuple[str, list[str]]:
    places = [p["title"] for p in ctx.evidence(skill)]
    if places:
        return "demonstrated", places[:3]
    return ("listed", []) if ctx.has(skill) else ("not_found", [])


def _stage_for(track: dict, skill: str) -> dict | None:
    return next((s for s in track.get("roadmap", []) if skill.casefold() in {x.casefold() for x in s.get("skills", [])}),
                None)


def _task_for(track: dict, skill: str) -> str | None:
    key = skill.casefold()
    for text in track.get("exercises", []) + track.get("projects", []):
        if key in text.casefold():
            return text
    return (track.get("projects") or track.get("exercises") or [None])[0]


def _gap(track: dict, skill: str, importance: str, status: str) -> dict[str, Any]:
    if status == "not_found":
        priority = "high" if importance == "core" else "medium"
    else:                                                   # listed but not shown in any project/experience
        priority = "medium" if importance == "core" else "low"
    stage = _stage_for(track, skill)
    why = (f"{skill} is a core skill for a {track['title']}: {track['summary']}" if importance == "core" else
           f"{skill} is an advanced skill that strengthens a {track['title']} application.")
    learn = (f"Roadmap stage \"{stage['stage']}\": {stage['goal']}" if stage else
             f"Learn the fundamentals of {skill} and use it in a small project.")
    if status == "listed":
        resume_tip = (f"Your resume lists {skill} but no project or experience shows it. Describe where you actually "
                      f"used {skill} in a project entry (problem, what you built, result).")
        headline = "Listed but not demonstrated"
    else:
        resume_tip = (f"After you have genuinely built the task, add {skill} to your Skills section and describe the "
                      f"project with the problem, what you built with {skill} and the result.")
        headline = "Not found in your resume"
    return {"skill": skill, "importance": importance, "status": status, "headline": headline, "priority": priority,
            "why": why, "learn": learn, "practice": _task_for(track, skill), "resume_tip": resume_tip,
            "stage_index": track.get("roadmap", []).index(stage) if stage else 99}


def analyse(db: Session, user_id: int, role_slug: str | None = None, resume_id: int | None = None) -> dict[str, Any]:
    ctx = load_context(db, user_id, resume_id)
    if ctx is None:
        raise AnalysisError("resume_required", "Upload a resume and wait for it to be parsed first.")
    grouped: dict[str, list[dict]] = {g: [] for g in GROUPS}
    for skill in sorted(ctx.skills, key=str.casefold):
        normalized = normalize_skill(skill)
        if normalized is not None and normalized.category == "soft_skill":
            continue
        status, places = _status(ctx, skill)
        grouped[group_of(skill)].append({"skill": skill, "status": status, "where": places})
    current = [{"group": g, "skills": items} for g, items in grouped.items() if items]
    roles = [{"slug": t["slug"], "title": t["title"]} for t in career_tracks.load_tracks()]
    base = {"resume": {"resume_id": ctx.resume.resume_id, "filename": ctx.resume.filename,
                       "label": ctx.resume.label}, "current_skills": current, "roles": roles,
            "counts": {"demonstrated": sum(1 for g in current for s in g["skills"] if s["status"] == "demonstrated"),
                       "listed": sum(1 for g in current for s in g["skills"] if s["status"] == "listed")}}
    if not role_slug:
        return {**base, "mode": "general", "role": None, "requirements": [], "gaps": [], "learning_priorities": [],
                "note": "General analysis - choose a target role to see the skills that role needs and your gaps."}
    track = career_tracks.get_track(role_slug)
    if track is None:
        raise AnalysisError("unknown_role", "Unknown role. Choose one of the listed roles.")
    requirements, gaps = [], []
    for importance, skills in (("core", track["core_skills"]), ("advanced", track.get("advanced_skills", []))):
        for skill in skills:
            status, places = _status(ctx, skill)
            requirements.append({"skill": skill, "importance": importance, "status": status, "where": places,
                                 "group": group_of(skill)})
            if status != "demonstrated":
                gaps.append(_gap(track, skill, importance, status))
    gaps.sort(key=lambda g: (PRIORITY_ORDER[g["priority"]], g["stage_index"], g["skill"].casefold()))
    for g in gaps:
        g.pop("stage_index")
    fit = assess(track, ctx)
    core = [r for r in requirements if r["importance"] == "core"]
    advanced = [r for r in requirements if r["importance"] == "advanced"]
    return {
        **base, "mode": "role",
        "role": {"slug": track["slug"], "title": track["title"], "summary": track["summary"]},
        "fit": {"score": fit["score"], "algorithm": fit["algorithm"],
                "basis": "75% core-skill coverage + 25% advanced-skill coverage (skills found in your resume)",
                "core_found": sum(1 for r in core if r["status"] != "not_found"), "core_total": len(core),
                "core_demonstrated": sum(1 for r in core if r["status"] == "demonstrated"),
                "advanced_found": sum(1 for r in advanced if r["status"] != "not_found"), "advanced_total": len(advanced)},
        "requirements": requirements,
        "gaps": gaps,
        "learning_priorities": [g["skill"] for g in gaps if g["priority"] != "low"][:6],
        "resume_advice": track.get("resume_advice", []),
        "note": ("\"Not found in your resume\" means the resume does not mention the skill - it does not mean you "
                 "lack it. Add skills you genuinely have, ideally inside a project or experience entry."),
    }
