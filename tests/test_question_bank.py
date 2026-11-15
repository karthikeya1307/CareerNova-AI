"""Phase 6: curated question banks - coverage, quality and validation."""

import copy
import json
from pathlib import Path

import pytest

from backend.services.question_bank import (
    bank_info,
    behavioral_bank,
    technical_bank,
    validate_behavioral_bank,
    validate_technical_bank,
)
from backend.services.skill_normalizer import SKILL_CATALOG

DATASET = json.loads((Path(__file__).resolve().parents[1] / "backend/data/internships.json").read_text(encoding="utf-8"))
DATASET_SKILLS = {s for r in DATASET for s in r["required_skills"] + r["preferred_skills"]}


def test_covers_all_69_dataset_skills_with_three_difficulties():
    bank = technical_bank()["technical"]
    assert set(bank) == DATASET_SKILLS and len(bank) == 69
    for skill, questions in bank.items():
        assert sorted(q["difficulty"] for q in questions) == ["easy", "hard", "medium"], skill
    assert bank_info()["technical_questions"] == 207
    assert bank_info()["by_difficulty"] == {"easy": 69, "medium": 69, "hard": 69}


def test_question_quality():
    bank = technical_bank()["technical"]
    ids, texts = set(), set()
    for skill, questions in bank.items():
        assert skill in SKILL_CATALOG
        for q in questions:
            assert q["id"] not in ids and q["question"] not in texts
            ids.add(q["id"])
            texts.add(q["question"])
            assert len(q["key_points"]) >= 3 and q["explanation"]
            for point in q["key_points"]:
                assert len(point["point"]) >= 5 and point["keywords"]
                assert all(k == k.lower() and k.strip() for k in point["keywords"])
    behavioral_ids = {q["id"] for q in behavioral_bank()["questions"]}
    assert not ids & behavioral_ids and len(behavioral_ids) == 12


def test_banks_contain_no_links():
    for data in (technical_bank(), behavioral_bank()):
        text = json.dumps(data).lower()
        assert "http://" not in text and "https://" not in text and "www." not in text


def mutate(data, fn):
    data = copy.deepcopy(data)
    fn(data)
    return data


@pytest.mark.parametrize("change, message", [
    (lambda d: d["technical"].__setitem__("Quantum Basket Weaving", d["technical"]["Git"]), "Unknown skill"),
    (lambda d: d["technical"]["Git"][1].__setitem__("id", d["technical"]["Git"][0]["id"]), "duplicate"),
    (lambda d: d["technical"]["Git"][0].__setitem__("difficulty", "expert"), "difficulty"),
    (lambda d: d["technical"]["Git"][0].__setitem__("key_points", d["technical"]["Git"][0]["key_points"][:1]), "two key points"),
    (lambda d: d["technical"]["Git"][0]["key_points"][0].__setitem__("keywords", []), "keywords"),
    (lambda d: d["technical"]["Git"][0]["key_points"][0].__setitem__("keywords", ["Merge"]), "lower-case"),
    (lambda d: d["technical"]["Git"][0].__setitem__("explanation", "see https://example.com"), "links"),
    (lambda d: d["technical"]["Git"][0].__setitem__("question", "Git"), "full question"),
])
def test_invalid_technical_bank_rejected(change, message):
    with pytest.raises(ValueError, match=message):
        validate_technical_bank(mutate(technical_bank(), change))


@pytest.mark.parametrize("change", [
    lambda d: d["questions"].append(dict(d["questions"][0])),
    lambda d: d["questions"][0].__setitem__("theme_keywords", []),
    lambda d: d["questions"][0].__setitem__("difficulty", "trivial"),
])
def test_invalid_behavioral_bank_rejected(change):
    with pytest.raises(ValueError):
        validate_behavioral_bank(mutate(behavioral_bank(), change))
