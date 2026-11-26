"""Answer guidance for one interview question: what the interviewer expects, points to mention, an
answer structure, a sample answer and common mistakes.

Two kinds of content are kept apart in every response:
* ``from_your_resume`` - verified facts from the student's own resume they can use, and
* ``sample_answer``    - a generic sample (``is_sample: True``) built from the curated bank or guide.
The agent never writes experiences or achievements the resume does not contain.
"""

from __future__ import annotations

from typing import Any

from backend.services.prep.context import ResumeContext, short_title
from backend.services.prep.questions import LEVEL_OF, bank_index, hr_guide

TECH_STRUCTURE = [
    "Define the concept in one or two sentences.",
    "Explain how it works or the key difference, using the points below.",
    "Give a short example - from your own project if you really used it.",
    "Mention a trade-off, a limitation or when you would choose it.",
]
TECH_MISTAKES = [
    "Reciting a memorised definition without an example.",
    "Claiming hands-on experience that you cannot discuss in detail.",
    "Answering a different question than the one asked - check you covered every part.",
]
PROJECT_GUIDE = {
    "expects": "That you understand your own work: the problem, your decisions and trade-offs, and the result.",
    "points": ["The problem and who it was for", "Your exact contribution", "The stack and why you chose it",
               "One difficulty and how you solved it", "The result, and what you would improve next"],
    "structure": ["Problem (1-2 sentences)", "Your approach and technology choices", "Challenge and solution",
                  "Result and next improvement"],
    "mistakes": ["Listing tools without explaining why you used them", "Taking credit for teammates' work",
                 "Inventing metrics - quote numbers only if you measured them"],
}


def _resume_material(ctx: ResumeContext, skill: str | None = None) -> list[dict[str, str]]:
    """Verified resume facts the student can draw on (titles only)."""
    out = []
    if skill:
        for place in ctx.evidence(skill)[:3]:
            out.append({"fact_id": place["fact_id"], "text": f"{place['kind'].title()}: {place['title']}"})
        return out
    if ctx.facts.degree:
        out.append({"fact_id": "degree", "text": f"Education: {ctx.facts.degree}"})
    for fact in ctx.facts.of_kind("project", "internship", "experience")[:3]:
        out.append({"fact_id": fact.id, "text": f"{fact.kind.title()}: {short_title(fact.title, 120)}"})
    if ctx.skills:
        out.append({"fact_id": "skills", "text": f"Skills: {', '.join(ctx.skills[:8])}"})
    for fact in ctx.facts.of_kind("certification", "achievement")[:2]:
        out.append({"fact_id": fact.id, "text": f"{fact.kind.title()}: {short_title(fact.title, 120)}"})
    return out


def _about_yourself_draft(ctx: ResumeContext, track: dict[str, Any] | None) -> str | None:
    """A draft assembled ONLY from resume facts, for the student to rewrite in their own words."""
    parts = []
    if ctx.facts.degree:
        degree, *rest = [p.strip() for p in ctx.facts.degree.split(",")]
        place = next((p for p in rest if not any(ch.isdigit() for ch in p)), None)
        parts.append(f"I'm studying {degree}{f' at {place}' if place else ''}.")
    # Role skills in the role's own order (core first), then any resume skills.
    role_order = (track["core_skills"] + track.get("advanced_skills", [])) if track else []
    relevant = [s for s in role_order if ctx.has(s)] or ctx.skills
    if relevant:
        parts.append(f"I work mainly with {', '.join(relevant[:3])}.")
    work = next(iter(ctx.facts.of_kind("project", "internship", "experience")), None)
    if work is not None:
        parts.append(f"For example, in \"{short_title(work.title)}\" I [describe your contribution and the result].")
    if track:
        parts.append(f"I'm now looking for a {track['title']} role where I can [what you want to learn or contribute].")
    return " ".join(parts) if parts else None


def guidance(question_id: str, ctx: ResumeContext, track: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Guidance for a bank question id, an HR guide id or a project question id (proj-<fact id>)."""
    q = bank_index().get(question_id)
    if q is not None:
        points = [p["point"] for p in q["key_points"]]
        misconceptions = [f"Getting this wrong - remember: {m['note']}" for p in q["key_points"] for m in p.get("misconceptions", [])]
        on_resume = ctx.has(q["skill"])
        return {
            "id": question_id, "kind": "technical", "question": q["question"], "skill": q["skill"],
            "level": LEVEL_OF.get(q["difficulty"], q["difficulty"]),
            "expects": f"A correct, clear explanation of {q['skill']}: {q['explanation']}",
            "points": points,
            "structure": TECH_STRUCTURE,
            "sample_answer": {"is_sample": True,
                              "label": "Sample answer (general knowledge, not your personal experience)",
                              "text": " ".join(p.rstrip(".") + "." for p in points) + " " + q["explanation"]},
            "mistakes": misconceptions[:3] + TECH_MISTAKES[: max(1, 4 - len(misconceptions[:3]))],
            "from_your_resume": _resume_material(ctx, q["skill"]),
            "note": None if on_resume else f"{q['skill']} is not on your resume - answer from what you have learned and be honest about your level.",
        }
    if question_id.startswith("proj-"):
        fact = ctx.facts.by_id.get(question_id[5:])
        if fact is None:
            return None
        return {"id": question_id, "kind": "project", "question": f"Walk me through \"{short_title(fact.title)}\".",
                **PROJECT_GUIDE,
                "sample_answer": {"is_sample": True, "label": "Answer outline (fill in your real details)",
                                  "text": "The problem was [...]. I was responsible for [...]. I chose [...] because [...]. "
                                          "The hardest part was [...], which I solved by [...]. The result was [...]; "
                                          "next I would [...]."},
                "from_your_resume": [{"fact_id": fact.id, "text": line} for line in fact.lines[:5]],
                "note": "Only the lines above come from your resume; fill the outline with what really happened."}
    hr = next((h for h in hr_guide()["questions"] if h["id"] == question_id), None)
    if hr is None:
        return None
    draft = _about_yourself_draft(ctx, track) if hr["theme"] == "about_yourself" else None
    return {
        "id": question_id, "kind": "hr", "question": hr["question"], "theme": hr["theme"],
        "expects": hr["expects"], "points": hr["points"], "structure": hr["structure"], "mistakes": hr["mistakes"],
        "sample_answer": ({"is_sample": False, "label": "Draft built only from your resume - rewrite it in your own words",
                           "text": draft} if draft else
                          {"is_sample": True, "label": "How to build your answer",
                           "text": "Follow the structure above with one real example from your studies, projects or work."}),
        "from_your_resume": _resume_material(ctx),
        "note": None,
    }
