"""Assignment 2: product-guide retrieval with the real local MiniLM model.

Checks the calibration behind ``product_help.ANSWER_THRESHOLD`` (0.40): covered product questions
retrieve the right guide section above it; product topics the guide doesn't cover and unrelated
questions stay below it, so they get the "not covered" or "only CareerNova AI" fallback.
"""

import pytest

from backend.services import embeddings, product_kb
from backend.services.assistant.product_help import ANSWER_THRESHOLD


@pytest.fixture(scope="module")
def index():
    product_kb.clear_cache()
    yield product_kb.get_index(embeddings.SentenceTransformerEmbedder())
    product_kb.clear_cache()


@pytest.mark.parametrize("question, document", [
    ("What is CareerNova AI?", "01_overview"),
    ("Is my data private?", "01_overview"),
    ("How do I upload my resume?", "03_resume_upload"),
    ("Which file types can I upload?", "03_resume_upload"),
    ("How does internship matching work?", "04_internship_matching"),
    ("How is the compatibility score calculated?", "04_internship_matching"),
    ("How do I create a cover letter?", "05_cover_letters"),
    ("What is mock mode?", "06_interview_preparation"),
    ("Are reminders sent by email?", "07_applications_and_assistant"),
])
def test_covered_questions_find_their_section(index, question, document):
    top = index.search(question, 1)[0]
    assert top.chunk.id.startswith(document) and top.score >= ANSWER_THRESHOLD


@pytest.mark.parametrize("question", [
    "How much does a premium subscription cost?", "Can I export my data to LinkedIn?",
    "What is the capital of France?", "Write me a poem about the sea", "How do I cook pasta?",
])
def test_uncovered_and_unrelated_questions_stay_below_the_threshold(index, question):
    assert index.search(question, 1)[0].score < ANSWER_THRESHOLD


# ------------------------------------------------------------------
# Routing with the real model (in memory; no database)
# ------------------------------------------------------------------

class Turn:
    def __init__(self, query):
        self.entities = {"product_query": query}


@pytest.fixture(scope="module")
def ask(index):
    from types import SimpleNamespace

    from backend.services.assistant import product_help
    from backend.services.assistant.intents import SemanticIntent, understand

    semantic = SemanticIntent(index.embedder)
    state = {"previous": None}
    original = product_help.previous_product_turn
    product_help.previous_product_turn = lambda db, conversation: state["previous"]
    conversation = SimpleNamespace(context={}, conversation_id=0)

    def _ask(text, fresh=False):
        if fresh:
            state["previous"] = None
        u = understand(text, semantic=semantic)
        route = product_help.route(None, conversation, text, u.intent, u.ordinal, u.referent, embedder=index.embedder)
        state["previous"] = Turn(route.query) if route and route.intent == "product_help" else None
        return u, route

    yield _ask
    product_help.previous_product_turn = original


@pytest.mark.parametrize("question, document", [
    ("What is this application?", "01_overview"),
    ("What features does this app have?", "01_overview"),
    ("How do I upload my resume?", "03_resume_upload"),
    ("How does internship matching work?", "04_internship_matching"),
    ("How can I generate a cover letter?", "05_cover_letters"),
    ("How does interview preparation work?", "06_interview_preparation"),
    ("Is my data private?", "01_overview"),
])
def test_required_product_questions_are_answered_from_the_right_section(ask, question, document):
    _, route = ask(question, fresh=True)
    assert route.intent == "product_help" and route.result.status == "ok"
    assert route.result.sources()[0]["id"].startswith(document)
    texts = {c.id: c.text for c in product_kb.load_chunks()}
    assert all(any(f.text in texts[s.id] for s in f.sources) for f in route.result.facts)   # verbatim, cited


@pytest.mark.parametrize("question", ["What is the product pricing?", "What is the price of this product?"])
def test_pricing_is_not_covered(ask, question):
    _, route = ask(question, fresh=True)
    assert route.intent == "product_help" and route.result.status == "empty" and route.result.sources() == []


def test_unrelated_topic_is_declined(ask):
    _, route = ask("Can you explain photosynthesis?", fresh=True)
    assert route.intent == "unknown" and route.result.sources() == []


def test_follow_up_memory_and_new_standalone_question(ask):
    ask("How can I generate a cover letter?", fresh=True)
    _, follow = ask("How do I do that?")
    assert follow.followup and follow.result.sources()[0]["id"].startswith("05_cover_letters")
    _, download = ask("can I download it?")
    assert download.followup and any("download" in f.text for f in download.result.facts)
    _, new_topic = ask("Is my data private?")
    assert not new_topic.followup and new_topic.result.sources()[0]["id"].startswith("01_overview")


@pytest.mark.parametrize("question", ["who is ronaldo", "where is paris", "who won the world cup"])
def test_short_unrelated_question_is_not_merged_with_the_previous_product_question(ask, question):
    ask("How do I upload my resume?", fresh=True)
    _, route = ask(question)
    assert route.intent == "unknown" and not route.followup and route.result.sources() == []


def test_what_about_an_unknown_name_is_left_to_the_data_tools_not_the_guide(ask):
    ask("How do I upload my resume?", fresh=True)
    _, route = ask("what about messi?")
    assert route is None                     # not a product answer; the data tools ask which item is meant


def test_short_follow_up_that_refers_back_keeps_the_memory(ask):
    ask("How do I upload my resume?", fresh=True)
    _, follow = ask("how big can it be?")
    assert follow.followup and follow.result.sources()[0]["id"].startswith("03_resume_upload")
    _, formats = ask("what formats?")                       # answered on its own (scores above the threshold)
    assert formats.intent == "product_help" and formats.result.sources()[0]["id"].startswith("03_resume_upload")


@pytest.mark.parametrize("question", ["What is the status of this application?", "what happened with my application",
                                      "What skills are on my resume?", "show my applications"])
def test_data_questions_keep_the_existing_assistant_tools(ask, question):
    _, route = ask(question, fresh=True)
    assert route is None
