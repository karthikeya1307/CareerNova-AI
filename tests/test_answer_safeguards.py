"""Phase 6 review fixes: incorrect, uncertain and keyword-only answers must not score highly.

Keyword path only (no embedding model); the real-model variant lives in
test_answer_evaluation_real_model.py.
"""

import json

import pytest

from backend.services.answer_evaluator import (
    COVERAGE_DISCLAIMER,
    KEYWORD_LIST_CAP,
    MANY_MISCONCEPTIONS_CAP,
    ONE_MISCONCEPTION_CAP,
    THIN_STAR_CAP,
    UNCERTAIN_CAP,
    evaluate_answer,
    is_keyword_list,
    misconception_hits,
    split_sentences,
)
from backend.services.interview_generator import STAR_POINTS
from backend.services.question_bank import (
    MISCONCEPTIONS_PATH,
    TECHNICAL_PATH,
    bank_info,
    behavioral_bank,
    technical_bank,
    validate_misconceptions,
)

BANK = {q["id"]: q for qs in technical_bank()["technical"].values() for q in qs}
SKILLS = ["Python", "SQL", "Docker"]


def technical(qid):
    return {"category": "technical", "key_points": BANK[qid]["key_points"], "context": {}, "skill": None}


TEAMWORK = next(q for q in behavioral_bank()["questions"] if q["id"] == "beh-teamwork")
BEHAVIORAL = {"category": "behavioral", "key_points": STAR_POINTS,
              "context": {"theme_keywords": TEAMWORK["theme_keywords"]}}

# (question, correct answer, technically wrong answer that uses the right keywords)
PAIRS = {
    "python-e1": (
        "A list is mutable, so you can append or change items, while a tuple is immutable once created. Because "
        "tuples of hashable items are hashable they can be used as dictionary keys. Lists are written with square "
        "brackets and tuples with parentheses.",
        "Lists are immutable while tuples are mutable. Tuples cannot be dictionary keys because they are not "
        "hashable. Lists use parentheses and tuples use square brackets, so you can append to a tuple.",
    ),
    "sql-e1": (
        "An inner join returns only the rows that match in both tables. A left join returns all rows from the left "
        "table, and where there is no match the right-side columns are NULL. I use left joins when I need every "
        "customer even if they have no orders.",
        "An INNER JOIN returns all rows from the left table even when there is no match, filling NULLs, while a "
        "LEFT JOIN returns only the rows that match in both tables. They usually give the same result.",
    ),
    "docker-e1": (
        "An image is a read-only template built from a Dockerfile. A container is a running instance of that "
        "image with its own writable layer. You can start many containers from one image.",
        "A container is the read-only template that you build from a Dockerfile, and an image is the running "
        "instance created from that container. You can run only one image per container.",
    ),
    "rest-h1": (
        "Idempotent means repeating the same request has the same effect as sending it once. GET, PUT and DELETE "
        "are idempotent, but POST is not, which matters when clients retry after a timeout.",
        "Idempotent means repeating the same request has the same effect. POST is idempotent and GET is not "
        "idempotent, so it is safe to retry a POST request after a timeout.",
    ),
    "stats-m1": (
        "The p-value is the probability of getting results at least this extreme if the null hypothesis is true. "
        "We compare it with a significance level such as 0.05. A small p-value is evidence against the null, but "
        "it is not proof.",
        "The p-value is the probability that the null hypothesis is true. We compare it with a significance level "
        "such as 0.05, and a small p-value proves the alternative hypothesis.",
    ),
}


# ------------------------------------------------------------------
# Incorrect technical statements
# ------------------------------------------------------------------

@pytest.mark.parametrize("qid", list(PAIRS))
def test_incorrect_answers_with_the_right_keywords_are_capped(qid):
    correct, wrong = PAIRS[qid]
    good = evaluate_answer(technical(qid), correct, SKILLS)
    bad = evaluate_answer(technical(qid), wrong, SKILLS)
    assert good["score"] >= 65 and not good["incorrect_statements"], good
    assert bad["incorrect_statements"], bad
    cap = ONE_MISCONCEPTION_CAP if len(bad["incorrect_statements"]) == 1 else MANY_MISCONCEPTIONS_CAP
    assert bad["score"] <= cap and bad["label"] in ("Fair", "Needs work")
    assert bad["score"] < good["score"] - 20
    assert "Possible mistakes:" in bad["feedback"]
    assert all(m["reason"] == "incorrect_statement" for m in bad["missed_points"]
               if m["point"] in {i["point"] for i in bad["incorrect_statements"]})


