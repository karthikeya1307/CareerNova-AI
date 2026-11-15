"""Resume-internship compatibility scoring (algorithm v1).

Pure functions: no database or model access, fully deterministic.

Final score = 100 x sum(weight x component score), clamped to [0, 100].

Components (weights): skills 0.50, semantic 0.20, education 0.15,
location 0.15. Every component reports a status:

    assessed     both sides known, score computed
    unknown      the student's information is missing      -> 0.3
    not_stated   the posting does not specify it           -> 0.5
    unavailable  semantic index/model not available        -> 0.3

Missing student information scores BELOW neutral, so it can never
inflate a score. Label caps:
    * no required skill matched (posting lists some) -> score <= 50
    * posting lists no skills                         -> label <= Fair
    * any component not assessed                      -> label <= Strong

Semantic calibration (validated on the 180-posting dataset with the
pinned all-MiniLM-L6-v2 model): cosine 0.40 -> 0.0, 0.75 -> 1.0.
Median unrelated pair 0.43 -> 0.08; median related pair 0.62 -> 0.63.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "v1"

WEIGHTS = {"skills": 0.50, "semantic": 0.20, "education": 0.15, "location": 0.15}

UNKNOWN_SCORE = 0.3
NOT_STATED_SCORE = 0.5
UNAVAILABLE_SCORE = 0.3

REQUIRED_SHARE = 0.8
PREFERRED_SHARE = 0.2
PREFERRED_ONLY_MAX = 0.8

SEMANTIC_FLOOR = 0.40
SEMANTIC_CEILING = 0.75

NO_REQUIRED_MATCH_CAP = 50.0

LABELS = [(80.0, "Excellent"), (65.0, "Strong"), (45.0, "Fair"), (0.0, "Weak")]
LABEL_ORDER = ["Weak", "Fair", "Strong", "Excellent"]

ASSESSED = "assessed"
UNKNOWN = "unknown"
NOT_STATED = "not_stated"
UNAVAILABLE = "unavailable"


# ============================================================
# INPUT TYPES
# ============================================================

@dataclass(frozen=True)
class Candidate:
    """What we know about the student (no personal identifiers)."""

    skills: tuple[str, ...]                 # canonical skill names
    degree_text: str | None = None
    degree_source: str | None = None        # "profile" | "resume"
    location_text: str | None = None
    location_source: str | None = None      # "request" | "profile" | "resume"


@dataclass(frozen=True)
class Posting:
    internship_id: int
    required_skills: tuple[str, ...]
    preferred_skills: tuple[str, ...]
    min_education: str | None = None
    work_mode: str | None = None
    location: str | None = None


@dataclass
class Component:
    name: str
    score: float
    weight: float
    status: str
    detail: str

    @property
    def weighted(self) -> float:
        return self.score * self.weight

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "weight": self.weight,
            "weighted": round(self.weighted * 100, 2),
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class CompatibilityResult:
    internship_id: int
    score: float
    label: str
    components: list[Component]
    matched_required: list[str]
    missing_required: list[str]
    matched_preferred: list[str]
    missing_preferred: list[str]
    required_coverage: float | None
    data_completeness: float
    # Sum of the weighted components (0-100) before caps; equals
    # sum(component.weighted) and score == min(score_before_caps, caps).
    score_before_caps: float = 0.0
    missing_information: list[str] = field(default_factory=list)
    caps_applied: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)

    def component(self, name: str) -> Component:
        return next(c for c in self.components if c.name == name)

    def breakdown(self) -> dict[str, Any]:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "components": [c.as_dict() for c in self.components],
            "matched_required_skills": self.matched_required,
            "missing_required_skills": self.missing_required,
            "matched_preferred_skills": self.matched_preferred,
            "missing_preferred_skills": self.missing_preferred,
            "required_skill_coverage": self.required_coverage,
            "data_completeness": self.data_completeness,
            "score_before_caps": self.score_before_caps,
            "missing_information": self.missing_information,
            "caps_applied": self.caps_applied,
            "explanation": self.explanation,
        }


# ============================================================
# SKILLS
# ============================================================

def _split(posting_skills, candidate_keys):
    matched = [s for s in posting_skills if s.casefold() in candidate_keys]
    missing = [s for s in posting_skills if s.casefold() not in candidate_keys]
    return matched, missing


def score_skills(candidate: Candidate, posting: Posting):
    keys = {s.casefold() for s in candidate.skills}
    matched_req, missing_req = _split(posting.required_skills, keys)
    matched_pref, missing_pref = _split(posting.preferred_skills, keys)

    n_req, n_pref = len(posting.required_skills), len(posting.preferred_skills)
    req_cov = len(matched_req) / n_req if n_req else None
    pref_cov = len(matched_pref) / n_pref if n_pref else None

    if n_req and n_pref:
        score = REQUIRED_SHARE * req_cov + PREFERRED_SHARE * pref_cov
        status = ASSESSED
    elif n_req:
        score, status = req_cov, ASSESSED
    elif n_pref:
        # No required skills: preferred skills are weaker evidence.
        score, status = PREFERRED_ONLY_MAX * pref_cov, ASSESSED
    else:
        score, status = NOT_STATED_SCORE, NOT_STATED

    parts = []
    if n_req:
        text = f"You have {len(matched_req)} of {n_req} required skills"
        text += f" ({', '.join(matched_req)})." if matched_req else "."
        if missing_req:
            text += f" Missing: {', '.join(missing_req)}."
        parts.append(text)
    if n_pref:
        text = f"You have {len(matched_pref)} of {n_pref} preferred skills"
        text += f" ({', '.join(matched_pref)})." if matched_pref else "."
        parts.append(text)
    if not n_req and n_pref:
        parts.append("The posting lists no required skills, so the skill score is limited to 80%.")
    if not n_req and not n_pref:
        parts.append("The posting lists no skills, so skill fit could not be assessed.")

    component = Component("skills", score, WEIGHTS["skills"], status, " ".join(parts))
    return component, matched_req, missing_req, matched_pref, missing_pref, req_cov


# ============================================================
# SEMANTIC
# ============================================================

def calibrate_similarity(cosine: float) -> float:
    value = (cosine - SEMANTIC_FLOOR) / (SEMANTIC_CEILING - SEMANTIC_FLOOR)
    return min(1.0, max(0.0, value))


SEMANTIC_UNAVAILABLE_DETAIL = (
    "Semantic similarity is unavailable (search index or model not ready)."
)
SEMANTIC_NOT_INDEXED_DETAIL = (
    "Semantic similarity is unavailable because this internship has not "
    "been indexed yet."
)


def score_semantic(cosine: float | None, unavailable_detail: str | None = None) -> Component:
    if cosine is None or not math.isfinite(cosine):
        return Component(
            "semantic", UNAVAILABLE_SCORE, WEIGHTS["semantic"], UNAVAILABLE,
            unavailable_detail or SEMANTIC_UNAVAILABLE_DETAIL,
        )

    score = calibrate_similarity(cosine)
    strength = "closely" if score >= 0.6 else "moderately" if score >= 0.3 else "weakly"
    return Component(
        "semantic", score, WEIGHTS["semantic"], ASSESSED,
        f"Your resume is {strength} related to this role (similarity {cosine:.2f}).",
    )


# ============================================================
# EDUCATION
# ============================================================

LEVEL_RANK = {"diploma": 0, "bachelor": 1, "master": 2, "phd": 3}

FAMILY_LABELS = {
    "engineering": "engineering",
    "science": "science",
    "computer_applications": "computer applications",
    "business": "business administration",
    "commerce": "commerce",
    "arts": "arts",
    "design": "design",
    "other": "unspecified field",
}

# (pattern on normalized text, level, family) - first match wins.
# Two-letter degrees (B.E., M.E., B.A., M.A.) are recognised only in their
# dotted form ("b e" after normalisation), so words like "be"/"me"/"ba" in
# free text are never mistaken for a degree.
_DEGREE_PATTERNS = [
    (r"\bph ?d\b|\bdoctor(ate| of philosophy)\b", "phd", "other"),
    (r"\bm ?tech\b|\bm e\b|\bmaster of (technology|engineering)\b", "master", "engineering"),
    (r"\bmca\b|\bmaster of computer applications?\b", "master", "computer_applications"),
    (r"\bmba\b|\bmaster of business administration\b", "master", "business"),
    (r"\bm ?sc\b|\bmaster of science\b", "master", "science"),
    (r"\bm ?com\b|\bmaster of commerce\b", "master", "commerce"),
    (r"\bm ?des\b|\bmaster of design\b", "master", "design"),
    (r"\bm a\b|\bmaster of arts\b", "master", "arts"),
    (r"\bb ?tech\b|\bb e\b|\bbachelor of (technology|engineering)\b", "bachelor", "engineering"),
    (r"\bbca\b|\bbachelor of computer applications?\b", "bachelor", "computer_applications"),
    (r"\bbba\b|\bbachelor of business administration\b", "bachelor", "business"),
    (r"\bb ?sc\b|\bbachelor of science\b", "bachelor", "science"),
    (r"\bb ?com\b|\bbachelor of commerce\b", "bachelor", "commerce"),
    (r"\bb ?des\b|\bbachelor of design\b", "bachelor", "design"),
    (r"\bb a\b|\bbachelor of arts\b", "bachelor", "arts"),
    # Generic forms need degree context ("master's degree", "masters in"),
    # so phrases like "master the art of cooking" are not degrees.
    (r"\bmasters? (degree|in|of)\b|\bpost ?graduate\b", "master", "other"),
    (r"\bbachelors? (degree|in|of)\b|\bundergraduate\b", "bachelor", "other"),
    (r"\bdiploma\b|\bpolytechnic\b", "diploma", "other"),
]

# Computing field: full words (case-insensitive) ...
_CS_WORDS = re.compile(
    r"\b(cse|computer|computing|software|information technology|data|"
    r"statistics|stats|mathematics|maths|artificial intelligence)\b"
)
# ... and acronyms only in capitals, so ordinary "it"/"ai" are ignored.
_CS_ACRONYMS = re.compile(r"\b(CS|CSE|IT|AI)\b")

COMPUTING_FAMILIES = {"engineering", "computer_applications", "science"}


def _normalize(text: str) -> str:
    # Apostrophes are removed first so "I'm a" cannot look like "M.A.".
    text = text.casefold().replace("'", "").replace("’", "")
    text = text.replace(".", " ").replace("/", " / ")
    text = re.sub(r"[^a-z0-9/()& ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _has_computing_field(original: str) -> bool:
    return bool(_CS_ACRONYMS.search(original) or _CS_WORDS.search(_normalize(original)))


@dataclass(frozen=True)
class Degree:
    level: str
    family: str
    computing_field: bool

    @property
    def is_computing(self) -> bool:
        # "other" covers PhDs and generic "Bachelor's in Computer Science".
        return self.family == "computer_applications" or (
            self.family in {"engineering", "science", "other"} and self.computing_field
        )

    def describe(self) -> str:
        level = {"phd": "doctorate", "master": "master's", "bachelor": "bachelor's",
                 "diploma": "diploma"}[self.level]
        return f"{level} in {FAMILY_LABELS[self.family]}"


def classify_degree(text: str | None) -> Degree | None:
    if not text or not text.strip():
        return None
    normalized = _normalize(text)
    for pattern, level, family in _DEGREE_PATTERNS:
        if re.search(pattern, normalized):
            return Degree(level, family, _has_computing_field(text))
    return None


@dataclass(frozen=True)
class Requirement:
    any_bachelor: bool
    family: str | None
    levels: frozenset[str]
    prefer_computing: bool = False
    require_computing: bool = False


def classify_requirement(text: str | None) -> Requirement | None:
    if not text or not text.strip():
        return None
    normalized = _normalize(text)

    if re.search(r"\bany bachelor", normalized):
        return Requirement(True, None, frozenset({"bachelor"}))
    if re.search(r"\bbca\b|\bmca\b", normalized):
        return Requirement(False, "computer_applications", frozenset({"bachelor", "master"}))
    if re.search(r"\bm ?tech\b|\bm e\b", normalized):
        return Requirement(False, "engineering", frozenset({"master"}))
    if re.search(r"\bmba\b", normalized):
        return Requirement(False, "business", frozenset({"master"}))
    if re.search(r"\bb ?tech\b|\bb e\b", normalized):
        return Requirement(
            False, "engineering", frozenset({"bachelor"}),
            prefer_computing="preferred" in normalized and _has_computing_field(text),
        )
    if re.search(r"\bb ?sc\b", normalized):
        return Requirement(
            False, "science", frozenset({"bachelor"}),
            require_computing=_has_computing_field(text),
        )
    return None


def _education_value(degree: Degree, req: Requirement) -> tuple[float, str]:
    rank = LEVEL_RANK[degree.level]

    if req.any_bachelor:
        if degree.level == "bachelor":
            return 1.0, "meets the requirement"
        if rank > LEVEL_RANK["bachelor"]:
            return 0.8, "exceeds the bachelor's-level requirement"
        return 0.2, "is below the bachelor's-level requirement"

    if degree.level == "diploma":
        return 0.1, "is below the degree requirement"

    min_rank = min(LEVEL_RANK[l] for l in req.levels)
    max_rank = max(LEVEL_RANK[l] for l in req.levels)

    if degree.family == req.family:
        if degree.level in req.levels:
            if req.require_computing and not degree.computing_field:
                return 0.5, "is in the right degree but a different subject"
            if req.prefer_computing and not degree.computing_field:
                return 0.85, "matches; a CS/IT branch is preferred"
            return 1.0, "matches the requirement"
        if rank > max_rank:
            return 0.7, "is a higher level than this internship targets"
        return 0.3, "is a lower level than required"

    # Related computing degrees: CS/IT engineering <-> BCA/MCA <-> B.Sc CS.
    if degree.is_computing and req.family in COMPUTING_FAMILIES:
        if rank >= min_rank:
            return 0.6, "is a closely related computing degree"
        return 0.3, "is a related degree but below the required level"

    return 0.1, "is in an unrelated field"


def score_education(candidate: Candidate, posting: Posting) -> tuple[Component, str | None]:
    requirement = classify_requirement(posting.min_education)
    degree = classify_degree(candidate.degree_text)

    if requirement is None:
        detail = "The posting does not state a recognisable education requirement."
        return Component("education", NOT_STATED_SCORE, WEIGHTS["education"], NOT_STATED, detail), None

    if degree is None:
        detail = (
            f"Requirement: {posting.min_education}. Your degree is unknown"
            + (" or could not be recognised." if candidate.degree_text else ".")
        )
        return (
            Component("education", UNKNOWN_SCORE, WEIGHTS["education"], UNKNOWN, detail),
            "Add your degree (for example 'B.Tech Computer Science') to your profile.",
        )

    value, reason = _education_value(degree, requirement)
    source = f" (from your {candidate.degree_source})" if candidate.degree_source else ""
    detail = f"Requirement: {posting.min_education}. Your {degree.describe()}{source} {reason}."
    return Component("education", value, WEIGHTS["education"], ASSESSED, detail), None


# ============================================================
# LOCATION
# ============================================================

CITY_ALIASES = {
    "bangalore": "bengaluru", "gurgaon": "gurugram", "bombay": "mumbai",
    "madras": "chennai", "calcutta": "kolkata", "new delhi": "delhi",
    "trivandrum": "thiruvananthapuram", "cochin": "kochi", "poona": "pune",
    "mysore": "mysuru", "vizag": "visakhapatnam", "baroda": "vadodara",
}


def normalize_city(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    city = re.sub(r"\s+", " ", text.split(",")[0].strip().casefold())
    city = re.sub(r"[^a-z ]", "", city).strip()
    return CITY_ALIASES.get(city, city) or None


def score_location(candidate: Candidate, posting: Posting) -> tuple[Component, str | None]:
    weight = WEIGHTS["location"]
    mode = (posting.work_mode or "").casefold()
    posting_city = normalize_city(posting.location)

    if mode == "remote" or posting_city == "remote":
        return Component("location", 1.0, weight, ASSESSED,
                         "Remote internship, so your location is not a constraint."), None

    if posting_city is None:
        return Component("location", NOT_STATED_SCORE, weight, NOT_STATED,
                         "The posting does not state a location."), None

    candidate_city = normalize_city(candidate.location_text)
    where = f"{posting.work_mode or 'On-site'} in {posting.location}"

    if candidate_city is None:
        return (
            Component("location", UNKNOWN_SCORE, weight, UNKNOWN,
                      f"{where}. Your location is unknown."),
            "Add your city to your profile to assess location fit.",
        )

    if candidate_city == posting_city:
        return Component("location", 1.0, weight, ASSESSED,
                         f"{where}, which matches your location."), None
    if mode == "hybrid":
        return Component("location", 0.3, weight, ASSESSED,
                         f"{where}; you are in a different city (hybrid needs some office days)."), None
    return Component("location", 0.0, weight, ASSESSED,
                     f"{where}; you are in a different city."), None


# ============================================================
# COMBINE
# ============================================================

def label_for(score: float) -> str:
    return next(name for threshold, name in LABELS if score >= threshold)


def _cap_label(label: str, maximum: str) -> str:
    return LABEL_ORDER[min(LABEL_ORDER.index(label), LABEL_ORDER.index(maximum))]


def compute_compatibility(
    candidate: Candidate,
    posting: Posting,
    cosine: float | None,
    semantic_unavailable_detail: str | None = None,
) -> CompatibilityResult:
    skills, matched_req, missing_req, matched_pref, missing_pref, req_cov = score_skills(
        candidate, posting
    )
    semantic = score_semantic(cosine, semantic_unavailable_detail)
    education, education_hint = score_education(candidate, posting)
    location, location_hint = score_location(candidate, posting)
    components = [skills, semantic, education, location]

    assert abs(sum(c.weight for c in components) - 1.0) < 1e-9

    raw = sum(c.weighted for c in components)
    score = 100.0 * raw
    if not math.isfinite(score):
        raise ValueError("Compatibility score is not a finite number")
    score_before_caps = round(min(100.0, max(0.0, score)), 2)
    caps: list[str] = []

    if posting.required_skills and not matched_req and score > NO_REQUIRED_MATCH_CAP:
        score = NO_REQUIRED_MATCH_CAP
        caps.append("Score limited to 50 because none of the required skills matched.")

    if not math.isfinite(score):
        raise ValueError("Compatibility score is not a finite number")
    score = round(min(100.0, max(0.0, score)), 1)

    label = label_for(score)
    if skills.status == NOT_STATED and LABEL_ORDER.index(label) > LABEL_ORDER.index("Fair"):
        label = "Fair"
        caps.append("Label limited to Fair because the posting lists no skills.")

    completeness = round(sum(c.weight for c in components if c.status == ASSESSED), 4)
    if completeness < 1.0 and label == "Excellent":
        label = _cap_label(label, "Strong")
        caps.append("Label limited to Strong because some information is missing.")

    missing_info = [hint for hint in (education_hint, location_hint) if hint]
    if semantic.status == UNAVAILABLE:
        missing_info.append("Semantic similarity was not available for this result.")

    explanation = [c.detail for c in components] + caps

    return CompatibilityResult(
        internship_id=posting.internship_id,
        score=score,
        label=label,
        components=components,
        matched_required=matched_req,
        missing_required=missing_req,
        matched_preferred=matched_pref,
        missing_preferred=missing_pref,
        required_coverage=None if req_cov is None else round(req_cov, 4),
        data_completeness=completeness,
        score_before_caps=score_before_caps,
        missing_information=missing_info,
        caps_applied=caps,
        explanation=explanation,
    )


def rank_results(results: list[CompatibilityResult]) -> list[CompatibilityResult]:
    """Deterministic order: score, then required coverage, then id."""
    return sorted(
        results,
        key=lambda r: (-r.score, -(r.required_coverage or 0.0), r.internship_id),
    )
