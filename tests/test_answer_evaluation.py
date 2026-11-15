"""Phase 6: deterministic answer evaluation (no database, keyword path)."""

import numpy as np
import pytest

from backend.services.answer_evaluator import (
    SEMANTIC_THRESHOLD,
    SemanticMatcher,
    default_semantic_matcher,
    evaluate_answer,
    keyword_hit,
    label_for,
)
from backend.services.interview_generator import STAR_POINTS
from backend.services.question_bank import behavioral_bank, technical_bank

SQL_Q = next(q for q in technical_bank()["technical"]["SQL"] if q["id"] == "sql-e1")
TECH = {"category": "technical", "key_points": SQL_Q["key_points"], "context": {}, "skill": "SQL"}
CONFLICT = next(q for q in behavioral_bank()["questions"] if q["id"] == "beh-conflict")
BEHAVIORAL = {"category": "behavioral", "key_points": STAR_POINTS,
              "context": {"theme_keywords": CONFLICT["theme_keywords"]}}
PROJECT = {"category": "project", "context": {"fact_skills": ["Docker", "FastAPI"]}, "key_points": [
    {"point": "Context", "keywords": ["inventory"]},
    {"point": "Role", "keywords": ["i "]},
    {"point": "Tech", "keywords": ["docker", "fastapi"]},
    {"point": "Outcome", "keywords": ["result", "learn", "users"]},
]}
SKILLS = ["Python", "SQL", "Docker", "FastAPI"]

GOOD_SQL = ("An inner join returns only the rows that match in both tables. A left join returns all rows "
            "from the left table, and where there is no match the right-side columns are NULL. I use left "
            "joins when I need every customer even if they have no orders, for example in a monthly report.")


def test_technical_full_partial_none():
    full = evaluate_answer(TECH, GOOD_SQL, SKILLS)
    partial = evaluate_answer(TECH, "An inner join only keeps rows that match in both tables, which is the "
                                    "most common join in reporting queries and dashboards.", SKILLS)
    none = evaluate_answer(TECH, "Docker images are templates and containers are their running instances "
                                 "that you can start many times from one image on a server.", SKILLS)
    assert full["score"] >= 80 and full["label"] == "Excellent" and not full["missed_points"]
    assert 20 < partial["score"] < full["score"]
    assert none["score"] <= 20 and len(none["missed_points"]) == 3
    assert full["method"] == "keyword"


@pytest.mark.parametrize("answer, cap", [("", 0), ("Inner join matches both tables.", 20)])
def test_empty_and_short_answers_are_capped(answer, cap):
    result = evaluate_answer(TECH, answer, SKILLS)
    assert result["score"] <= cap


def test_behavioral_star_and_theme():
    star = ("When I was working on a group project at college, a teammate and I disagreed about the database "
            "design. My task was to agree a design before the deadline. I suggested we compare both options "
            "against our requirements, I listened to his concerns and we discussed the trade-offs together. "
            "As a result we chose a combined design, finished on time, and I learned to resolve conflicts by "
            "focusing on shared goals.")
    off_theme = ("When I was at college my task was to build a website. I built the pages and I created the "
                 "database. As a result the website worked well and I learned a lot about programming and "
                 "about building websites from scratch with my own code.")
    good = evaluate_answer(BEHAVIORAL, star, SKILLS)
    off = evaluate_answer(BEHAVIORAL, off_theme, SKILLS)
    assert good["score"] >= 80 and all(good["star"].values())
    assert off["score"] <= 50 and off["tips"][0].startswith("Make sure your example directly answers")


def test_behavioral_missing_parts_get_tips():
    result = evaluate_answer(BEHAVIORAL, "We disagreed about something once and then it was fine in the end "
                                         "after some talking between everyone involved.", SKILLS)
    assert any("Action" in tip or "action" in tip for tip in result["tips"])
    assert result["score"] < 65


def test_project_rubric():
    good = ("The Inventory API was a service for tracking stock. I designed the endpoints with FastAPI and I "
            "containerised it with Docker so the team could deploy it easily. As a result it was used by our "
            "class for the whole semester and I learned how to structure an API.")
    weak = "It was a project I did with some tools for a class and it worked fine overall in the end."
    assert evaluate_answer(PROJECT, good, SKILLS)["score"] >= 80
    weak_result = evaluate_answer(PROJECT, weak, SKILLS)
    assert weak_result["score"] < 45 and weak_result["tips"]


