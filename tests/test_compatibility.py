"""Phase 3: compatibility scoring rules (pure unit tests, no database)."""

import itertools
import json
import math
from pathlib import Path

import pytest

from backend.services.compatibility import (
    ALGORITHM_VERSION,
    NO_REQUIRED_MATCH_CAP,
    NOT_STATED_SCORE,
    UNKNOWN_SCORE,
    WEIGHTS,
    Candidate,
    Posting,
    calibrate_similarity,
    classify_degree,
    classify_requirement,
    compute_compatibility,
    label_for,
    normalize_city,
    rank_results,
    score_education,
    score_location,
    score_skills,
)

DATASET = json.loads(
    (Path(__file__).resolve().parents[1] / "backend/data/internships.json").read_text(encoding="utf-8")
)


def candidate(skills=("Python", "SQL", "Git", "AWS"), degree="B.Tech Computer Science",
              location="Pune, India"):
    return Candidate(skills=tuple(skills), degree_text=degree, degree_source="profile",
                     location_text=location, location_source="profile")


def posting(required=("Python", "SQL", "Git", "Docker"), preferred=("AWS", "Linux"),
            education="Pursuing B.Tech/B.E.", mode="Onsite", location="Pune, India", iid=1):
    return Posting(iid, tuple(required), tuple(preferred), education, mode, location)


# ------------------------------------------------------------------
# Weights and worked example
# ------------------------------------------------------------------

def test_weights_sum_to_one():
    assert math.isclose(sum(WEIGHTS.values()), 1.0)


def test_worked_example_from_plan():
    # cosine 0.6025 -> semantic (0.6025-0.40)/0.35 = 0.5786
    result = compute_compatibility(candidate(), posting(), cosine=0.6025)

    assert result.component("skills").score == pytest.approx(0.8 * 0.75 + 0.2 * 0.5)
    assert result.component("semantic").score == pytest.approx(0.5786, abs=1e-4)
    assert result.component("education").score == 1.0
    assert result.component("location").score == 1.0
    expected = 100 * (0.5 * 0.70 + 0.2 * 0.5786 + 0.15 + 0.15)
    assert result.score == pytest.approx(round(expected, 1))
    assert result.label == "Strong"
    assert result.matched_required == ["Python", "SQL", "Git"]
    assert result.missing_required == ["Docker"]
    assert result.matched_preferred == ["AWS"]
    assert result.missing_preferred == ["Linux"]
    assert result.data_completeness == 1.0


# ------------------------------------------------------------------
# Skills (point 2: no automatic 100%)
# ------------------------------------------------------------------

def test_skill_coverage_cases():
    full = score_skills(candidate(["Python", "SQL", "Git", "Docker", "AWS", "Linux"]), posting())[0]
    none = score_skills(candidate(["Figma"]), posting())[0]
    assert full.score == 1.0 and none.score == 0.0


def test_required_only_uses_required_coverage():
    comp = score_skills(candidate(["Python", "SQL"]), posting(preferred=()))[0]
    assert comp.score == 0.5


def test_preferred_only_is_capped_at_80_percent():
    comp = score_skills(candidate(["AWS", "Linux"]), posting(required=()))[0]
    assert comp.score == pytest.approx(0.8)
    assert comp.status == "assessed"


def test_no_skills_listed_is_neutral_not_full():
    result = compute_compatibility(
        candidate(), posting(required=(), preferred=()), cosine=0.75
    )
    skills = result.component("skills")
    assert skills.score == NOT_STATED_SCORE and skills.status == "not_stated"
    assert result.label in {"Fair", "Weak"}
    assert any("lists no skills" in c for c in result.caps_applied + result.explanation)


def test_skill_matching_is_case_insensitive():
    comp = score_skills(candidate(["python", "sql", "git", "docker"]), posting(preferred=()))[0]
    assert comp.score == 1.0


def test_zero_required_matches_caps_score_at_50():
    result = compute_compatibility(
        candidate(["Figma"]), posting(mode="Remote"), cosine=0.75
    )
    assert result.score <= NO_REQUIRED_MATCH_CAP
    assert result.label in {"Fair", "Weak"}


