"""Role catalogue (the career tracks) and the resume-based role recommendation engine.

Scoring (``roles-v1``), from the student's own resume only:
* core coverage     = core skills of the role found on the resume / core skills
* advanced coverage = advanced skills found / advanced skills
* fit score         = round(100 * (0.75 * core coverage + 0.25 * advanced coverage))
* evidence          = role skills that also appear in a project, experience, internship,
                      certification or achievement (not only in the skills list)
Readiness labels: >= 70 ready to apply, >= 45 close, >= 25 possible with focused learning, else
a longer-term goal. Education is reported when it is relevant but never changes the score.
"""

from __future__ import annotations

import re
from typing import Any

from backend.services import career_tracks
from backend.services.prep.context import ResumeContext

ALGORITHM = "roles-v1"

# Extra names people use for the roles (matched as whole words, case-insensitive).
ALIASES: dict[str, list[str]] = {
    "software-developer": ["software engineer", "software developer", "sde", "software development engineer", "programmer"],
    "ai-engineer": ["ai engineer", "ai/ml engineer", "ai ml engineer", "artificial intelligence engineer", "genai engineer",
                    "llm engineer", "ai developer"],
    "machine-learning-engineer": ["machine learning engineer", "ml engineer", "mle", "machine learning developer"],
    "data-scientist": ["data scientist", "data science"],
    "data-analyst": ["data analyst", "business analyst", "data analytics", "bi analyst"],
    "web-developer": ["web developer", "web development"],
    "java-developer": ["java developer", "java engineer", "spring developer", "java"],
    "python-developer": ["python developer", "python engineer", "django developer", "python"],
    "cybersecurity-analyst": ["cybersecurity analyst", "security analyst", "cyber security", "cybersecurity", "soc analyst"],
    "cloud-engineer": ["cloud engineer", "cloud developer", "aws engineer", "cloud"],
    "devops-engineer": ["devops engineer", "devops", "site reliability engineer", "sre"],
    "frontend-developer": ["frontend developer", "front end developer", "front-end developer", "frontend engineer",
                           "ui developer", "react developer", "frontend", "front end", "front-end"],
    "backend-developer": ["backend developer", "back end developer", "back-end developer", "backend engineer",
                          "api developer", "backend", "back end", "back-end"],
    "full-stack-developer": ["full stack developer", "full-stack developer", "fullstack developer", "full stack engineer",
                             "mern developer", "full stack", "full-stack", "fullstack"],
}

RELEVANT_EDUCATION = re.compile(r"\b(computer|information|software|data|artificial intelligence|machine learning|"
                                r"electronics|(?-i:IT)|mca|bca|b\.?tech|m\.?tech|engineering|statistics|mathematics)\b", re.I)


def tracks() -> list[dict[str, Any]]:
    return career_tracks.load_tracks()


def _patterns() -> list[tuple[re.Pattern, str]]:
    pairs = []
    for track in tracks():
        names = {track["title"].lower(), *ALIASES.get(track["slug"], [])}
        for name in names:
            pairs.append((re.compile(r"(?<![a-z0-9])" + re.escape(name).replace(r"\ ", r"[\s-]+") + r"(?![a-z0-9])"),
                          track["slug"]))
    # Longest names first so "java developer" wins over "java" and "full stack" over "stack".
    pairs.sort(key=lambda p: -len(p[0].pattern))
    return pairs


_PATTERNS: list[tuple[re.Pattern, str]] | None = None


def find_role(text: str) -> dict[str, Any] | None:
    """The role named in the text (title or alias), or None."""
    global _PATTERNS
    if _PATTERNS is None:
        _PATTERNS = _patterns()
    lowered = (text or "").lower()
    for pattern, slug in _PATTERNS:
        if pattern.search(lowered):
            return career_tracks.get_track(slug)
    return None


def readiness(score: int) -> dict[str, str]:
    if score >= 70:
        return {"level": "ready", "label": "Ready to apply"}
    if score >= 45:
        return {"level": "close", "label": "Close - a few skills to add"}
    if score >= 25:
        return {"level": "possible", "label": "Possible with focused learning"}
    return {"level": "long_term", "label": "Longer-term goal"}


def assess(track: dict[str, Any], ctx: ResumeContext) -> dict[str, Any]:
    core, advanced = track["core_skills"], track.get("advanced_skills", [])
    core_have = [s for s in core if ctx.has(s)]
    adv_have = [s for s in advanced if ctx.has(s)]
    core_missing = [s for s in core if not ctx.has(s)]
    adv_missing = [s for s in advanced if not ctx.has(s)]
    core_cov = len(core_have) / len(core) if core else 0.0
    adv_cov = len(adv_have) / len(advanced) if advanced else 0.0
    score = round(100 * (0.75 * core_cov + 0.25 * adv_cov))
    evidence = {s: ctx.evidence(s) for s in core_have + adv_have if ctx.evidence(s)}

    reasons = []
    if core_have:
        reasons.append(f"Your resume shows {len(core_have)} of the {len(core)} core skills: {', '.join(core_have)}.")
    else:
        reasons.append(f"None of the {len(core)} core skills ({', '.join(core)}) appear on your resume yet.")
    for skill, places in list(evidence.items())[:3]:
        reasons.append(f"You used {skill} in: {places[0]['title']}.")
    if adv_have:
        reasons.append(f"Advanced skills you already have: {', '.join(adv_have)}.")
    education = ctx.facts.degree or next((f.title for f in ctx.facts.of_kind("education")), None)
    if education and RELEVANT_EDUCATION.search(education):
        reasons.append(f"Your education ({education[:100]}) is relevant to this role.")

    return {
        "slug": track["slug"], "title": track["title"], "summary": track["summary"],
        "score": score, "readiness": readiness(score), "algorithm": ALGORITHM,
        "core": {"have": core_have, "missing": core_missing, "total": len(core)},
        "advanced": {"have": adv_have, "missing": adv_missing, "total": len(advanced)},
        "evidence": evidence,
        "reasons": reasons,
        "improve": core_missing[:4] + adv_missing[:2],
        "resume_id": ctx.resume.resume_id,
    }


def recommend(ctx: ResumeContext, limit: int = 5) -> list[dict[str, Any]]:
    """Roles ranked by fit (score, then skills with project/experience evidence, then title)."""
    ranked = [assess(t, ctx) for t in tracks()]
    ranked.sort(key=lambda a: (-a["score"], -len(a["evidence"]), a["title"]))
    return ranked[:limit]