def test_reported_python_case_drops_from_excellent():
    _, wrong = PAIRS["python-e1"]
    result = evaluate_answer(technical("python-e1"), wrong, SKILLS)
    assert result["score"] <= MANY_MISCONCEPTIONS_CAP and len(result["incorrect_statements"]) == 3
    assert result["components"]["key_point_coverage"] == 0.0


def test_rejecting_a_misconception_is_not_penalised():
    answer = ("Lists are mutable and tuples are immutable; it is a common misconception that lists are immutable. "
              "Tuples of hashable values are hashable, so they work as dictionary keys, and lists are not hashable. "
              "Lists use square brackets and tuples use parentheses.")
    result = evaluate_answer(technical("python-e1"), answer, SKILLS)
    assert not result["incorrect_statements"] and result["score"] >= 80


@pytest.mark.parametrize("sentence", [
    "Lists are mutable but tuples are immutable.",
    "You should never rebase shared branches that other people use.",
    "Correlation does not imply causation.",
    "Do not store secrets in the source code; use Key Vault instead.",
    "Indexes speed up reads but slow down inserts and updates.",
    "Binary search needs sorted data and runs in O(log n) time.",
    "A Pod can run one or more containers.",
    "Readiness probes control whether a Pod receives traffic, while liveness probes restart containers.",
    "Basic slicing returns a view, so changing the view changes the original array.",
    "A LEFT JOIN returns all rows from the left table and fills missing matches with NULL.",
])
def test_correct_statements_do_not_trigger_misconceptions(sentence):
    every = [m for q in BANK.values() for p in q["key_points"] for m in p.get("misconceptions", [])]
    assert misconception_hits(sentence, every) == []


def test_misconceptions_never_match_the_banks_own_correct_text():
    for qid, q in BANK.items():
        entries = [m for p in q["key_points"] for m in p.get("misconceptions", [])]
        texts = [p["point"] for p in q["key_points"]] + split_sentences(q["explanation"]) + [q["question"]]
        for text in texts:
            assert misconception_hits(text, entries) == [], (qid, text)


def test_misconception_coverage_and_validation():
    info = bank_info()
    assert info["questions_with_misconception_checks"] >= 140
    assert info["skills_with_misconception_checks"] >= 60
    assert info["technical_version"] == info["misconception_version"] == "2026.11-v2"

    raw = json.loads(TECHNICAL_PATH.read_text(encoding="utf-8"))
    good = json.loads(MISCONCEPTIONS_PATH.read_text(encoding="utf-8"))
    validate_misconceptions(good, raw)
    entry = {"point": 0, "patterns": [r"\bx is y"], "note": "x is not y"}
    for broken in (
        {"version": "v", "misconceptions": {"no-such-id": [entry]}},
        {"version": "v", "misconceptions": {"python-e1": [{**entry, "point": 9}]}},
        {"version": "v", "misconceptions": {"python-e1": [{**entry, "patterns": [r"\bLists"]}]}},
        {"version": "v", "misconceptions": {"python-e1": [{**entry, "patterns": ["(unclosed"]}]}},
        {"version": "v", "misconceptions": {"python-e1": [{**entry, "note": ""}]}},
        {"version": "v", "misconceptions": {"python-e1": [{**entry, "note": "see https://example.com"}]}},
    ):
        with pytest.raises(ValueError):
            validate_misconceptions(broken, raw)


def test_oversimplified_key_points_were_corrected():
    assert "items are hashable" in BANK["python-e1"]["key_points"][1]["point"]
    assert "O(n)" in BANK["ds-e1"]["key_points"][1]["point"]
    assert "upper bound" in BANK["algo-e1"]["key_points"][1]["point"]
    assert "faster" not in BANK["net-e1"]["key_points"][1]["point"]
    assert BANK["numpy-h1"]["key_points"][0]["point"].startswith("Basic slicing")


# ------------------------------------------------------------------
# Uncertainty
# ------------------------------------------------------------------

def test_i_dont_know_answers_get_no_credit():
    answer = ("Honestly I do not know whether lists are mutable or immutable, and I have never understood "
              "hashable dictionary keys or square brackets versus parentheses at all.")
    result = evaluate_answer(technical("python-e1"), answer, SKILLS)
    assert result["score"] <= UNCERTAIN_CAP and result["uncertain_sentences"] == 1
    assert result["components"]["key_point_coverage"] == 0.0