# ------------------------------------------------------------------
# Semantic calibration (point 1)
# ------------------------------------------------------------------

@pytest.mark.parametrize("cosine, expected", [
    (0.10, 0.0), (0.40, 0.0), (0.428, 0.08), (0.575, 0.5), (0.62, 0.6286),
    (0.75, 1.0), (0.95, 1.0), (-0.3, 0.0),
])
def test_semantic_calibration(cosine, expected):
    assert calibrate_similarity(cosine) == pytest.approx(expected, abs=1e-3)


def test_unavailable_semantic_is_conservative():
    result = compute_compatibility(candidate(), posting(), cosine=None)
    semantic = result.component("semantic")
    assert semantic.status == "unavailable" and semantic.score == UNKNOWN_SCORE
    assert result.data_completeness == pytest.approx(0.8)
    assert any("not available" in m for m in result.missing_information)

    # Weights are NOT redistributed: the semantic slot keeps its 20% weight
    # with a conservative 0.3, so the score can never exceed what an
    # assessed similarity of 0.3 would give.
    assert semantic.weight == WEIGHTS["semantic"]
    assessed_equivalent = compute_compatibility(
        candidate(), posting(), cosine=0.40 + 0.3 * 0.35
    )
    assert result.score == pytest.approx(assessed_equivalent.score, abs=0.1)


def test_not_indexed_detail_is_specific():
    from backend.services.compatibility import SEMANTIC_NOT_INDEXED_DETAIL
    result = compute_compatibility(candidate(), posting(), None, SEMANTIC_NOT_INDEXED_DETAIL)
    assert result.component("semantic").detail == SEMANTIC_NOT_INDEXED_DETAIL


def test_nan_similarity_treated_as_unavailable():
    result = compute_compatibility(candidate(), posting(), cosine=float("nan"))
    assert result.component("semantic").status == "unavailable"


# ------------------------------------------------------------------
# Education (point 3: families matter, not just level)
# ------------------------------------------------------------------

DATASET_REQUIREMENTS = sorted({r["min_education"] for r in DATASET})


def test_all_dataset_requirements_are_recognised():
    assert len(DATASET_REQUIREMENTS) == 7
    assert all(classify_requirement(r) is not None for r in DATASET_REQUIREMENTS)


def edu(degree, requirement):
    comp, _ = score_education(candidate(degree=degree), posting(education=requirement))
    return comp.score


@pytest.mark.parametrize("degree, requirement, expected", [
    ("B.Tech Computer Science", "Pursuing B.Tech/B.E.", 1.0),
    ("B.E. Mechanical", "Pursuing B.Tech/B.E.", 1.0),
    ("B.E. Mechanical", "Pursuing B.Tech/B.E. (CS/IT preferred)", 0.85),
    ("B.Tech CSE", "Pursuing B.Tech/B.E. (CS/IT preferred)", 1.0),
    ("B.Sc Statistics", "Pursuing B.Sc (CS/IT/Stats)", 1.0),
    ("B.Sc Physics", "Pursuing B.Sc (CS/IT/Stats)", 0.5),
    ("BCA", "Pursuing BCA/MCA", 1.0),
    ("MCA", "Pursuing BCA/MCA", 1.0),
    ("M.Tech CSE", "Pursuing M.Tech/M.E.", 1.0),
    ("MBA", "Pursuing MBA", 1.0),
    ("B.Com", "Any Bachelor's degree (final year)", 1.0),
    ("MBA", "Any Bachelor's degree (final year)", 0.8),
    ("Diploma in Computer Engineering", "Any Bachelor's degree (final year)", 0.2),
    ("M.Tech CSE", "Pursuing B.Tech/B.E.", 0.7),            # higher level
    ("B.Tech Computer Science", "Pursuing M.Tech/M.E.", 0.3),  # lower level
    ("BBA", "Pursuing MBA", 0.3),
    ("BCA", "Pursuing B.Tech/B.E.", 0.6),                   # related computing
    ("B.Tech Computer Science", "Pursuing BCA/MCA", 0.6),
    ("PhD Computer Science", "Pursuing M.Tech/M.E.", 0.6),
    ("Diploma in Computer Engineering", "Pursuing B.Tech/B.E.", 0.1),
])
def test_education_rules(degree, requirement, expected):
    assert edu(degree, requirement) == pytest.approx(expected)


