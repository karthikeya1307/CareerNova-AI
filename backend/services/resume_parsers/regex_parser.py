"""Rule-based resume parser: regular expressions and deterministic rules only (no LLM).

It reuses CareerNova's existing extraction (``backend.services.resume_parser``: column-aware PDF reading, DOCX
tables, section detection, contact details, the skill dictionary and the project grouping) and adds deterministic
structuring on top: education (institution, qualification, field, dates, grade), work experience (title, company,
dates, description), projects (title, technologies, description), certifications, and phone numbers with country
codes.

Usage:  python -m backend.manage parse-resume <file> --parser regex
"""

from __future__ import annotations

import re
from typing import Any

from backend.services.resume_parsers.common import (Education, Experience, Metadata, ParsedResume, Project,
                                                    ResumeFileError, dates_in, extract_text, normalise_space)

QUALIFICATION = re.compile(
    r"\b(B\.?\s?Tech|B\.?\s?E\.?|B\.?\s?Sc|B\.?\s?Com|B\.?\s?C\.?A|B\.?\s?A\.?|Bachelor(?:'s)?(?: of [A-Z][a-z]+)?|"
    r"M\.?\s?Tech|M\.?\s?E\.?|M\.?\s?Sc|M\.?\s?C\.?A|M\.?\s?B\.?A|Master(?:'s)?(?: of [A-Z][a-z]+)?|Ph\.?\s?D|"
    r"Diploma|Intermediate|Senior Secondary|Higher Secondary|HSC|SSC|12th|10th|Class (?:X|XII))\b", re.IGNORECASE)
INSTITUTION = re.compile(r"\b(university|college|institute|school|academy|polytechnic|iit|nit|iiit)\b", re.IGNORECASE)
FIELD = re.compile(r"\b(?:in|of)\s+([A-Z][A-Za-z&/ ]{2,60}?)(?=\s*(?:[,(–—|-]|\d|$|\bat\b|\bfrom\b))")
GRADE = re.compile(r"\b(?:CGPA|GPA|CPI|SGPA)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)(?:\s*/\s*\d{1,2})?|\b(\d{2}(?:\.\d{1,2})?)\s*%",
                   re.IGNORECASE)
TITLE_WORDS = re.compile(r"\b(intern|engineer|developer|analyst|associate|assistant|manager|consultant|designer|"
                         r"scientist|trainee|lead|executive|specialist|administrator|tester|architect)\b", re.IGNORECASE)
PHONE = re.compile(r"(?<![\w+])(\+\d{1,3})?[\s.-]?\(?\d{2,5}\)?[\s.-]?\d{3,5}[\s.-]?\d{3,5}(?!\w)")


