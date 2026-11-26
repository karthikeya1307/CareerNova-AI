"""Parsing quality for an extracted resume: section confidence, missing fields and dates.

Everything here is computed from the stored extraction (``ResumeParsedData``); nothing is
inferred beyond what the resume says. The result is recalculated on every read, so a re-parse or a
user correction is reflected immediately.

Confidence (0..1) per section is a transparent heuristic:
* contact fields: 1.0 when the value has the expected shape (valid email, 10-15 digit phone,
  2-4 word name, linkedin.com / github.com URL), 0.5 when present but unusual;
* list sections: 0.9 when every entry has meaningful text (>= 15 characters), 0.6 when some
  entries are very short (possible mis-split), 0.4 for a single very short entry;
* skills: 0.9 with 5 or more skills, 0.6 with 1-4.
Overall confidence = mean confidence of the sections that were found x share of the core fields
present (name, email, phone, skills, education).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_POINT = rf"(?:{_MONTH}\s*,?\s*(?:19|20)\d{{2}}|\d{{1,2}}\s*/\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
_OPEN = r"(?:present|current|now|ongoing|till date|to date)"
RANGE_RE = re.compile(rf"({_POINT})\s*(?:-|–|—|to|until)\s*({_POINT}|{_OPEN})", re.IGNORECASE)
SINGLE_RE = re.compile(rf"(?<![\d/])({_POINT})(?![\d/])", re.IGNORECASE)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
CORE_FIELDS = ("full_name", "email", "phone", "skills", "education")
RECOMMENDED = {
    "professional_summary": "Professional summary",
    "experience": "Work experience or internships",
    "projects": "Projects",
    "profile_link": "LinkedIn or GitHub profile",
    "certifications": "Certifications",
    "achievements": "Achievements",
}
CORE_LABELS = {"full_name": "Full name", "email": "Email address", "phone": "Phone number",
               "skills": "Skills", "education": "Education"}
ENTRY_SECTIONS = ("education", "work_experience", "internships", "projects")


def _text(entry: Any) -> str:
    if isinstance(entry, dict):
        return " ".join(str(v) for v in entry.values() if isinstance(v, str)).strip()
    return str(entry or "").strip()


def parse_point(text: str, today: date | None = None) -> tuple[int, int] | None:
    """(year, month) for '06/2024', 'Jun 2024', '2024' (month 1 when only the year is given)."""
    text = text.strip().lower().replace(",", " ")
    m = re.match(r"(\d{1,2})\s*/\s*(\d{4})$", text)
    if m:
        month = int(m.group(1))
        return (int(m.group(2)), month) if 1 <= month <= 12 else None
    m = re.match(r"([a-z]+)\.?\s+(\d{4})$", text)
    if m and m.group(1)[:3] in MONTHS:
        return int(m.group(2)), MONTHS[m.group(1)[:3]]
    m = re.match(r"(\d{4})$", text)
    return (int(m.group(1)), 1) if m else None


def parse_dates(text: str, today: date | None = None) -> list[dict]:
    """Date ranges (with duration in months) and single years found in an entry."""
    today = today or date.today()
    found, used = [], []
    for m in RANGE_RE.finditer(text):
        start = parse_point(m.group(1))
        open_end = re.fullmatch(_OPEN, m.group(2).strip(), re.IGNORECASE) is not None
        end = (today.year, today.month) if open_end else parse_point(m.group(2))
        if not start or not end:
            continue
        months = (end[0] - start[0]) * 12 + (end[1] - start[1]) + 1     # inclusive; the current month counts
        found.append({"text": m.group(0), "start": f"{start[0]:04d}-{start[1]:02d}",
                      "end": None if open_end else f"{end[0]:04d}-{end[1]:02d}", "ongoing": open_end,
                      "months": months if months > 0 else None, "valid": months > 0})
        used.append(m.span())
    for m in SINGLE_RE.finditer(text):
        if any(a <= m.start() < b for a, b in used):
            continue
        point = parse_point(m.group(1))
        if point:
            year_only = re.fullmatch(r"(?:19|20)\d{2}", m.group(1).strip()) is not None
            # A bare year stays a year: no month is invented.
            end = f"{point[0]:04d}" if year_only else f"{point[0]:04d}-{point[1]:02d}"
            found.append({"text": m.group(0), "start": None, "end": end,
                          "ongoing": False, "months": None, "valid": True})
    return found


def _entry_confidence(entries: list) -> float:
    texts = [_text(e) for e in entries]
    texts = [t for t in texts if t]
    if not texts:
        return 0.0
    if len(texts) == 1 and len(texts[0]) < 15:
        return 0.4
    return 0.9 if all(len(t) >= 15 for t in texts) else 0.6


def analyze(data: dict, today: date | None = None) -> dict:
    data = data or {}
    sections: dict[str, dict] = {}

    def add(name: str, found: bool, confidence: float, count: int | None = None, note: str | None = None):
        sections[name] = {"found": found, "confidence": round(confidence, 2) if found else 0.0,
                          **({"entries": count} if count is not None else {}), **({"note": note} if note else {})}

    name = (data.get("full_name") or "").strip()
    add("full_name", bool(name), 1.0 if 2 <= len(name.split()) <= 4 and re.fullmatch(r"[A-Za-z .'-]+", name) else 0.5)
    email = (data.get("email") or "").strip()
    add("email", bool(email), 1.0 if EMAIL_RE.match(email) else 0.5)
    phone = (data.get("phone") or "").strip()
    digits = len(re.sub(r"\D", "", phone))
    add("phone", bool(phone), 1.0 if 10 <= digits <= 15 and "\n" not in phone else 0.5)
    for link, domain in (("linkedin", "linkedin.com"), ("github", "github.com")):
        value = (data.get(link) or "").strip()
        add(link, bool(value), 1.0 if domain in value.lower() else 0.5)
    summary = (data.get("professional_summary") or "").strip()
    add("professional_summary", bool(summary), 0.9 if len(summary) >= 40 else 0.6)

    skills = [s for s in (data.get("skills") or []) if str(s).strip()]
    add("skills", bool(skills), 0.9 if len(skills) >= 5 else 0.6, len(skills))
    for key in ENTRY_SECTIONS:
        entries = [e for e in (data.get(key) or []) if _text(e)]
        add(key, bool(entries), _entry_confidence(entries), len(entries))
    for key in ("certifications", "achievements"):
        items = [i for i in (data.get(key) or []) if str(i).strip()]
        add(key, bool(items), 0.9 if all(len(str(i).strip()) >= 4 for i in items) else 0.6, len(items))

    present = {
        "full_name": sections["full_name"]["found"], "email": sections["email"]["found"],
        "phone": sections["phone"]["found"], "skills": sections["skills"]["found"],
        "education": sections["education"]["found"],
    }
    missing_core = [CORE_LABELS[k] for k, ok in present.items() if not ok]
    recommended = {
        "professional_summary": sections["professional_summary"]["found"],
        "experience": sections["work_experience"]["found"] or sections["internships"]["found"],
        "projects": sections["projects"]["found"],
        "profile_link": sections["linkedin"]["found"] or sections["github"]["found"],
        "certifications": sections["certifications"]["found"],
        "achievements": sections["achievements"]["found"],
    }
    missing_recommended = [RECOMMENDED[k] for k, ok in recommended.items() if not ok]

    dates, warnings = [], []
    for key in ENTRY_SECTIONS:
        for index, entry in enumerate(data.get(key) or []):
            for item in parse_dates(_text(entry), today):
                dates.append({"section": key, "entry": index, **item})
                if not item["valid"]:
                    warnings.append(f"A date range in {key.replace('_', ' ')} ends before it starts: {item['text']}")
    for key in ("work_experience", "internships"):          # projects are often undated
        for index, entry in enumerate(data.get(key) or []):
            if _text(entry) and not parse_dates(_text(entry), today):
                warnings.append(f"{key.replace('_', ' ').capitalize()} entry {index + 1} has no dates.")
    if phone and "\n" in phone:
        warnings.append("The phone number looks merged with another line; check it.")

    found = [s["confidence"] for s in sections.values() if s["found"]]
    core_share = sum(present.values()) / len(present)
    overall = round((sum(found) / len(found) if found else 0.0) * core_share, 2)
    return {
        "overall_confidence": overall,
        "sections": sections,
        "missing_core_fields": missing_core,
        "missing_recommended_sections": missing_recommended,
        "dates": dates,
        "total_experience_months": sum(d["months"] or 0 for d in dates
                                       if d["section"] in ("work_experience", "internships") and d["valid"]),
        "warnings": warnings,
    }
