"""Compare two versions of a student's resume (HR feedback: multiple resume versions + comparison).

Everything comes from the two resumes' extracted data (the existing parser's output) and is measured with the
same engines for both versions:
* readiness-v1 (``resume_readiness.score_resume``) - general resume quality, per category;
* role coverage (``prep.roles.assess``, roles-v1) when a target role is chosen;
* the ATS report (``ats.ats_report``) against one internship when one is chosen.

Section entries are matched by their first line (title). Same title + different description = modified.
The verdict is only "stronger" when the measured scores differ by at least ``MIN_DIFFERENCE`` points;
otherwise the versions are reported as about equal. Nothing is generated or guessed.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Internship, Resume
from backend.services.ats import ats_report, skill_locations
from backend.services.candidate_profile import latest_completed_extraction
from backend.services.fact_base import NoExtractionError, build_fact_base
from backend.services.prep.context import ResumeContext, short_title
from backend.services.prep.roles import assess
from backend.services.resume_readiness import score_resume
from backend.services.resume_skills import get_resume_skill_rows

ALGORITHM = "compare-v1"
MIN_DIFFERENCE = 5              # readiness points needed to call one version stronger
SECTIONS = [("education", "Education"), ("experience", "Experience"), ("internship", "Internships"),
            ("project", "Projects"), ("certification", "Certifications"), ("achievement", "Achievements")]
CONTACT = [("name", "Full name"), ("email", "Email"), ("phone", "Phone"), ("linkedin", "LinkedIn"),
           ("github", "GitHub"), ("location", "Location")]
SOFT = "soft_skill"


class CompareError(ValueError):
    pass


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _status(a, b) -> str:
    if not a and not b:
        return "missing_in_both"
    if a and not b:
        return "removed"
    if b and not a:
        return "added"
    return "unchanged" if _norm(str(a)) == _norm(str(b)) else "modified"


def _entries(facts, kind: str) -> list[dict[str, Any]]:
    return [{"title": short_title(f.title, 90), "lines": f.lines, "key": _norm(f.title)} for f in facts.of_kind(kind)]


def _match(old: list[dict], new: list[dict]) -> dict[str, list]:
    """added / removed / modified / unchanged entries, matching titles exactly or very closely."""
    result = {"added": [], "removed": [], "modified": [], "unchanged": []}
    remaining = list(new)
    for entry in old:
        best = max(remaining, key=lambda e: difflib.SequenceMatcher(None, entry["key"], e["key"]).ratio(), default=None)
        if best is not None and difflib.SequenceMatcher(None, entry["key"], best["key"]).ratio() >= 0.85:
            remaining.remove(best)
            same = [_norm(x) for x in entry["lines"]] == [_norm(x) for x in best["lines"]]
            if same:
                result["unchanged"].append(best["title"])
            else:
                before, after = {_norm(x) for x in entry["lines"][1:]}, {_norm(x) for x in best["lines"][1:]}
                result["modified"].append({"title": best["title"],
                                           "lines_added": [x for x in best["lines"][1:] if _norm(x) not in before],
                                           "lines_removed": [x for x in entry["lines"][1:] if _norm(x) not in after]})
        else:
            result["removed"].append(entry["title"])
    result["added"] = [e["title"] for e in remaining]
    return result


def _skills(db: Session, resume_id: int) -> dict[str, str]:
    return {skill.name: (skill.category or "other") for _, skill in get_resume_skill_rows(db, resume_id)}


def _version(resume: Resume, data: dict, readiness: dict) -> dict[str, Any]:
    return {"resume_id": resume.resume_id, "filename": resume.filename, "label": resume.label,
            "uploaded_at": resume.uploaded_at, "is_preferred": bool(resume.is_preferred),
            "readiness": {"score": readiness["score"], "label": readiness["label"],
                          "categories": [{"key": c["key"], "label": c["label"], "score": c["score"], "max": c["max"]}
                                         for c in readiness["categories"]]}}


def compare(db: Session, older: Resume, newer: Resume, role: dict | None = None,
            internship: Internship | None = None) -> dict[str, Any]:
    """Compare version ``older`` (A) with ``newer`` (B). Both must be the same student's parsed resumes."""
    sides = []
    for resume in (older, newer):
        extraction = latest_completed_extraction(db, resume.resume_id)
        if extraction is None:
            raise CompareError(f"\"{resume.filename}\" has not been parsed successfully, so it can't be compared.")
        try:
            facts = build_fact_base(db, resume)
        except NoExtractionError:
            raise CompareError(f"\"{resume.filename}\" has no parsed content to compare.") from None
        data = extraction.extracted_data or {}
        sides.append((resume, facts, data, score_resume(data), _skills(db, resume.resume_id)))
    (ra, fa, da, sa, ka), (rb, fb, db_, sb, kb) = sides

    contact = [{"field": key, "label": label, "a": fa.contact.get(key), "b": fb.contact.get(key),
                "status": _status(fa.contact.get(key), fb.contact.get(key))} for key, label in CONTACT]
    tech_a = {s for s, c in ka.items() if c != SOFT}
    tech_b = {s for s, c in kb.items() if c != SOFT}
    soft_a = {s for s, c in ka.items() if c == SOFT}
    soft_b = {s for s, c in kb.items() if c == SOFT}
    skills = {
        "technical": {"added": sorted(tech_b - tech_a), "removed": sorted(tech_a - tech_b), "kept": sorted(tech_a & tech_b)},
        "soft": {"added": sorted(soft_b - soft_a), "removed": sorted(soft_a - soft_b), "kept": sorted(soft_a & soft_b)},
        "count": {"a": len(ka), "b": len(kb)},
    }
    sections = {key: {"label": label, **_match(_entries(fa, key), _entries(fb, key))} for key, label in SECTIONS}
    summary_status = _status((fa.of_kind("summary") or [None])[0] and fa.of_kind("summary")[0].text,
                             (fb.of_kind("summary") or [None])[0] and fb.of_kind("summary")[0].text)
    loc_a, loc_b = skill_locations(fa), skill_locations(fb)
    evidenced_a = {s for s, places in loc_a.items() if any(p != "skills" for p in places)}
    evidenced_b = {s for s, places in loc_b.items() if any(p != "skills" for p in places)}
    keywords = {"added": sorted(set(loc_b) - set(loc_a)), "removed": sorted(set(loc_a) - set(loc_b)),
                "now_backed_by_evidence": sorted(evidenced_b - evidenced_a),
                "lost_evidence": sorted(evidenced_a - evidenced_b)}

    categories = []
    for ca, cb in zip(sa["categories"], sb["categories"]):
        categories.append({"key": ca["key"], "label": ca["label"], "max": ca["max"], "a": ca["score"], "b": cb["score"],
                           "change": round(cb["score"] - ca["score"], 1)})
    metrics: dict[str, Any] = {"readiness": {"algorithm": sa["algorithm"], "a": sa["score"], "b": sb["score"],
                                             "change": round(sb["score"] - sa["score"], 1), "categories": categories}}
    if role is not None:
        fit_a = assess(role, ResumeContext(ra, fa, loc_a))
        fit_b = assess(role, ResumeContext(rb, fb, loc_b))
        metrics["role"] = {"slug": role["slug"], "title": role["title"], "algorithm": fit_a["algorithm"],
                           "a": fit_a["score"], "b": fit_b["score"], "change": fit_b["score"] - fit_a["score"],
                           "missing_a": fit_a["core"]["missing"], "missing_b": fit_b["core"]["missing"]}
    if internship is not None:
        ats_a, ats_b = ats_report(fa, internship), ats_report(fb, internship)

        def ats_summary(r):
            checks = r["checks"]
            return {"required": r["required_coverage"], "preferred": r["preferred_coverage"],
                    "checks_passed": sum(c["passed"] for c in checks), "checks_total": len(checks),
                    "missing_keywords": r["missing_keywords"]}
        metrics["ats"] = {"internship_id": internship.internship_id, "title": internship.title,
                          "company": internship.company, "a": ats_summary(ats_a), "b": ats_summary(ats_b)}

    # Verdict from measured differences only.
    diff = metrics["readiness"]["change"]
    role_diff = metrics.get("role", {}).get("change", 0)
    if abs(diff) >= MIN_DIFFERENCE or abs(role_diff) >= MIN_DIFFERENCE:
        primary = role_diff if abs(role_diff) >= MIN_DIFFERENCE and role is not None else diff
        stronger = "b" if primary > 0 else "a"
    else:
        stronger = None
    better, worse = ("b", "a") if stronger == "b" else ("a", "b")
    reasons = []
    for c in categories:
        delta = c["change"] if stronger != "a" else -c["change"]
        if delta >= 1:
            reasons.append(f"{c['label']}: {c[better]}/{c['max']} vs {c[worse]}/{c['max']}")
    if role is not None and role_diff:
        reasons.append(f"{role['title']} fit: {metrics['role'][better]}/100 vs {metrics['role'][worse]}/100")

    weaker_readiness = sb if stronger == "a" else sa if stronger == "b" else (sa if sa["score"] <= sb["score"] else sb)
    recommendations = list(weaker_readiness.get("recommendations", []))[:5]
    weaknesses_introduced = []
    for key, label in SECTIONS:
        for title in sections[key]["removed"]:
            weaknesses_introduced.append(f"{label[:-1] if label.endswith('s') else label} \"{title[:80]}\" is no longer in version B.")
    for s in skills["technical"]["removed"]:
        weaknesses_introduced.append(f"Skill \"{s}\" was removed in version B.")
    for s in keywords["lost_evidence"]:
        weaknesses_introduced.append(f"\"{s}\" is no longer shown in any project or job in version B.")
    for c in categories:
        if c["change"] <= -1:
            weaknesses_introduced.append(f"{c['label']} score dropped from {c['a']} to {c['b']} (of {c['max']}).")
    improvements = [f"{c['label']} score rose from {c['a']} to {c['b']} (of {c['max']})." for c in categories if c["change"] >= 1]
    improvements += [f"New skill: {s}." for s in skills["technical"]["added"]]
    improvements += [f"New {label.lower()[:-1] if label.endswith('s') else label.lower()}: \"{t[:80]}\"." for key, label in SECTIONS
                     for t in sections[key]["added"]]
    role_advice = []
    if role is not None:
        missing = metrics["role"]["missing_b"] if stronger != "a" else metrics["role"]["missing_a"]
        if missing:
            role_advice.append(f"For {role['title']}, the stronger version still lacks: {', '.join(missing)} - add them only "
                               "if you genuinely have the skill, ideally inside a project.")

    return {
        "algorithm": ALGORITHM,
        "a": _version(ra, da, sa), "b": _version(rb, db_, sb),
        "contact": contact, "summary": summary_status, "skills": skills, "sections": sections, "keywords": keywords,
        "metrics": metrics,
        "verdict": {
            "stronger": stronger,
            "headline": ("About equal: the measured scores differ by less than "
                         f"{MIN_DIFFERENCE} points." if stronger is None else
                         f"Version {'B' if stronger == 'b' else 'A'} is stronger by the measured scores."),
            "reasons": reasons[:8],
            "basis": "readiness-v1 (and role fit / ATS report when chosen), calculated the same way for both versions",
        },
        "improvements_in_b": improvements[:12],
        "weaknesses_introduced_in_b": weaknesses_introduced[:12],
        "recommendations_for_weaker": recommendations,
        "role_advice": role_advice,
        "notes": [
            "Section entries are matched by their first line; a renamed entry shows as removed + added.",
            "Scores are guidance about completeness and evidence, not a prediction of any employer's decision.",
        ] + ([] if internship is not None else ["Choose an internship to compare ATS keyword coverage for that job."]),
    }
