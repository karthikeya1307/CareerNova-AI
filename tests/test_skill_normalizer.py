"""Unit tests for the skill normalizer (no database)."""

import pytest

from backend.services.skill_normalizer import (
    CATEGORY_OTHER,
    SKILL_ALIASES,
    SKILL_CATALOG,
    normalize_extracted_skills,
    normalize_skill,
    normalize_skills,
)

# Every skill used by the Milestone 2 internship dataset.
DATASET_SKILLS = [
    "AWS", "Adobe XD", "Agile", "Algorithms", "Angular", "Azure",
    "Bootstrap", "C++", "CI/CD", "CSS", "Communication", "Computer Vision",
    "Content Writing", "Data Analysis", "Data Structures", "Deep Learning",
    "Design Systems", "Django", "Docker", "Excel", "FastAPI", "Figma",
    "Financial Modeling", "Firebase", "GCP", "Git", "Google Analytics",
    "GraphQL", "HTML", "JIRA", "Java", "JavaScript", "Jenkins", "Kotlin",
    "Kubernetes", "Linux", "Machine Learning", "Market Research",
    "Monitoring", "NLP", "Networking", "Node.js", "NumPy", "Pandas",
    "Power BI", "Problem Solving", "Prototyping", "PyTorch", "Python",
    "REST API", "React", "React Native", "SEO", "SQL", "SQLite",
    "Scikit-learn", "Selenium", "Social Media Marketing", "Spring Boot",
    "Statistics", "Swift", "Tableau", "Tailwind CSS", "TensorFlow",
    "Terraform", "TypeScript", "User Research", "Vue", "Wireframing",
]


def test_dataset_has_69_skills():
    assert len(set(DATASET_SKILLS)) == 69


@pytest.mark.parametrize("name", DATASET_SKILLS)
def test_every_dataset_skill_maps_to_itself(name):
    skill = normalize_skill(name)
    assert skill is not None
    assert skill.name == name
    assert skill.category != CATEGORY_OTHER


@pytest.mark.parametrize("raw, expected", [
    ("React.js", "React"),
    ("reactjs", "React"),
    ("A WS", "AWS"),
    ("aws", "AWS"),
    ("Node", "Node.js"),
    ("NodeJS", "Node.js"),
    ("sklearn", "Scikit-learn"),
    ("scikit learn", "Scikit-learn"),
    ("k8s", "Kubernetes"),
    ("RESTful APIs", "REST API"),
    ("ci/cd", "CI/CD"),
    ("Postgres", "PostgreSQL"),
    ("problem-solving", "Problem Solving"),
    ("Java Script", "JavaScript"),
    ("  • Python ,", "Python"),
])
def test_aliases_and_spacing(raw, expected):
    assert normalize_skill(raw).name == expected


def test_c_family_stays_distinct():
    assert normalize_skill("C").name == "C"
    assert normalize_skill("c++").name == "C++"
    assert normalize_skill("C#").name == "C#"


@pytest.mark.parametrize("raw", [
    "Basic", "Intermediate", "Skills", "", "   ", "-", "2024",
    "x" * 61, None, 42,
])
def test_noise_is_dropped(raw):
    assert normalize_skill(raw) is None


def test_unknown_skill_is_kept_as_other():
    skill = normalize_skill("  Antigravity  ")
    assert skill.name == "Antigravity"
    assert skill.category == CATEGORY_OTHER
    assert skill.is_known is False


def test_soft_skill_category():
    assert normalize_skill("Communication").category == "soft_skill"
    assert normalize_skill("teamwork").category == "soft_skill"


def test_deduplication_is_case_insensitive_and_ordered():
    result = normalize_skills(
        ["React.js", "Python", "react", "PYTHON", "Antigravity", "antigravity"]
    )
    assert [s.name for s in result] == ["React", "Python", "Antigravity"]


def test_normalize_extracted_skills_records_source():
    extracted = {
        "skills": ["Java", "Communication", "Basic"],
        "technical_skills": ["Java", "React.js", "A WS"],
        "soft_skills": ["Communication"],
    }
    result = normalize_extracted_skills(extracted)

    assert [s.name for s in result] == ["Java", "React", "AWS", "Communication"]
    assert result[0].source == "technical_skills"
    assert result[3].source == "soft_skills"


def test_normalize_extracted_skills_handles_missing_fields():
    assert normalize_extracted_skills({}) == []
    assert normalize_extracted_skills({"skills": None}) == []
    assert normalize_extracted_skills({"skills": "not a list"}) == []


def test_all_aliases_point_to_catalog():
    assert set(SKILL_ALIASES.values()) <= set(SKILL_CATALOG)