def normalise_phone(raw: str | None, text: str = "") -> str | None:
    """Keep the country code when present (+91 98765 43210); never invent one."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not 10 <= len(digits) <= 15:
        return None
    if raw.strip().startswith("+"):
        national = digits[-10:]
        code = digits[:-10]
        return f"+{code} {national[:5]} {national[5:]}" if code else f"+{digits}"
    if len(digits) == 12 and digits.startswith("91"):           # 91XXXXXXXXXX written without '+'
        return f"+91 {digits[2:7]} {digits[7:]}"
    return f"{digits[:5]} {digits[5:]}" if len(digits) == 10 else digits


def _lines(entry: Any) -> list[str]:
    text = entry.get("details") if isinstance(entry, dict) else entry
    return [normalise_space(line) for line in str(text or "").splitlines() if normalise_space(line)]


def structure_education(entry: Any) -> Education:
    lines = _lines(entry)
    text = " ".join(lines)
    qualification = QUALIFICATION.search(text)
    line = next((line for line in lines if INSTITUTION.search(line)), None)
    institution = None
    if line:                       # "B.Tech in CS, Example Institute of Technology, 2022 - 2026" -> the institution part
        parts = [p.strip(" -–—|") for p in re.split(r"\s*[,|]\s*|\s+[–—]\s+", line) if p.strip(" -–—|")]
        institution = next((p for p in parts if INSTITUTION.search(p)), line)
        institution = DATE_TAIL.sub("", institution).strip(" ,-–—|") or None
    field = FIELD.search(text[qualification.end():] if qualification else text)
    start, end = dates_in(text)
    grade = GRADE.search(text)
    return Education(institution=institution or None, qualification=qualification.group(0) if qualification else None,
                     field_of_study=normalise_space(field.group(1)) if field else None, start=start, end=end,
                     grade=(grade.group(1) or f"{grade.group(2)}%") if grade else None, text="\n".join(lines))


DATE_TAIL = re.compile(r"[\s,|–—-]*(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?"
                       r"(?:19|20)\d{2}.*$", re.IGNORECASE)


def structure_experience(entry: Any) -> Experience:
    lines = _lines(entry)
    if not lines:
        return Experience()
    head = lines[0]
    start, end = dates_in(" ".join(lines[:2]))
    head_clean = DATE_TAIL.sub("", head).strip(" ,-–—|")
    title = company = None
    at = re.match(r"(.+?)\s+(?:at|@)\s+(.+)", head_clean, re.IGNORECASE)
    parts = [p.strip() for p in re.split(r"\s*[,|–—]\s*|\s+-\s+", head_clean) if p.strip()]
    if at:
        title, company = at.group(1), at.group(2)
    elif len(parts) >= 2:
        first_is_title = bool(TITLE_WORDS.search(parts[0]))
        title, company = (parts[0], parts[1]) if first_is_title else (parts[1], parts[0])
    elif TITLE_WORDS.search(head_clean):
        title = head_clean
    else:
        company = head_clean
    description = [re.sub(r"^[•▪●◦·\-–—*]\s*", "", line) for line in lines[1:]]
    description = [d for d in description if d and DATE_TAIL.sub("", d).strip(" ,-–—|()")]   # drop date-only lines
    return Experience(title=title, company=company, start=start, end=end, description=description, text="\n".join(lines))


def structure_project(entry: Any) -> Project:
    lines = _lines(entry)
    if not lines:
        return Project()
    technologies: list[str] = []
    description: list[str] = []
    for line in lines[1:]:
        tech = re.match(r"(?:technologies|tech stack|tools|stack)\s*:\s*(.+)", line, re.IGNORECASE)
        if tech:
            technologies.extend(t.strip() for t in re.split(r",|\||·", tech.group(1)) if t.strip())
        else:
            description.append(line)
    return Project(title=lines[0], technologies=technologies, description=description, text="\n".join(lines))


def _skills(data: dict) -> list[str]:
    from backend.services.skill_normalizer import normalize_skill

    found: dict[str, str] = {}
    for raw in (data.get("technical_skills") or []) + (data.get("skills") or []):
        skill = normalize_skill(str(raw))
        if skill is not None and skill.category != "soft_skill":
            found.setdefault(skill.name.casefold(), skill.name)
    return sorted(found.values(), key=str.casefold)


def parse_text(text: str, file_type: str | None = None, data: dict | None = None) -> ParsedResume:
    """Structure already-extracted resume text (``data`` = the existing parser's output, if available)."""
    from backend.services import resume_parser

    data = data or resume_parser.parse_resume_text(text)
    warnings: list[str] = []
    phone = normalise_phone(data.get("phone"), text)
    if data.get("phone") and not phone:
        warnings.append("A phone-like number was found but it does not have 10-15 digits; it was not used.")
    result = ParsedResume(
        full_name=data.get("full_name") or None,
        email=data.get("email") or None,
        phone=phone,
        technical_skills=_skills(data),
        education=[structure_education(e) for e in data.get("education") or []],
        work_experience=[structure_experience(e) for e in (data.get("work_experience") or []) + (data.get("internships") or [])],
        projects=[structure_project(p) for p in data.get("projects") or []],
        certifications=[normalise_space(c if isinstance(c, str) else (c or {}).get("details"))
                        for c in data.get("certifications") or [] if normalise_space(c if isinstance(c, str) else (c or {}).get("details"))],
        metadata=Metadata(parser="regex", file_type=file_type, warnings=warnings),
    )
    for field in ("full_name", "email", "phone"):
        if getattr(result, field) is None:
            result.metadata.warnings.append(f"{field.replace('_', ' ')} not found in the resume.")
    return result


def parse(file_bytes: bytes, filename: str) -> ParsedResume:
    """PDF / DOCX / ODT file -> ParsedResume (raises ``ResumeFileError`` for unusable files)."""
    from backend.services import resume_parser

    text, file_type = extract_text(file_bytes, filename)
    data = None
    if file_type in ("pdf", "docx"):
        try:                                 # the existing parser also reads DOCX tables and repairs layouts
            data = resume_parser.parse_resume_file(file_bytes, filename)["extracted_data"]
        except ValueError as exc:
            raise ResumeFileError(str(exc)) from None
    return parse_text(text, file_type, data)