@pytest.mark.parametrize("degree, requirement", [
    ("MBA", "Pursuing B.Tech/B.E."),
    ("MBA", "Pursuing M.Tech/M.E."),          # same level, unrelated field
    ("M.Tech CSE", "Pursuing MBA"),            # same level, unrelated field
    ("B.Com", "Pursuing BCA/MCA"),
    ("B.A. English", "Pursuing B.Sc (CS/IT/Stats)"),
    ("B.E. Mechanical", "Pursuing BCA/MCA"),
    ("PhD History", "Pursuing M.Tech/M.E."),
])
def test_unrelated_fields_score_low_regardless_of_level(degree, requirement):
    assert edu(degree, requirement) <= 0.1


def test_bare_words_are_not_degrees():
    assert classify_degree("Let me be clear about a plan") is None
    assert classify_degree("") is None and classify_degree(None) is None


@pytest.mark.parametrize("text", [
    "I'm a final year student",            # "m a" must not become M.A.
    "I’m a quick learner",
    "Master the art of cooking",           # generic "master" needs degree context
    "Graduated in 2024 from XYZ School",
    "Class XII, CBSE board",
    "To be or not to be",
])
def test_ordinary_text_is_not_a_degree(text):
    assert classify_degree(text) is None


@pytest.mark.parametrize("text, computing", [
    ("B.Sc Physics, enjoyed it a lot", False),   # lowercase "it" is a word
    ("B.Com, completed it with distinction", False),
    ("B.Sc IT", True),                            # capital IT is the field
    ("B.Tech CSE", True),
    ("B.Tech cse", True),
    ("Bachelor of Science in Data Science", True),
    ("B.A. History", False),
])
def test_computing_field_detection(text, computing):
    assert classify_degree(text).computing_field is computing


def test_unknown_degree_is_conservative_and_reported():
    comp, hint = score_education(candidate(degree=None), posting())
    assert comp.status == "unknown" and comp.score == UNKNOWN_SCORE
    assert "degree" in hint


def test_posting_without_education_requirement_is_neutral():
    comp, hint = score_education(candidate(), posting(education=None))
    assert comp.status == "not_stated" and comp.score == NOT_STATED_SCORE and hint is None


# ------------------------------------------------------------------
# Location
# ------------------------------------------------------------------

@pytest.mark.parametrize("student, mode, where, expected", [
    ("Pune, India", "Remote", "Remote", 1.0),
    (None, "Remote", "Remote", 1.0),
    ("Pune", "Onsite", "Pune, India", 1.0),
    ("Bangalore", "Onsite", "Bengaluru, India", 1.0),
    ("Gurgaon, Haryana", "Hybrid", "Gurugram, India", 1.0),
    ("Chennai", "Hybrid", "Pune, India", 0.3),
    ("Chennai", "Onsite", "Pune, India", 0.0),
    (None, "Onsite", "Pune, India", UNKNOWN_SCORE),
    ("Pune", "Onsite", None, NOT_STATED_SCORE),
])
def test_location_rules(student, mode, where, expected):
    comp, _ = score_location(candidate(location=student), posting(mode=mode, location=where))
    assert comp.score == pytest.approx(expected)


def test_city_normalization():
    assert normalize_city("Bombay, Maharashtra") == "mumbai"
    assert normalize_city("  New Delhi ") == "delhi"
    assert normalize_city("") is None


# ------------------------------------------------------------------
# Missing information never inflates (point 4)
# ------------------------------------------------------------------