def test_internship_rubric_and_missing_skill_question():
    question = {"category": "internship", "context": {"kind": "motivation", "company": "Nimbus Analytics",
                                                      "title": "Backend Developer Intern", "domain": "Software Development"},
                "key_points": [{"point": "role", "keywords": ["nimbus", "analytics", "backend", "developer"]},
                               {"point": "skills", "keywords": ["python"]}, {"point": "learn", "keywords": ["learn"]}]}
    good = ("I want to join Nimbus Analytics as a backend developer because I enjoy building APIs. I have used "
            "Python and Docker in my projects and I want to learn how software development works at scale.")
    generic = "I want a job because it is a good opportunity for me and I like working hard every day."
    assert evaluate_answer(question, good, SKILLS)["score"] >= 80
    assert evaluate_answer(question, generic, SKILLS)["score"] < 45

    missing = {"category": "internship", "context": {"kind": "missing_skill", "skill": "Kubernetes"}, "key_points": [
        {"point": "honest", "keywords": ["not yet", "new to", "beginner"]},
        {"point": "plan", "keywords": ["kubernetes", "plan", "course", "practice"]},
        {"point": "related", "keywords": ["docker"]}]}
    answer = ("Kubernetes is new to me, but I already use Docker. My plan is to take a short course, practice "
              "with a local cluster and deploy one of my own projects to learn it properly.")
    result = evaluate_answer({**missing, "skill": "Kubernetes"}, answer, SKILLS)
    assert result["score"] >= 65 and result["advisories"] == []


def test_unsupported_skill_claims_are_advisory_only():
    answer = GOOD_SQL + " I also used Kubernetes and Terraform to deploy the reporting service."
    with_claims = evaluate_answer(TECH, answer, SKILLS)
    assert {a.split(",")[0] for a in with_claims["advisories"]} == {"You mentioned Kubernetes", "You mentioned Terraform"}
    assert with_claims["score"] == evaluate_answer(TECH, GOOD_SQL + " I also deployed the reporting service.",
                                                   SKILLS)["score"]


def test_scores_bounded_and_consistent_structure():
    for question in (TECH, BEHAVIORAL, PROJECT):
        for answer in ("", "x", GOOD_SQL, "word " * 2000):
            result = evaluate_answer(question, answer, SKILLS)
            assert 0 <= result["score"] <= 100
            assert result["label"] == label_for(result["score"])
            assert {"score", "label", "components", "tips", "advisories", "feedback", "category"} <= set(result)


@pytest.mark.parametrize("score, label", [(0, "Needs work"), (44.9, "Needs work"), (45, "Fair"),
                                          (64.9, "Fair"), (65, "Good"), (79.9, "Good"), (80, "Excellent")])
def test_labels(score, label):
    assert label_for(score) == label


def test_keyword_matching_is_prefix_at_word_start():
    text = " i normalised the data and used the mutable list "
    assert keyword_hit(text, ["normali", "mutable", "immutable", "table"]) == ["normali", "mutable"]


def test_test_embedder_keeps_evaluation_deterministic():
    assert default_semantic_matcher() is None       # hashing test embedder is not the configured model


class FixedEmbedder:
    """Returns vectors whose similarity to the first text is controlled."""
    model_name, revision, dimension = "fixed", "x", 2

    def __init__(self, similarity):
        self.similarity = similarity

    def embed(self, texts):
        s = self.similarity
        return np.array([[1.0, 0.0]] + [[s, (1 - s * s) ** 0.5]] * (len(texts) - 1), dtype="float32")


def test_semantic_matching_uses_threshold():
    answer = "Rows that pair up on both sides come back and everything else is dropped from the output."
    above = evaluate_answer(TECH, answer, SKILLS, SemanticMatcher(FixedEmbedder(SEMANTIC_THRESHOLD + 0.01)))
    below = evaluate_answer(TECH, answer, SKILLS, SemanticMatcher(FixedEmbedder(SEMANTIC_THRESHOLD - 0.01)))
    assert above["components"]["key_point_coverage"] == 1.0
    assert all(p["matched_by"] == "semantic" for p in above["covered_points"])
    assert below["components"]["key_point_coverage"] == 0.0
