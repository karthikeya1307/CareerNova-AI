"""Assignment evaluation package: profile integrity and safety guard."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.services.resume_parser import parse_resume_file
from backend.services.skill_normalizer import normalize_extracted_skills, normalize_skill
from evaluation.profiles import PROFILES

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ASSIGNMENT_SCENARIOS = [
    "AI/ML candidate",
    "Backend developer",
    "Data Science candidate",
    "Generative AI candidate",
    "Candidate with multiple programming skills",
    "Candidate with strong educational qualifications",
    "Candidate with relevant experience",
    "Candidate with relevant academic projects",
    "Candidate with partial skill overlap",
    "Candidate with limited or missing information",
]


def test_ten_profiles_cover_every_assignment_scenario():
    assert [p.scenario for p in PROFILES] == ASSIGNMENT_SCENARIOS
    assert len({p.key for p in PROFILES}) == 10


@pytest.mark.parametrize("profile", PROFILES, ids=[p.key for p in PROFILES])
def test_profile_resume_is_parsed_by_the_real_parser(profile):
    parsed = parse_resume_file(profile.to_docx(), f"{profile.key}.docx")
    data = parsed["extracted_data"]

    expected = {normalize_skill(s).name for s in profile.skills}
    assert {s.name for s in normalize_extracted_skills(data)} == expected

    if profile.education:
        assert data["education"], "education section not extracted"
    if profile.experience:
        assert data["work_experience"], "experience section not extracted"
    if profile.projects:
        assert data["projects"], "projects section not extracted"

    # Contact details are fictional placeholders only.
    assert data["email"].endswith("@example.com")


def test_runner_refuses_non_test_database():
    env = {**os.environ, "DB_NAME": "career_companion"}
    result = subprocess.run(
        [sys.executable, "-m", "evaluation.rag_evaluation"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "Refusing to run" in (result.stdout + result.stderr)