def test_missing_profile_data_never_increases_score():
    for mode, location in [("Onsite", "Pune, India"), ("Hybrid", "Delhi, India")]:
        complete = compute_compatibility(
            candidate(degree="B.Tech CSE", location="Pune"), posting(mode=mode, location=location), 0.6
        )
        missing = compute_compatibility(
            candidate(degree=None, location=None), posting(mode=mode, location=location), 0.6
        )
        good_edu = complete.component("education").score
        assert missing.component("education").score < good_edu
        assert missing.data_completeness < 1.0


def test_unknown_scores_are_below_neutral():
    assert UNKNOWN_SCORE < NOT_STATED_SCORE == 0.5


def test_excellent_requires_complete_data():
    perfect = candidate(["Python", "SQL", "Git", "Docker", "AWS", "Linux"])
    full = compute_compatibility(perfect, posting(), cosine=0.75)
    assert full.label == "Excellent"

    no_semantic = compute_compatibility(perfect, posting(), cosine=None)
    assert no_semantic.label != "Excellent"


# ------------------------------------------------------------------
# Output consistency and bounds (point 5)
# ------------------------------------------------------------------

def test_score_always_within_bounds_and_output_consistent():
    skill_sets = [(), ("Python",), ("Python", "SQL", "Git", "Docker", "AWS", "Linux")]
    postings = [
        posting(), posting(required=()), posting(required=(), preferred=()),
        posting(mode="Remote"), posting(education=None, location=None),
    ]
    cosines = [None, -1.0, 0.0, 0.5, 1.0, 5.0]
    for skills, post, cos in itertools.product(skill_sets, postings, cosines):
        result = compute_compatibility(
            Candidate(skills=skills, degree_text=None, location_text=None), post, cos
        )
        assert 0.0 <= result.score <= 100.0
        assert [c.name for c in result.components] == ["skills", "semantic", "education", "location"]
        for comp in result.components:
            assert 0.0 <= comp.score <= 1.0
            assert comp.status in {"assessed", "unknown", "not_stated", "unavailable"}
        breakdown = result.breakdown()
        assert breakdown["algorithm_version"] == ALGORITHM_VERSION
        assert set(breakdown) >= {
            "components", "matched_required_skills", "missing_required_skills",
            "matched_preferred_skills", "missing_preferred_skills",
            "data_completeness", "missing_information", "caps_applied", "explanation",
        }
        assert len(result.explanation) >= 4

        # Mathematical consistency: components add up to the pre-cap
        # score; the final score only differs by caps and rounding.
        weighted_sum = sum(c["weighted"] for c in breakdown["components"])
        assert weighted_sum == pytest.approx(result.score_before_caps, abs=0.05)
        expected = result.score_before_caps
        if post.required_skills and not result.matched_required:
            expected = min(expected, NO_REQUIRED_MATCH_CAP)
        assert result.score == pytest.approx(round(expected, 1), abs=0.051)
        assert result.score <= result.score_before_caps + 0.05

        # Completeness is exactly the share of weight with real data.
        assessed = sum(c.weight for c in result.components if c.status == "assessed")
        assert result.data_completeness == pytest.approx(assessed)
        if result.data_completeness < 1.0:
            assert result.label != "Excellent"


@pytest.mark.parametrize("score, label", [
    (0.0, "Weak"), (44.9, "Weak"), (45.0, "Fair"), (64.9, "Fair"),
    (65.0, "Strong"), (79.9, "Strong"), (80.0, "Excellent"), (100.0, "Excellent"),
])
def test_label_boundaries(score, label):
    assert label_for(score) == label


def test_ranking_is_deterministic():
    results = [
        compute_compatibility(candidate(), posting(iid=i), 0.6) for i in (3, 1, 2)
    ]
    ordered = rank_results(results)
    assert [r.internship_id for r in ordered] == [1, 2, 3]


def test_explanation_contains_no_personal_data():
    result = compute_compatibility(
        Candidate(skills=("Python",), degree_text="B.Tech CSE", location_text="Pune"),
        posting(), 0.6,
    )
    text = " ".join(result.explanation)
    assert "@" not in text
    assert "Python" in text
