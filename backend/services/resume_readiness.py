"""General Resume Readiness score (0-100), algorithm ``readiness-v1``.

A transparent check of how complete and well-evidenced a resume is, independent of any job.
It is NOT a prediction of any particular employer's applicant-tracking system and does not
guarantee interviews; job-specific fit is the separate compatibility score.

Categories and maximum points (total 100):

| Category                        | Max | Points for                                                      |
|---------------------------------|-----|-----------------------------------------------------------------|
| Contact and profile             | 10  | name 3, email 3, phone 2, LinkedIn/GitHub 2                     |
| Structure and completeness      | 15  | summary, skills, education, experience/internships, projects: 3 each |
| Skills and evidence             | 20  | number of skills (up to 8) + share of skills shown in experience/projects (12) |
| Experience and internships      | 15  | has an entry 5 + dated share 4 + action-verb share 3 + quantified-result share 3 |
| Projects                        | 15  | has a project 5 + a second project 2 + described share 4 + share naming a technology 4 |
| Education                       | 10  | entry 4 + recognised degree 3 + year 3                          |
| Certifications and achievements |  5  | certification 3 + achievement 2                                 |
| Formatting and readability      | 10  | parsing confidence (up to 5), no parsing warnings 2, summary 40-600 chars 1, skills list not padded 1, clean contact line 1 |

Shares are computed per entry, so empty or one-word entries earn nothing. Labels: 85+ Excellent,
70+ Good, 50+ Fair, below 50 Needs work.
"""

from __future__ import annotations

import re
from datetime import date

from backend.services.compatibility import classify_degree
from backend.services.resume_insights import _text, analyze, parse_dates

ALGORITHM = "readiness-v1"
DISCLAIMER = ("General resume readiness based on completeness and evidence in your resume. It is not a "
              "prediction of any specific employer's applicant-tracking system and does not guarantee an interview.")
ACTION_VERBS = re.compile(
    r"\b(built|developed|designed|implemented|created|led|managed|improved|reduced|increased|deployed|automated|"
    r"analy[sz]ed|optimi[sz]ed|delivered|launched|trained|wrote|tested|migrated|integrated|engineered|"
    r"maintained|refactored|researched|coordinated|organi[sz]ed|presented|achieved|won|mentored)\b", re.IGNORECASE)
QUANTIFIED = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent|x\b|\+|users|clients|ms|hours|days|teams|k\b|m\b)|\b\d{2,}\b",
                        re.IGNORECASE)
LABELS = [(85, "Excellent"), (70, "Good"), (50, "Fair"), (0, "Needs work")]


class Category:
    def __init__(self, key: str, label: str, maximum: int):
        self.key, self.label, self.maximum = key, label, maximum
        self.points: list[dict] = []
        self.recommendations: list[str] = []

    def award(self, points: float, reason: str) -> None:
        self.points.append({"points": round(points, 1), "reason": reason, "earned": True})

    def miss(self, points: float, reason: str, recommendation: str | None = None) -> None:
        self.points.append({"points": round(points, 1), "reason": reason, "earned": False})
        if recommendation:
            self.recommendations.append(recommendation)

    def partial(self, earned: float, maximum: float, reason: str, recommendation: str | None = None) -> None:
        if earned > 0:
            self.award(earned, reason)
        if maximum - earned > 0.05:
            self.miss(maximum - earned, reason, recommendation)

    @property
    def score(self) -> float:
        return round(min(self.maximum, sum(p["points"] for p in self.points if p["earned"])), 1)

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "score": self.score, "max": self.maximum,
                "points": self.points, "recommendations": self.recommendations}


def _share(items: list[str], test) -> float:
    return sum(1 for i in items if test(i)) / len(items) if items else 0.0


def _mentions(skill: str, text: str) -> bool:
    return re.search(rf"(?<![\w+#.]){re.escape(skill.lower())}(?![\w+#])", text.lower()) is not None


