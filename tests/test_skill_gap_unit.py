"""Phase 4: skill relations, learning plans and gap logic (no database)."""

import copy
import json
from pathlib import Path

import pytest

from backend.models import Internship, InternshipSkill, Skill, SkillGapRecommendation
from backend.services import learning_plans
from backend.services.learning_plans import (
    learning_order,
    load_plans,
    missing_prerequisites,
    plan_for,
    validate_plans,
)
from backend.services.skill_gap import (
    aggregate_gaps,
    analyse_internship,
    assess_internship,
    recommended_action,
    update_status,
)
from backend.services.skill_normalizer import SKILL_CATALOG
from backend.services.skill_relations import (
    RELATED_SKILL_PAIRS,
    find_related_in,
    related_skills,
)

DATASET = json.loads(
    (Path(__file__).resolve().parents[1] / "backend/data/internships.json").read_text(encoding="utf-8")
)
DATASET_SKILLS = {s for r in DATASET for s in r["required_skills"] + r["preferred_skills"]}


_next_id = iter(range(1, 10_000))


def internship(iid, required, preferred=(), title="Intern", company="Example Co"):
    item = Internship(internship_id=iid, title=title, company=company, is_active=True)
    item.skill_links = [
        InternshipSkill(skill=Skill(skill_id=_skill_id(s), name=s, category=SKILL_CATALOG.get(s)),
                        importance=imp)
        for imp, names in (("required", required), ("preferred", preferred)) for s in names
    ]
    return item


_ids: dict[str, int] = {}


def _skill_id(name):
    if name not in _ids:
        _ids[name] = next(_next_id)
    return _ids[name]


# ------------------------------------------------------------------
# Related skills
# ------------------------------------------------------------------

def test_all_related_skills_are_canonical():
    for a, b, why in RELATED_SKILL_PAIRS:
        assert a in SKILL_CATALOG and b in SKILL_CATALOG and why


def test_relations_are_symmetric():
    for a, b, _ in RELATED_SKILL_PAIRS:
        assert b in related_skills(a) and a in related_skills(b)


def test_find_related_in_candidate_skills():
    assert [s for s, _ in find_related_in("PostgreSQL", ["MySQL", "Python"])] == ["MySQL"]
    assert find_related_in("Kubernetes", ["Figma"]) == []
    assert [s for s, _ in find_related_in("TensorFlow", ["pytorch"])] == ["pytorch"]


# ------------------------------------------------------------------
# Learning plans
# ------------------------------------------------------------------

def test_every_dataset_skill_has_a_curated_plan():
    plans = load_plans()["plans"]
    assert DATASET_SKILLS <= set(plans)
    assert all(plan_for(s)["curated"] for s in DATASET_SKILLS)


def test_plans_contain_no_links_or_unknown_skills():
    text = json.dumps(load_plans()).lower()
    # The protocol name "HTTP" is a legitimate topic; URLs are not.
    assert "http://" not in text and "https://" not in text and "www." not in text
    for skill, plan in load_plans()["plans"].items():
        assert skill in SKILL_CATALOG
        assert set(plan["prerequisites"]) <= set(SKILL_CATALOG)


def test_uncurated_skill_gets_labelled_generic_plan():
    plan = plan_for("LangChain")
    assert plan["curated"] is False and plan["estimated_hours"] is None
    assert "generic" in plan["note"]


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["plans"].__setitem__("Quantum Basket Weaving", d["plans"]["Git"]), "unknown skill"),
    (lambda d: d["plans"]["Git"].__setitem__("topics", ["see https://example.com"]), "links"),
    (lambda d: d["plans"]["Git"].__setitem__("estimated_hours", 0), "estimated_hours"),
    (lambda d: d["plans"]["Git"].__setitem__("prerequisites", ["Kubernetes"]) or
               d["plans"]["Kubernetes"].__setitem__("prerequisites", ["Git"]), "cycle"),
    (lambda d: d["plans"]["Git"].__setitem__("level", "expert"), "level"),
])
def test_invalid_plan_files_are_rejected(mutate, message):
    data = copy.deepcopy(load_plans())
    mutate(data)
    with pytest.raises(ValueError, match=message):
        validate_plans(data)


def test_learning_order_puts_prerequisites_first():
    order = learning_order(["Kubernetes", "Deep Learning", "Docker", "Machine Learning", "Linux"])
    assert order.index("Linux") < order.index("Docker") < order.index("Kubernetes")
    assert order.index("Machine Learning") < order.index("Deep Learning")
    assert sorted(order) == sorted(["Kubernetes", "Deep Learning", "Docker", "Machine Learning", "Linux"])


def test_missing_prerequisites_respects_known_skills():
    assert missing_prerequisites("Kubernetes", {"Docker"}) == []
    assert missing_prerequisites("Kubernetes", set()) == ["Docker"]


# ------------------------------------------------------------------
# Single internship classification
# ------------------------------------------------------------------

