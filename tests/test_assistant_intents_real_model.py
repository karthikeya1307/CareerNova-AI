"""Phase 8: the optional semantic intent stage with the real local MiniLM model.

Calibration (threshold 0.55, margin 0.05): off-topic questions scored at most
0.41 and are never classified; paraphrases without rule keywords are either
classified correctly or fall back to "unknown" (never a confident wrong guess
in this set).
"""

import pytest

from backend.services import embeddings
from backend.services.assistant.intents import SemanticIntent, understand


@pytest.fixture(scope="module")
def semantic():
    return SemanticIntent(embeddings.SentenceTransformerEmbedder())


@pytest.mark.parametrize("question, intent", [
    ("which abilities don't I have yet for these jobs", "skill_gap"),
    ("can you quiz me before my interview", "interview_prep"),
    ("do I have any interviews coming up soon", "upcoming_interviews"),
    ("how am I doing with my job hunt overall", "dashboard"),
    ("any news on the jobs I sent my cv to", "application_status"),
    ("got anything in machine learning for me", "internship_search"),
])
def test_paraphrases(semantic, question, intent):
    assert understand(question, semantic=semantic).intent == intent


def test_uncertain_paraphrase_falls_back_to_unknown(semantic):
    assert understand("how would I go about getting good at kubernetes", semantic=semantic).intent in (
        "learning_plan", "unknown")


@pytest.mark.parametrize("question", [
    "what is the capital of france", "tell me a joke", "who won the cricket match yesterday",
    "what is the weather today", "write a poem about cats", "how do I cook pasta", "i like turtles",
])
def test_off_topic_is_never_classified(semantic, question):
    assert semantic.classify(question) is None
    assert understand(question, semantic=semantic).intent == "unknown"
