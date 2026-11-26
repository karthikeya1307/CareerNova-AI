"""Per-job insights for a resume (algorithm ``insights-v1``), used by both matching modes.

Built only from the internship record, the resume's normalized skills, the compatibility
breakdown (education/location components) and the general readiness score. Nothing is invented:
a skill counts as matched only when it is on the resume; "partial" means a closely related skill
is on the resume (curated list in skill_relations.py).

* Skill Match (0-100) = 100 x (0.8 x required share + 0.2 x preferred share), where a matched
  skill counts 1 and a partial one 0.5. With only required (or only preferred) skills listed, that
  share alone is used. None when the posting lists no skills.
* Eligibility from the education requirement (compatibility component) and the deadline:
  eligible | open (no requirement stated) | check (partly meets / different subject) |
  unknown (degree not readable from the resume) | not_eligible | closed.
* Application Readiness (0-100) = 0.6 x Skill Match + 0.25 x resume readiness + 0.15 x eligibility
  value (eligible/open 100, check 60, unknown 50, not eligible/closed 0); without a readiness score
  the weights are 0.8 / 0.2. It is guidance, not a prediction of selection.
* Category: Apply Now (Skill Match >= 70, no fully missing required skill, eligible or open),
  Long-Term Target (not eligible, closed, or Skill Match < 40 with 3+ missing required skills),
  otherwise Apply After Improvement.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.models import Internship
from backend.services import job_sources
from backend.services.learning_plans import plan_for
from backend.services.skill_gap import assess_internship

ALGORITHM = "insights-v1"
ELIGIBILITY_VALUE = {"eligible": 100, "open": 100, "check": 60, "unknown": 50, "not_eligible": 0, "closed": 0}
ELIGIBILITY_LABEL = {
    "eligible": "Eligible", "open": "No education requirement stated", "check": "Check the requirement",
    "unknown": "Couldn't confirm your degree", "not_eligible": "Below the stated requirement", "closed": "Closed",
}
CATEGORY_LABEL = {"apply_now": "Apply Now", "improve": "Apply After Improvement", "long_term": "Long-Term Target"}


def _share(items: list, total: int) -> float:
    return sum(1.0 if i.status == "matched" else 0.5 if i.status == "partial" else 0.0 for i in items) / total


def skill_match(assessments: list) -> int | None:
    required = [a for a in assessments if a.importance == "required"]
    preferred = [a for a in assessments if a.importance == "preferred"]
    if not required and not preferred:
        return None
    if required and preferred:
        value = 0.8 * _share(required, len(required)) + 0.2 * _share(preferred, len(preferred))
    else:
        group = required or preferred
        value = _share(group, len(group))
    return round(100 * value)


def eligibility(internship: Internship, breakdown: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    deadline = internship.deadline
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if not internship.is_active or (deadline is not None and deadline < now):
        status = "closed"
        detail = "This opportunity is no longer open."
    else:
        component = next((c for c in breakdown.get("components", []) if c.get("name") == "education"), None)
        if component is None or component.get("status") == "not_stated":
            status, detail = "open", "The posting does not state an education requirement."
        elif component.get("status") == "unknown":
            status = "unknown"
            detail = component.get("detail") or "Your degree could not be read from the resume or profile."
        else:
            score = component.get("score", 0)
            status = "eligible" if score >= 0.8 else "check" if score >= 0.5 else "not_eligible"
            detail = component.get("detail") or ""
    return {"status": status, "label": ELIGIBILITY_LABEL[status], "detail": detail,
            "requirement": internship.min_education}


def build(internship: Internship, breakdown: dict, candidate_skills: list[str],
          readiness_score: int | None, now: datetime | None = None,
          evidence: dict[str, list[str]] | None = None) -> dict:
    """``evidence``: skill (casefold) -> titles of the resume's projects / experience entries that mention it."""
    assessments = assess_internship(candidate_skills, internship)
    matched = [a for a in assessments if a.status == "matched"]
    partial = [a for a in assessments if a.status == "partial"]
    missing = [a for a in assessments if a.status == "missing"]
    missing_required = [a for a in missing if a.importance == "required"]
    required_total = sum(1 for a in assessments if a.importance == "required")

    match = skill_match(assessments)
    elig = eligibility(internship, breakdown, now)
    if readiness_score is None:
        readiness = round(0.8 * (match or 0) + 0.2 * ELIGIBILITY_VALUE[elig["status"]])
    else:
        readiness = round(0.6 * (match or 0) + 0.25 * readiness_score + 0.15 * ELIGIBILITY_VALUE[elig["status"]])

    if elig["status"] in ("not_eligible", "closed") or (
            (match or 0) < 40 and len(missing_required) >= 3):
        category = "long_term"
    elif (match or 0) >= 70 and not missing_required and elig["status"] in ("eligible", "open"):
        category = "apply_now"
    else:
        category = "improve"

    reasons: list[str] = []
    if required_total:
        have = sum(1 for a in matched if a.importance == "required")
        reasons.append(f"You have {have} of {required_total} required skills"
                       + (f": {', '.join(a.skill for a in matched if a.importance == 'required')}." if have else "."))
    preferred_matched = [a.skill for a in matched if a.importance == "preferred"]
    if preferred_matched:
        reasons.append(f"Preferred skills you have: {', '.join(preferred_matched)}.")
    for a in partial[:3]:
        related = ", ".join(r["skill"] for r in a.related[:2])
        reasons.append(f"{a.skill}: partly covered by your experience with {related}.")
    if elig["detail"]:
        reasons.append(f"Education: {elig['detail']}")
    for component in breakdown.get("components", []):
        if component.get("name") == "location" and component.get("status") == "assessed" and component.get("detail"):
            reasons.append(f"Location: {component['detail']}")

    improvements: list[str] = []
    for a in (missing_required + [m for m in missing if m.importance == "preferred"])[:4]:
        plan = plan_for(a.skill)
        first = (plan.get("topics") or [None])[0]
        hours = plan.get("estimated_hours")
        why = "required" if a.importance == "required" else "preferred"
        improvements.append(f"Learn {a.skill} ({why} for this role)"
                            + (f" - start with: {first}" if first else "")
                            + (f" (about {hours} hours)." if hours else ".")
                            + " It was not found in your resume - if you already use it, add it to a project or "
                              "experience entry instead.")
    for a in partial[:2]:
        improvements.append(f"Show {a.skill} directly in a project or experience entry; related skills only count half.")
    if readiness_score is not None and readiness_score < 70:
        improvements.append(f"Strengthen your resume first (readiness {readiness_score}/100) - see the resume readiness report.")

    # Where the resume shows the matched (and partly matched) skills - projects and experience, not just the list.
    evidence = evidence or {}
    relevant: dict[str, list[str]] = {}
    for a in matched + partial:
        names = [a.skill] + [r["skill"] for r in a.related]
        places = []
        for name in names:
            for title in evidence.get(name.casefold(), []):
                if title not in places:
                    places.append(title)
        if places:
            relevant[a.skill] = places[:3]
    for skill, places in list(relevant.items())[:2]:
        reasons.append(f"Your resume shows {skill} in: {places[0]}.")
    listed_only = [a.skill for a in matched if a.skill not in relevant]

    return {
        "algorithm": ALGORITHM,
        "relevant_experience": [{"skill": k, "where": v} for k, v in relevant.items()],
        "listed_only_skills": listed_only,       # matched, but only in the skills list (no project/experience shows it)
        "skill_match": match,
        "eligibility": elig,
        "application_readiness": readiness,
        "category": category,
        "category_label": CATEGORY_LABEL[category],
        "matched_skills": [{"skill": a.skill, "importance": a.importance} for a in matched],
        "partial_skills": [{"skill": a.skill, "importance": a.importance,
                            "related": [r["skill"] for r in a.related]} for a in partial],
        "missing_skills": [{"skill": a.skill, "importance": a.importance,
                            "note": "Not found in your resume (this does not mean you lack the skill)."}
                           for a in missing],
        "reasons": reasons,
        "improvements": improvements,
        "application_url": internship.application_url,
        "source": internship.source,
        "source_label": job_sources.source_label(internship),
        "source_url": internship.source_url,
        "posted_at": internship.posted_at,
        "last_verified_at": internship.last_verified_at,
        "freshness": job_sources.freshness(internship, now),
        "listed_at": internship.created_at,
        "last_updated": internship.updated_at,
        "deadline": internship.deadline,
    }