def test_matched_partial_and_missing():
    posting = internship(1, ["Python", "PostgreSQL", "Kubernetes"], ["TensorFlow", "Figma"])
    result = {a.skill: a for a in assess_internship(["python", "MySQL", "PyTorch"], posting)}

    assert result["Python"].status == "matched"
    assert result["PostgreSQL"].status == "partial"
    assert result["PostgreSQL"].related[0]["skill"] == "MySQL"
    assert result["Kubernetes"].status == "missing"
    assert result["TensorFlow"].status == "partial" and result["TensorFlow"].importance == "preferred"
    assert result["Figma"].status == "missing"


def test_analysis_report_structure():
    posting = internship(1, ["Python", "Kubernetes", "Docker"], ["AWS"])
    report = analyse_internship(["Python"], posting)

    assert report["summary"] == {
        "required_total": 3, "required_matched": 1, "required_partial": 0, "required_missing": 2,
        "preferred_total": 1, "preferred_matched": 0, "preferred_partial": 0, "preferred_missing": 1,
    }
    assert report["learning_order"].index("Docker") < report["learning_order"].index("Kubernetes")
    plans = {p["skill"]: p["plan"] for p in report["learning_plans"]}
    assert plans["Kubernetes"]["missing_prerequisites"] == ["Docker"]
    assert plans["AWS"]["curated"] is True


# ------------------------------------------------------------------
# Aggregation and priority formula
# ------------------------------------------------------------------

def test_priority_formula_exact_values():
    a = internship(1, ["Docker", "SQL"], ["AWS"])
    b = internship(2, ["Docker"], ["SQL"])
    gaps, total = aggregate_gaps(["Python"], [(a, 0.8), (b, 0.4)])
    by = {g.skill: g for g in gaps}

    assert total == pytest.approx(1.2)
    # Docker required in both: (1.0*0.8 + 1.0*0.4) / 1.2 = 100
    assert by["Docker"].priority == 100.0
    # SQL required in a, preferred in b: (0.8 + 0.5*0.4) / 1.2 = 83.3
    assert by["SQL"].priority == 83.3
    assert by["SQL"].importance == "required" and by["SQL"].demand == 2
    # AWS preferred in a only: 0.5*0.8 / 1.2 = 33.3
    assert by["AWS"].priority == 33.3
    assert [g.skill for g in gaps] == ["Docker", "SQL", "AWS"]


def test_partial_skills_get_half_weight():
    a = internship(1, ["PostgreSQL", "Kubernetes"])
    gaps, _ = aggregate_gaps(["MySQL"], [(a, 1.0)])
    by = {g.skill: g for g in gaps}
    assert by["PostgreSQL"].gap_level == "partial" and by["PostgreSQL"].priority == 50.0
    assert by["Kubernetes"].gap_level == "missing" and by["Kubernetes"].priority == 100.0


def test_priorities_bounded_and_matched_skills_excluded():
    a = internship(1, ["Python", "Docker"], ["AWS"])
    gaps, _ = aggregate_gaps(["Python", "Docker", "AWS"], [(a, 0.9)])
    assert gaps == []

    gaps, _ = aggregate_gaps([], [(a, 0.0), (internship(2, ["Docker"]), 1.5)])
    assert all(0 <= g.priority <= 100 for g in gaps)


def test_ties_break_by_required_count_then_demand_then_name():
    a = internship(1, ["Git"], ["Bash"])
    b = internship(2, [], ["Linux"])
    gaps, _ = aggregate_gaps([], [(a, 0.5), (b, 0.5)])
    # Bash and Linux tie on priority (25.0); alphabetical.
    assert [g.skill for g in gaps] == ["Git", "Bash", "Linux"]


def test_recommended_action_uses_only_source_facts():
    a = internship(1, ["PostgreSQL", "Kubernetes"], title="DevOps Intern", company="Nimbus Labs")
    gaps, _ = aggregate_gaps(["MySQL"], [(a, 1.0)])
    by = {g.skill: g for g in gaps}

    text = recommended_action(by["PostgreSQL"], 1, [])
    assert text.startswith("Strengthen PostgreSQL: required by 1 of the 1 internship analysed")
    assert "DevOps Intern at Nimbus Labs" in text and "MySQL" in text
    assert "http" not in text

    text = recommended_action(by["Kubernetes"], 1, ["Docker"])
    assert text.startswith("Learn Kubernetes") and text.endswith("Start with: Docker.")


# ------------------------------------------------------------------
# Status transitions
# ------------------------------------------------------------------

def test_status_transitions_set_timestamps():
    rec = SkillGapRecommendation(status="pending")
    update_status(rec, "in_progress")
    assert rec.status == "in_progress" and rec.started_at and rec.completed_at is None

    started = rec.started_at
    update_status(rec, "completed")
    assert rec.completed_via == "user" and rec.completed_at and rec.started_at == started

    update_status(rec, "dismissed")
    assert rec.completed_at is None and rec.completed_via is None

    update_status(rec, "pending")
    assert rec.started_at is None

    with pytest.raises(ValueError):
        update_status(rec, "finished")
