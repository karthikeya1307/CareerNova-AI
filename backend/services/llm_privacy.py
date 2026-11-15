"""Personal-data protection for every request sent to the optional AI provider.

All language-model requests go through ``document_common.call_llm`` (Phase 5
resume and cover-letter rewriting, Phase 6 AI-tailored interview questions
and Phase 6 answer feedback). Before sending, ``scrub_llm_payload`` cleans a
copy of every candidate string in the request:

* e-mail addresses, phone numbers and links (shared Phase 5 ``scrub``);
* the full name and every part of it (3+ letters) as whole words, so a
  first name or surname on its own is also removed;
* the stored resume address and profile location, plus each part of the
  address;
* street-number patterns ("12 MG Road", "Flat No. 4B") and six-digit
  Indian PIN codes.

``find_llm_payload_personal_data`` is the last check before sending: if
anything is still detected, nothing is sent and deterministic or rubric
content is used instead. Internship records (public data) and canonical
skill lists are neither scrubbed nor checked. Stored resumes, facts,
answers and scores are never changed; only the outgoing copy is cleaned.
Warnings name the kind of data found, never the value.
"""

from __future__ import annotations

import re
from typing import Any

from backend.services.fact_base import EMAIL_RE, PHONE_RE, URL_RE, CandidateFacts, scrub

REMOVED = "[removed]"
MIN_NAME_PART = 3
MIN_ADDRESS_PART = 4

PIN_RE = re.compile(r"(?<![\d.,])[1-9]\d{2}\s?\d{3}(?![\d.,]*\d)")
STREET_WORDS = (
    r"road|rd|street|st|lane|ln|nagar|cross|main road|avenue|ave|marg|colony|sector|apartments?|apts?|"
    r"residency|enclave|society|chowk|gali|layout|block"
)
STREET_RE = re.compile(
    r"\b\d{1,5}[a-z]?(?:[/-]\d{1,5}[a-z]?)?,?\s+(?:[a-z0-9.'-]+\s+){0,3}?(?:" + STREET_WORDS + r")\b",
    re.IGNORECASE,
)
HOUSE_RE = re.compile(
    r"\b(?:flat|house|plot|door|apt|apartment|h)\.?\s*(?:no\.?|number|#)\s*[\w/-]*\d[\w/-]*",
    re.IGNORECASE,
)


# Request keys holding public or catalogue data, never personal data.
PUBLIC_KEYS = frozenset({"internship", "skills", "matched_skills"})


def personal_details(candidate: CandidateFacts | None) -> dict[str, Any]:
    """Contact details (including the parsed resume address) to keep away from the AI provider."""
    details: dict[str, Any] = dict(candidate.contact) if candidate else {}
    address = getattr(candidate, "address", None)
    details["address"] = address if isinstance(address, str) else None
    return details


def _name_parts(details: dict[str, Any]) -> list[str]:
    name = details.get("name") or ""
    parts = {p for p in re.findall(r"[^\W\d_]+(?:['-][^\W\d_]+)*", name) if len(p) >= MIN_NAME_PART}
    return sorted(parts, key=len, reverse=True)


def _address_strings(details: dict[str, Any]) -> list[str]:
    values = []
    for key in ("address", "location"):
        value = details.get(key)
        if isinstance(value, str) and len(value.strip()) >= MIN_ADDRESS_PART:
            values.append(value.strip())
            values += [p.strip() for p in re.split(r"[,;\n]", value) if len(p.strip()) >= MIN_ADDRESS_PART]
    return sorted(set(values), key=len, reverse=True)


def _whole_word(value: str) -> re.Pattern:
    escaped = r"\s+".join(re.escape(part) for part in value.split())
    return re.compile(r"(?<![\w])" + escaped + r"(?![\w])", re.IGNORECASE)


def scrub_personal(text: str, details: dict[str, Any]) -> str:
    text = scrub(text or "", details)
    for value in _address_strings(details):
        text = _whole_word(value).sub(REMOVED, text)
    text = HOUSE_RE.sub(REMOVED, text)
    text = STREET_RE.sub(REMOVED, text)
    text = PIN_RE.sub(REMOVED, text)
    for part in _name_parts(details):
        text = _whole_word(part).sub("the candidate", text)
    return text


def find_personal_data(text: str, details: dict[str, Any]) -> list[str]:
    """Kinds of personal data still present in text (empty list means safe to send)."""
    found = []
    if EMAIL_RE.search(text):
        found.append("email")
    if PHONE_RE.search(text):
        found.append("phone")
    if URL_RE.search(text):
        found.append("link")
    for key in ("email", "phone", "linkedin", "github"):
        value = details.get(key)
        if isinstance(value, str) and len(value.strip()) >= MIN_NAME_PART and value.strip().casefold() in text.casefold():
            found.append(key)
    if any(_whole_word(part).search(text) for part in _name_parts(details)):
        found.append("name")
    if any(_whole_word(value).search(text) for value in _address_strings(details)):
        found.append("address")
    if STREET_RE.search(text) or HOUSE_RE.search(text):
        found.append("street_address")
    if PIN_RE.search(text):
        found.append("pin_code")
    return sorted(set(found))


def scrub_llm_payload(payload: Any, details: dict[str, Any]) -> Any:
    """A copy of the request with every candidate string scrubbed (public keys left as they are)."""
    if isinstance(payload, dict):
        return {k: (v if k in PUBLIC_KEYS else scrub_llm_payload(v, details)) for k, v in payload.items()}
    if isinstance(payload, list):
        return [scrub_llm_payload(v, details) for v in payload]
    if isinstance(payload, str):
        return scrub_personal(payload, details)
    return payload


def _candidate_strings(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [s for k, v in payload.items() if k not in PUBLIC_KEYS for s in _candidate_strings(v)]
    if isinstance(payload, list):
        return [s for v in payload for s in _candidate_strings(v)]
    return [payload] if isinstance(payload, str) else []


def find_llm_payload_personal_data(payload: Any, details: dict[str, Any]) -> list[str]:
    """Kinds of personal data left anywhere in the candidate part of a request."""
    return sorted({kind for text in _candidate_strings(payload) for kind in find_personal_data(text, details)})


__all__ = ["REMOVED", "personal_details", "scrub_personal", "find_personal_data", "scrub_llm_payload",
           "find_llm_payload_personal_data"]
