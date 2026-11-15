"""Phase 6: semantic evaluation with the real local MiniLM model.

Guards against inflated scores: off-topic, generic and vague answers must
never gain key-point credit; relevant paraphrases without the curated
keywords should.
"""

import pytest

from backend.services import embeddings
from backend.services.answer_evaluator import SEMANTIC_THRESHOLD, SemanticMatcher, evaluate_answer
from backend.services.question_bank import technical_bank

BANK = {q["id"]: q for qs in technical_bank()["technical"].values() for q in qs}
FLUFF = ("I am a hard working and motivated person who always gives the best effort and loves learning "
         "new things every day with my team.")

CASES = {
    "sql-e1": {
        "paraphrase": "An inner join gives back just the records that have partners on each side. A left join keeps "
                      "everything from the first table and fills the gaps with empty values when the second table "
                      "has nothing to pair.",
        "off_topic": "Docker images are templates and containers are their running instances, created from layers "
                     "that are cached during builds.",
        "near_miss": "SQL is a language for databases. I have used it in several projects to store and query data "
                     "for websites and reports.",
    },
    "ml-m1": {
        "paraphrase": "When a model memorises the training examples it does great on them but badly on new data. If "
                      "the model is too basic it misses the patterns entirely. Holding out data for checking, adding "
                      "penalties on complexity, or collecting more examples helps.",
        "off_topic": "React components receive props from their parent and manage their own state, and changing "
                     "state triggers a re-render.",
        "near_miss": "Machine learning is very interesting and I took a course on it. Models learn from data and are "
                     "used in many applications today.",
    },
    "react-e1": {
        "paraphrase": "Values handed down from the parent component cannot be modified by the child. Data the component "
                      "owns itself can change over time, and updating it makes the component draw itself again.",
        "off_topic": "Kubernetes deployments manage replicas of pods, and services give them a stable network address.",
        "near_miss": "React is a JavaScript library made by Meta. I used it to build my portfolio website and I like "
                     "its component approach.",
    },
    "git-e1": {
        "paraphrase": "Combining branches the first way keeps both histories and adds a commit that joins them. The "
                      "second way takes your commits and re-applies them on top of the other branch so the history "
                      "becomes a straight line; do not do this on branches others use.",
        "off_topic": "Big-O notation describes how running time grows with input size, for example O(n) or O(log n).",
        "near_miss": "Git is a version control system. I use it every day with GitHub to save my code and share it "
                     "with classmates.",
    },
}


@pytest.fixture(scope="module")
def matcher():
    return SemanticMatcher(embeddings.SentenceTransformerEmbedder())


def question(qid):
    q = BANK[qid]
    return {"category": "technical", "key_points": q["key_points"], "context": {}, "skill": None}


@pytest.mark.parametrize("qid", list(CASES))
def test_irrelevant_answers_never_gain_semantic_credit(matcher, qid):
    for kind in ("off_topic", "near_miss"):
        result = evaluate_answer(question(qid), CASES[qid][kind], [], matcher)
        semantic_hits = [p for p in result["covered_points"] if p["matched_by"] == "semantic"]
        assert semantic_hits == [], (qid, kind, semantic_hits)
        assert result["score"] <= 25, (qid, kind, result["score"])
    fluff = evaluate_answer(question(qid), FLUFF, [], matcher)
    assert fluff["score"] <= 25 and not fluff["covered_points"]


@pytest.mark.parametrize("qid", list(CASES))
def test_relevant_paraphrase_scores_above_irrelevant_answers(matcher, qid):
    paraphrase = evaluate_answer(question(qid), CASES[qid]["paraphrase"], [], matcher)
    keyword_only = evaluate_answer(question(qid), CASES[qid]["paraphrase"], [], None)
    near_miss = evaluate_answer(question(qid), CASES[qid]["near_miss"], [], matcher)

    assert paraphrase["score"] > near_miss["score"]
    assert paraphrase["score"] >= keyword_only["score"]
    assert paraphrase["method"] == "keyword+semantic"


def test_semantic_improves_recall_overall(matcher):
    with_semantic = sum(evaluate_answer(question(q), c["paraphrase"], [], matcher)["score"] for q, c in CASES.items())
    keyword_only = sum(evaluate_answer(question(q), c["paraphrase"], [], None)["score"] for q, c in CASES.items())
    assert with_semantic > keyword_only
    assert 0.45 <= SEMANTIC_THRESHOLD <= 0.6


INVERTED = {
    "python-e1": "Lists are immutable while tuples are mutable. Tuples cannot be dictionary keys because they are "
                 "not hashable. Lists use parentheses and tuples use square brackets.",
    "sql-e1": "An INNER JOIN returns all rows from the left table even when there is no match, while a LEFT JOIN "
              "returns only the rows that match in both tables.",
    "docker-e1": "A container is the read-only template that you build from a Dockerfile, and an image is the "
                 "running instance created from that container.",
}


@pytest.mark.parametrize("qid", list(INVERTED))
def test_inverted_answers_stay_low_even_with_semantic_matching(matcher, qid):
    # Embeddings rate an inverted statement as very similar to the correct one, so the
    # misconception check must win over semantic credit.
    result = evaluate_answer(question(qid), INVERTED[qid], [], matcher)
    assert result["incorrect_statements"]
    assert result["score"] <= 55 and result["label"] in ("Fair", "Needs work")
