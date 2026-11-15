"""Phase 6: deterministic question generation and grounding (no database)."""

import pytest

from backend.models import Internship, InternshipSkill, Skill
from backend.services.fact_base import CandidateFacts, Fact
from backend.services.fact_check import skill_mentions
from backend.services.interview_generator import (
    DEFAULT_MIX,
    GenerationRequest,
    generate_questions,
)
from backend.services.question_bank import behavioral_bank


def make_internship(required=("Python", "SQL", "Docker"), preferred=("Django",)):
    internship = Internship(internship_id=1, title="Backend Developer Intern", company="Nimbus Analytics",
                            domain="Software Development", description="Build REST APIs.", is_active=True)
    internship.skill_links = [
        InternshipSkill(skill=Skill(skill_id=n, name=s), importance=imp)
        for n, (s, imp) in enumerate([*[(s, "required") for s in required], *[(s, "preferred") for s in preferred]])
    ]
    return internship


def make_candidate(skills=("Python", "FastAPI", "PostgreSQL", "Docker", "Git"), facts=None):
    facts = facts if facts is not None else [
        Fact("sum-1", "summary", "Backend developer."),
        Fact("exp-1", "experience", "Software Intern, Example Systems, 2025\nBuilt 12 REST endpoints with FastAPI and PostgreSQL."),
        Fact("proj-1", "project", "Inventory API\nDeployed a Docker service used by 20 users."),
        Fact("proj-2", "project", "Portfolio Site\nBuilt with HTML and CSS."),
    ]
    return CandidateFacts(5, {"name": "Asha Rao"}, facts, list(skills), "B.Tech IT")


def generate(candidate=None, internship="default", mix=None, seed=1, difficulty="mixed", exclude=frozenset()):
    return generate_questions(
        candidate or make_candidate(),
        make_internship() if internship == "default" else internship,
        GenerationRequest(mix or DEFAULT_MIX, difficulty, seed, exclude),
    )


def test_mix_is_respected():
    questions = generate()
    counts = {c: sum(q["category"] == c for q in questions) for c in DEFAULT_MIX}
    assert counts == DEFAULT_MIX


def test_technical_order_and_labels():
    technical = [q for q in generate(mix={"technical": 4}) if q["category"] == "technical"]
    skills = [(q["skill"], q["context"]["skill_status"]) for q in technical]
    # Required skills the candidate has first, then missing required ones.
    assert skills[:3] == [("Docker", "have"), ("Python", "have"), ("SQL", "required_missing")]
    assert technical[2]["suggested_answer"]["note"]


def test_technical_skills_only_from_internship_or_resume():
    allowed = {"Python", "SQL", "Docker", "Django", "FastAPI", "PostgreSQL", "Git"}
    technical = [q for q in generate(mix={"technical": 10}) if q["category"] == "technical"]
    assert {q["skill"] for q in technical} <= allowed
    assert len({q["bank_question_id"] for q in technical}) == len(technical)


def test_project_questions_are_grounded_in_cited_facts():
    candidate = make_candidate()
    projects = [q for q in generate(candidate, mix={"project": 3}) if q["category"] == "project"]
    assert len(projects) == 3
    for q in projects:
        fact = candidate.by_id[q["source_fact_ids"][0]]
        assert fact.title in q["text"]
        assert skill_mentions(q["text"]) <= skill_mentions(fact.text)       # no invented technologies
        assert q["suggested_answer"]["from_your_resume"] == fact.lines[:4]
    # Docker internship: the Docker project ranks before the HTML portfolio.
    assert projects[0]["source_fact_ids"] in (["proj-1"], ["exp-1"])
    assert "proj-2" == projects[-1]["source_fact_ids"][0]


def test_internship_questions_use_only_the_internship_record():
    questions = [q for q in generate(mix={"internship": 4}) if q["category"] == "internship"]
    kinds = [q["context"]["kind"] for q in questions]
    assert kinds == ["motivation", "missing_skill", "fit", "domain"]
    assert "Nimbus Analytics" in questions[0]["text"] and "Backend Developer Intern" in questions[0]["text"]
    assert questions[1]["skill"] == "SQL" and "not on your resume" in questions[1]["text"]
    assert "Software Development" in questions[3]["text"]


def test_without_internship_internship_quota_moves_to_behavioral():
    questions = generate(internship=None)
    assert not [q for q in questions if q["category"] == "internship"]
    assert sum(q["category"] == "behavioral" for q in questions) == DEFAULT_MIX["behavioral"] + DEFAULT_MIX["internship"]


def test_same_seed_same_questions_different_seed_may_differ():
    a = [q["text"] for q in generate(seed=7)]
    b = [q["text"] for q in generate(seed=7)]
    assert a == b
    variants = {tuple(q["text"] for q in generate(seed=s, mix={"behavioral": 3})) for s in range(1, 8)}
    assert len(variants) > 1


def test_no_duplicates_and_max_15():
    questions = generate(mix={"technical": 10, "project": 5, "behavioral": 5, "internship": 5})
    texts = [q["text"] for q in questions]
    assert len(texts) == len(set(texts)) and len(texts) <= 15


def test_recent_behavioral_questions_are_avoided():
    recent = frozenset(q["id"] for q in behavioral_bank()["questions"][:10])
    chosen = [q["bank_question_id"] for q in generate(mix={"behavioral": 2}, exclude=recent)
              if q["category"] == "behavioral"]
    assert not set(chosen) & recent


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_difficulty_filter(difficulty):
    technical = [q for q in generate(mix={"technical": 3}, difficulty=difficulty) if q["category"] == "technical"]
    assert {q["difficulty"] for q in technical} == {difficulty}


def test_candidate_without_projects_gets_no_project_questions():
    candidate = make_candidate(facts=[Fact("sum-1", "summary", "Student.")])
    questions = generate(candidate, mix={"project": 2, "behavioral": 1})
    assert [q["category"] for q in questions] == ["behavioral"]


def test_behavioral_stories_cite_real_facts():
    candidate = make_candidate()
    behavioral = [q for q in generate(candidate, mix={"behavioral": 1}) if q["category"] == "behavioral"][0]
    assert all(f in candidate.by_id for f in behavioral["source_fact_ids"])
    assert behavioral["suggested_answer"]["type"] == "star"
