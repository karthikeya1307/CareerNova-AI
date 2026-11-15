"""ATS (applicant tracking system) report for a resume and an internship.

Keyword coverage uses the internship's required and preferred skills.
Missing keywords are reported with "add only if true" guidance; they are
never inserted into a document as claims.
"""

from __future__ import annotations

import re
from typing import Any

from backend.models import Internship
from backend.services.fact_base import CandidateFacts
from backend.services.fact_check import skill_mentions
from backend.services.internship_text import internship_skill_names

MAX_RECOMMENDED_WORDS = 800
QUANTIFIED_RE = re.compile(r"\d")


def skill_locations(facts: CandidateFacts) -> dict[str, list[str]]:
    """Canonical skill (casefold) -> where it appears ('skills' or fact ids)."""
    where: dict[str, list[str]] = {}
    for skill in facts.skills:
        where.setdefault(skill.casefold(), []).append("skills")
    for fact in facts.facts:
        for skill in skill_mentions(fact.text):
            where.setdefault(skill.casefold(), []).append(fact.id)
    return where


def ats_report(facts: CandidateFacts, internship: Internship) -> dict[str, Any]:
    required, preferred = internship_skill_names(internship)
    where = skill_locations(facts)

    def coverage(skills: list[str], importance: str) -> list[dict[str, Any]]:
        return [
            {"skill": s, "importance": importance, "present": s.casefold() in where,
             "found_in": where.get(s.casefold(), [])}
            for s in skills
        ]

    keywords = coverage(required, "required") + coverage(preferred, "preferred")
    missing = [k for k in keywords if not k["present"]]

    bullets = [line for f in facts.of_kind("experience", "internship", "project") for line in f.body]
    unquantified = [line for line in bullets if not QUANTIFIED_RE.search(line)]
    words = sum(len(f.text.split()) for f in facts.facts)

    checks = [
        {"check": "contact_email", "passed": bool(facts.contact.get("email")),
         "detail": "An e-mail address is present." if facts.contact.get("email") else "Add an e-mail address."},
        {"check": "contact_phone", "passed": bool(facts.contact.get("phone")),
         "detail": "A phone number is present." if facts.contact.get("phone") else "Add a phone number."},
        {"check": "summary", "passed": bool(facts.of_kind("summary")),
         "detail": "A professional summary is present." if facts.of_kind("summary")
         else "Add a short professional summary."},
        {"check": "skills_section", "passed": bool(facts.skills),
         "detail": f"{len(facts.skills)} recognised skills." if facts.skills else "Add a skills section."},
        {"check": "education", "passed": bool(facts.of_kind("education")),
         "detail": "Education is present." if facts.of_kind("education") else "Add your education."},
        {"check": "experience_or_projects", "passed": bool(bullets),
         "detail": "Experience or projects are present." if bullets
         else "Add experience, internships or projects with short descriptions."},
        {"check": "length", "passed": words <= MAX_RECOMMENDED_WORDS,
         "detail": f"About {words} words." + ("" if words <= MAX_RECOMMENDED_WORDS
                                             else " Consider shortening to one page.")},
    ]

    suggestions = [
        f"Add {k['skill']} ({k['importance']}) only if you genuinely have this skill; "
        "otherwise consider learning it (see your skill-gap plan)."
        for k in missing
    ]
    if unquantified:
        suggestions.append(
            f"{len(unquantified)} experience/project lines have no measurable outcome. "
            "Add real numbers (users, time saved, accuracy) only where you have them."
        )

    req_present = sum(k["present"] for k in keywords if k["importance"] == "required")
    pref_present = sum(k["present"] for k in keywords if k["importance"] == "preferred")
    return {
        "required_coverage": {"present": req_present, "total": len(required)},
        "preferred_coverage": {"present": pref_present, "total": len(preferred)},
        "keywords": keywords,
        "missing_keywords": [k["skill"] for k in missing],
        "checks": checks,
        "suggestions": suggestions,
        "format_notes": [
            "Single-column layout with standard section headings.",
            "No tables, images, text boxes, headers or footers.",
            "Plain bullet points and consistent wording.",
        ],
    }