def test_only_the_confident_part_earns_credit():
    answer = ("An inner join returns only the rows that match in both tables, which is what most reports need. "
              "I'm not sure what a left join does with all rows from the left table or with NULL values.")
    result = evaluate_answer(technical("sql-e1"), answer, SKILLS)
    assert [p["point"] for p in result["covered_points"]] == [BANK["sql-e1"]["key_points"][0]["point"]]
    assert result["uncertain_sentences"] == 1
    assert result["score"] <= UNCERTAIN_CAP + 15


# ------------------------------------------------------------------
# Keyword-only answers
# ------------------------------------------------------------------

@pytest.mark.parametrize("question, answer", [
    (technical("python-e1"), "mutable immutable hashable dictionary keys square brackets parentheses list tuple"),
    (technical("sql-e1"), "inner join match in both tables left table all rows null left join inner join"),
    ({"category": "project", "context": {"fact_skills": ["Docker", "FastAPI"]}, "key_points": [
        {"point": "Context", "keywords": ["inventory"]}, {"point": "Role", "keywords": ["i "]},
        {"point": "Tech", "keywords": ["docker", "fastapi"]}, {"point": "Outcome", "keywords": ["result", "learn"]}]},
     "Inventory API Docker FastAPI result learned users deployed built containerised"),
])
def test_keyword_lists_are_capped(question, answer):
    assert is_keyword_list(answer)
    result = evaluate_answer(question, answer, SKILLS)
    assert result["score"] <= KEYWORD_LIST_CAP and "keyword_list" in result["caps_applied"]
    assert result["tips"][0].startswith("Write full sentences")


def test_real_sentences_are_not_treated_as_keyword_lists():
    assert not is_keyword_list(PAIRS["sql-e1"][0])
    assert not is_keyword_list("A container is a running instance of an image.")
    # Terse but correct answers built from every question's own key points are never flagged.
    for q in BANK.values():
        terse = ". ".join(p["point"] for p in q["key_points"]) + "."
        assert not is_keyword_list(terse), (q["id"], terse)
        assert not is_keyword_list(q["explanation"]), q["id"]


def test_comma_separated_keyword_list_is_detected():
    assert is_keyword_list("mutable, immutable, hashable, dictionary keys, square brackets, parentheses, list, tuple.")


# ------------------------------------------------------------------
# Behavioral STAR
# ------------------------------------------------------------------

def test_star_word_stuffing_is_capped():
    stuffed = ("Situation task goal result outcome learn. I worked, I led, I built, my team, during the situation I "
               "had to finally improve the result and in the end I learned teamwork team collaborate.")
    result = evaluate_answer(BEHAVIORAL, stuffed, SKILLS)
    assert result["score"] <= THIN_STAR_CAP and "thin_story" in result["caps_applied"]


def test_real_star_story_still_scores_well():
    story = ("During my third semester our team of four had to build a library app in six weeks. My task was to "
             "own the backend while two teammates handled the interface. When we fell behind, I suggested short "
             "daily check-ins and I paired with a colleague on the API. As a result we delivered on time and I "
             "learned how much clear communication helps a team.")
    result = evaluate_answer(BEHAVIORAL, story, SKILLS)
    assert result["score"] >= 80 and all(result["star"].values()) and result["real_sentences"] == 4


def test_two_sentence_story_is_limited():
    short = ("When our team project fell behind, I organised a meeting and we split the remaining tasks together. "
             "As a result we finished on time and I learned to plan earlier with my team.")
    result = evaluate_answer(BEHAVIORAL, short, SKILLS)
    assert result["score"] <= THIN_STAR_CAP


# ------------------------------------------------------------------
# Labelling
# ------------------------------------------------------------------

def test_technical_scores_are_labelled_as_coverage_not_correctness():
    result = evaluate_answer(technical("sql-e1"), PAIRS["sql-e1"][0], SKILLS)
    assert result["score_basis"] == "key_point_coverage" and result["correctness_verified"] is False
    assert result["feedback"].startswith("Key-point coverage") and COVERAGE_DISCLAIMER in result["feedback"]
    story = evaluate_answer(BEHAVIORAL, "I worked with my team on a project and we finished it together.", SKILLS)
    assert "score_basis" not in story and COVERAGE_DISCLAIMER not in story["feedback"]
