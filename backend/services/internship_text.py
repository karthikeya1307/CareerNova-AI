"""Build the text that represents an internship in the vector index.

Skills are listed plainly because resume queries are mostly skills.
The same function is used for indexing and for RAG context, so what is
retrieved is exactly what was embedded.
"""

from __future__ import annotations

import hashlib

from backend.models import Internship


def internship_skill_names(internship: Internship) -> tuple[list[str], list[str]]:
    required, preferred = [], []

    for link in sorted(internship.skill_links, key=lambda l: l.skill.name.casefold()):
        if link.importance == "preferred":
            preferred.append(link.skill.name)
        else:
            required.append(link.skill.name)

    return required, preferred


def build_internship_text(internship: Internship) -> str:
    required, preferred = internship_skill_names(internship)

    lines = [f"{internship.title} at {internship.company}"]

    if internship.domain:
        lines.append(f"Domain: {internship.domain}")
    if required:
        lines.append(f"Required skills: {', '.join(required)}")
    if preferred:
        lines.append(f"Preferred skills: {', '.join(preferred)}")
    if internship.min_education:
        lines.append(f"Minimum education: {internship.min_education}")
    if internship.location or internship.work_mode:
        where = ", ".join(v for v in [internship.location, internship.work_mode] if v)
        lines.append(f"Location: {where}")
    if internship.eligibility:
        lines.append(f"Eligibility: {internship.eligibility}")
    if internship.description:
        lines.append(internship.description.strip())

    return "\n".join(lines)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