def score_resume(data: dict, today: date | None = None) -> dict:
    data = data or {}
    insights = analyze(data, today)
    s = insights["sections"]
    skills = [str(x).strip() for x in data.get("skills") or [] if str(x).strip()]
    experience = [_text(e) for e in (data.get("work_experience") or []) + (data.get("internships") or []) if _text(e)]
    projects = [_text(e) for e in data.get("projects") or [] if _text(e)]
    education = [_text(e) for e in data.get("education") or [] if _text(e)]
    certifications = [str(c).strip() for c in data.get("certifications") or [] if str(c).strip()]
    achievements = [str(a).strip() for a in data.get("achievements") or [] if str(a).strip()]
    summary = (data.get("professional_summary") or "").strip()

    # 1. Contact and profile (10)
    contact = Category("contact", "Contact and profile", 10)
    for key, pts, label in (("full_name", 3, "Full name"), ("email", 3, "Email address"), ("phone", 2, "Phone number")):
        if s[key]["found"]:
            contact.award(pts, f"{label} found")
        else:
            contact.miss(pts, f"{label} not found", f"Add your {label.lower()} at the top of the resume.")
    if s["linkedin"]["found"] or s["github"]["found"]:
        contact.award(2, "Professional profile link (LinkedIn/GitHub) found")
    else:
        contact.miss(2, "No LinkedIn or GitHub link", "Add a LinkedIn or GitHub link so recruiters can see more of your work.")

    # 2. Structure and completeness (15)
    structure = Category("structure", "Structure and completeness", 15)
    for found, label, tip in (
        (bool(summary), "Professional summary", "Add a 2-3 sentence summary of your focus and strongest skills."),
        (bool(skills), "Skills section", "Add a dedicated skills section listing your technical skills."),
        (bool(education), "Education section", "Add your education with degree, institution and year."),
        (bool(experience), "Experience or internships", "Add internships, jobs or volunteer work - even short ones count."),
        (bool(projects), "Projects section", "Add 2-3 projects with what you built and the technologies used."),
    ):
        (structure.award if found else structure.miss)(3, f"{label} {'present' if found else 'missing'}",
                                                        *(() if found else (tip,)))

    # 3. Skills and evidence (20)
    skills_cat = Category("skills", "Skills and evidence", 20)
    count_points = 8 if len(skills) >= 8 else 6 if len(skills) >= 5 else 3 if skills else 0
    skills_cat.partial(count_points, 8, f"{len(skills)} skill(s) listed",
                       "List at least 8 relevant technical skills." if len(skills) < 8 else None)
    evidence_text = " ".join(experience + projects)
    evidenced = [k for k in skills if _mentions(k, evidence_text)]
    share = len(evidenced) / len(skills) if skills else 0.0
    skills_cat.partial(12 * share, 12, f"{len(evidenced)} of {len(skills)} skills are shown in experience or projects",
                       "Show your key skills in action: mention them in your experience and project descriptions."
                       if share < 0.75 else None)

    # 4. Experience and internships (15)
    exp = Category("experience", "Experience and internships", 15)
    if experience:
        exp.award(5, f"{len(experience)} experience/internship entr{'y' if len(experience) == 1 else 'ies'}")
        dated = _share(experience, lambda t: bool(parse_dates(t, today)))
        exp.partial(4 * dated, 4, "Entries with dates", "Add start and end dates (e.g. Jun 2024 - Aug 2024) to each role." if dated < 1 else None)
        verbs = _share(experience, lambda t: bool(ACTION_VERBS.search(t)))
        exp.partial(3 * verbs, 3, "Entries describing what you did with action verbs",
                    "Start bullet points with action verbs such as built, designed or improved." if verbs < 1 else None)
        numbers = _share(experience, lambda t: bool(QUANTIFIED.search(t)))
        exp.partial(3 * numbers, 3, "Entries with measurable results",
                    "Quantify results (e.g. 'reduced load time by 30%', 'served 200 users')." if numbers < 1 else None)
    else:
        exp.miss(15, "No experience or internships found",
                 "Add internships, part-time work, freelance or volunteer roles with dates and results.")

    # 5. Projects (15)
    proj = Category("projects", "Projects", 15)
    if projects:
        proj.award(5, f"{len(projects)} project(s)")
        if len(projects) >= 2:
            proj.award(2, "Two or more projects")
        else:
            proj.miss(2, "Only one project", "Add a second project to show range.")
        described = _share(projects, lambda t: len(t) >= 40)
        proj.partial(4 * described, 4, "Projects with a real description",
                     "Describe each project: the problem, what you built and the outcome." if described < 1 else None)
        with_tech = _share(projects, lambda t: any(_mentions(k, t) for k in skills))
        proj.partial(4 * with_tech, 4, "Projects naming the technologies used",
                     "Name the technology stack in each project (e.g. 'React, FastAPI, PostgreSQL')." if with_tech < 1 else None)
    else:
        proj.miss(15, "No projects found", "Add 2-3 projects with descriptions and the technologies you used.")

    # 6. Education (10)
    edu = Category("education", "Education", 10)
    if education:
        edu.award(4, "Education entry found")
        degree = any(classify_degree(t) for t in education)
        (edu.award if degree else edu.miss)(3, "Degree recognised" if degree else "Degree not recognised",
                                            *(() if degree else ("Write the degree clearly (e.g. B.Tech Computer Science).",)))
        year = any(re.search(r"(?:19|20)\d{2}", t) for t in education)
        (edu.award if year else edu.miss)(3, "Graduation year found" if year else "No year in education",
                                          *(() if year else ("Add your graduation year or expected graduation year.",)))
    else:
        edu.miss(10, "No education found", "Add your degree, institution and graduation year.")

    # 7. Certifications and achievements (5)
    extra = Category("credentials", "Certifications and achievements", 5)
    (extra.award if certifications else extra.miss)(3, f"{len(certifications)} certification(s)" if certifications
                                                    else "No certifications",
                                                    *(() if certifications else ("Add relevant certifications or completed courses.",)))
    (extra.award if achievements else extra.miss)(2, f"{len(achievements)} achievement(s)" if achievements
                                                  else "No achievements",
                                                  *(() if achievements else ("Add achievements such as awards, hackathons or rankings.",)))

    # 8. Formatting and readability (10)
    fmt = Category("formatting", "Formatting and readability", 10)
    fmt.partial(5 * insights["overall_confidence"], 5, f"Parsing confidence {round(insights['overall_confidence'] * 100)}%",
                "Use clear section headings (Skills, Education, Experience, Projects) and a simple one- or two-column layout."
                if insights["overall_confidence"] < 0.85 else None)
    warnings = insights["warnings"]
    has_content = bool(skills or experience or projects or education)   # absence of content earns nothing
    fmt.partial(max(0.0, 2 - 0.5 * len(warnings)) if has_content else 0.0, 2, "No parsing warnings" if not warnings else f"{len(warnings)} parsing warning(s)",
                "Fix the parsing warnings listed below (dates, merged lines)." if warnings else None)
    good_summary = 40 <= len(summary) <= 600
    (fmt.award if good_summary else fmt.miss)(1, "Summary length is readable" if good_summary else "Summary missing or too long",
                                              *(() if good_summary else ("Keep the summary between 2 and 4 sentences.",)))
    focused = 0 < len(skills) <= 40
    (fmt.award if focused else fmt.miss)(1, "Skills list is focused" if focused else
                                         ("Skills list is very long" if skills else "No skills listed"),
                                         *(() if focused else (("Keep the skills list focused on your strongest 15-30 skills.",)
                                                               if skills else ())))
    clean_contact = s["phone"]["confidence"] == 1.0 and s["email"]["confidence"] == 1.0
    (fmt.award if clean_contact else fmt.miss)(1, "Contact details are cleanly formatted" if clean_contact
                                               else "Contact details look incomplete or malformed",
                                               *(() if clean_contact else ("Put email and phone on their own line in a standard format.",)))

    categories = [contact, structure, skills_cat, exp, proj, edu, extra, fmt]
    total = round(sum(c.score for c in categories))
    label = next(name for threshold, name in LABELS if total >= threshold)
    strengths = [f"{c.label}: {c.score:g}/{c.maximum}" for c in categories if c.score >= 0.8 * c.maximum]
    weaknesses = [f"{c.label}: {c.score:g}/{c.maximum}" for c in categories if c.score < 0.5 * c.maximum]
    by_gap = sorted(categories, key=lambda c: c.score - c.maximum)
    recommendations: list[str] = []
    for c in by_gap:
        for tip in c.recommendations:
            if tip not in recommendations:
                recommendations.append(tip)
    return {
        "algorithm": ALGORITHM,
        "score": total,
        "label": label,
        "categories": [c.as_dict() for c in categories],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": recommendations[:8],
        "parsing": {k: insights[k] for k in ("overall_confidence", "missing_core_fields",
                                             "missing_recommended_sections", "warnings", "total_experience_months")},
        "disclaimer": DISCLAIMER,
    }
