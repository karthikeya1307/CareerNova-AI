"""Hybrid resume parser: deterministic rules + LLM, reconciled against the document text.

Rules (recorded per field in ``metadata.sources``):
* Name, email, phone: regex only (reliable, and never sent to the AI provider).
* Technical skills and certifications: union of both, keeping only values that appear in the resume text,
  de-duplicated case-insensitively.
* Education, work experience, projects: the LLM's entries when they are supported by the resume text and at least as
  complete as the regex entries; otherwise the regex entries. Missing details on a chosen entry are filled from the
  matching regex entry. Disagreements are listed in ``metadata.warnings``.
* If the AI provider is unavailable or answers badly, the result is the regex extraction with ``sources`` = "regex"
  and a clear warning - it is never presented as LLM output.

Usage:  python -m backend.manage parse-resume <file> --parser hybrid
"""

from __future__ import annotations

from backend.services.resume_parsers import llm_parser, regex_parser
from backend.services.resume_parsers.common import (Metadata, ParsedResume, extract_text, normalise_space,
                                                    supported_by)


def _key(value: str | None) -> str:
    return normalise_space(value).casefold()


def _union(document: str, a: list[str], b: list[str]) -> tuple[list[str], str]:
    seen, out = {}, []
    for value in a + b:
        k = _key(value)
        if k and k not in seen and supported_by(document, value):
            seen[k] = value
            out.append(value)
    in_a = {_key(x) for x in a}
    in_b = {_key(x) for x in b if supported_by(document, x)}
    source = "both" if in_a and in_b else "regex" if in_a else "llm" if in_b else "none"
    return out, source


def _filled(entry, fields) -> int:
    return sum(1 for f in fields if getattr(entry, f))


def _merge_entries(regex_entries, llm_entries, match_field, fields):
    """Pair entries by the match field; prefer the more complete one and fill gaps from the other."""
    chosen, conflicts = [], []
    remaining = list(regex_entries)
    for llm_entry in llm_entries:
        key = _key(getattr(llm_entry, match_field))
        partner = next((r for r in remaining if key and (_key(getattr(r, match_field)) == key
                                                         or key in _key(r.text))), None)
        if partner is None:
            chosen.append(llm_entry)
            continue
        remaining.remove(partner)
        better, other = (llm_entry, partner) if _filled(llm_entry, fields) >= _filled(partner, fields) else (partner, llm_entry)
        for f in fields:
            if not getattr(better, f) and getattr(other, f):
                setattr(better, f, getattr(other, f))
            elif getattr(better, f) and getattr(other, f) and isinstance(getattr(better, f), str) \
                    and _key(getattr(better, f)) != _key(getattr(other, f)):
                conflicts.append(f"{match_field} '{getattr(better, match_field)}': {f} differs "
                                 f"('{getattr(better, f)}' kept, '{getattr(other, f)}' ignored)")
        better.text = better.text or other.text
        chosen.append(better)
    chosen.extend(remaining)                                  # regex-only entries are kept (nothing dropped)
    return chosen, conflicts


def parse_text(text: str, file_type: str | None = None, provider=None, regex_data: dict | None = None) -> ParsedResume:
    deterministic = regex_parser.parse_text(text, file_type, regex_data)
    sources = {"full_name": "regex" if deterministic.full_name else "none",
               "email": "regex" if deterministic.email else "none",
               "phone": "regex" if deterministic.phone else "none"}
    warnings = list(deterministic.metadata.warnings)
    try:
        ai = llm_parser.parse_text(text, file_type, provider, name_hint=deterministic.full_name)
    except (llm_parser.LLMParserUnavailable, llm_parser.LLMParserError) as exc:
        for f in ("technical_skills", "education", "work_experience", "projects", "certifications"):
            sources[f] = "regex" if getattr(deterministic, f) else "none"
        deterministic.metadata = Metadata(parser="hybrid", file_type=file_type, sources=sources,
                                          warnings=warnings + [f"AI extraction not used: {exc} Only rule-based results "
                                                               "are shown."])
        return deterministic

    skills, sources["technical_skills"] = _union(text, deterministic.technical_skills, ai.technical_skills)
    certs, sources["certifications"] = _union(text, deterministic.certifications, ai.certifications)
    education, c1 = _merge_entries(deterministic.education, ai.education, "institution",
                                   ["institution", "qualification", "field_of_study", "start", "end", "grade"])
    experience, c2 = _merge_entries(deterministic.work_experience, ai.work_experience, "company",
                                    ["title", "company", "start", "end", "description"])
    projects, c3 = _merge_entries(deterministic.projects, ai.projects, "title", ["title", "technologies", "description"])
    for field, regex_list, ai_list in (("education", deterministic.education, ai.education),
                                       ("work_experience", deterministic.work_experience, ai.work_experience),
                                       ("projects", deterministic.projects, ai.projects)):
        sources[field] = "both" if regex_list and ai_list else "regex" if regex_list else "llm" if ai_list else "none"
    warnings += [w for w in ai.metadata.warnings if w not in warnings] + c1 + c2 + c3
    return ParsedResume(
        full_name=deterministic.full_name, email=deterministic.email, phone=deterministic.phone,
        technical_skills=sorted(skills, key=str.casefold), education=education, work_experience=experience,
        projects=projects, certifications=certs,
        metadata=Metadata(parser="hybrid", file_type=file_type, warnings=warnings, sources=sources,
                          llm_provider=ai.metadata.llm_provider, llm_model=ai.metadata.llm_model),
    )


def parse(file_bytes: bytes, filename: str, provider=None) -> ParsedResume:
    from backend.services import resume_parser

    text, file_type = extract_text(file_bytes, filename)
    data = resume_parser.parse_resume_file(file_bytes, filename)["extracted_data"] if file_type in ("pdf", "docx") else None
    return parse_text(text, file_type, provider, data)
