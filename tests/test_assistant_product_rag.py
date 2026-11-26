"""Assignment 2: RAG-based product assistant with conversational memory.

The product guide (backend/data/product_docs) is chunked, embedded and searched with FAISS; product
questions are answered only from the retrieved chunks, follow-ups use the previous product question,
other topics are declined, and the optional AI answer must be grounded in the cited excerpts.

Retrieval here uses ``TopicEmbedder`` (a deterministic keyword-topic embedder) so the relevance
threshold behaves predictably without downloading a model; the real-model calibration is recorded in
``backend/services/assistant/product_help.py`` and in ``tests/test_assistant_product_rag_real_model.py``.
"""

import re

import pytest
from sqlalchemy import select

from assistant_support import ask, new_conversation
from backend.models import Conversation
from backend.services import product_kb
from backend.services.assistant import product_help

TOPICS = [
    ("resume", "cv", "upload", "file", "pdf", "docx", "pars", "mb"),
    ("match", "compatib", "score", "rank"),
    ("cover", "letter", "tailor"),
    ("interview", "mock", "practice", "question"),
    ("privacy", "private", "personal", "consent"),
    ("reminder", "email", "notif"),
]


class TopicEmbedder:
    """Counts keyword topics; text with no product topic embeds to the zero vector (similarity 0)."""

    model_name, revision, dimension = "test-topics", "test", len(TOPICS)

    def embed(self, texts):
        import numpy as np

        rows = []
        for text in texts:
            words = re.findall(r"[a-z0-9]+", text.lower())
            rows.append([sum(1 for w in words for stem in group if w.startswith(stem)) for group in TOPICS])
        return np.asarray(rows, dtype="float32")


@pytest.fixture
def topics(monkeypatch):
    embedder = TopicEmbedder()
    original = product_kb.get_index
    monkeypatch.setattr(product_kb, "get_index",
                        lambda embedder_=None, directory=product_kb.DOCS_DIR: original(embedder_ or embedder, directory))
    # Routing picks its embedder first (neural model or keyword fallback); use the topic embedder there too.
    monkeypatch.setattr(product_kb, "default_embedder", lambda directory=product_kb.DOCS_DIR: embedder)
    product_kb.clear_cache()
    yield embedder
    product_kb.clear_cache()


@pytest.fixture
def user(create_user):
    return create_user()


def doc_ids(answer):
    return [s["id"].split("#")[0] for s in answer["sources"] if s["type"] == "product_doc"]


# ------------------------------------------------------------------
# Knowledge base: chunking and the vector index
# ------------------------------------------------------------------

def test_guide_covers_the_required_topics():
    chunks = product_kb.load_chunks()
    documents = {c.id.split("#")[0] for c in chunks}
    assert {"01_overview", "02_workflow", "03_resume_upload", "04_internship_matching", "05_cover_letters",
            "06_interview_preparation"} <= documents
    assert len({c.id for c in chunks}) == len(chunks)
    assert all(c.text and c.heading and c.document for c in chunks)
    assert max(len(c.text) for c in chunks) <= product_kb.MAX_CHUNK_CHARS + 300


def test_chunking_splits_sections_and_windows_long_ones_with_overlap():
    long_body = " ".join(f"Sentence number {n} explains one detail of the feature." for n in range(40))
    md = f"# Guide title\n\nIntro line.\n\n## First section\n- Bullet one.\n- Bullet two.\n\n## Long section\n{long_body}\n"
    chunks = product_kb.chunk_markdown("99_test", md)
    assert chunks[0].heading == "Overview" and chunks[0].text == "Intro line."
    assert chunks[1].heading == "First section" and chunks[1].text == "Bullet one. Bullet two."
    long = [c for c in chunks if c.heading == "Long section"]
    assert len(long) > 1 and all(len(c.text) <= product_kb.MAX_CHUNK_CHARS for c in long)
    last_of_first = product_kb.split_sentences(long[0].text)[-1]
    assert long[1].text.startswith(last_of_first)                         # one sentence of overlap
    assert [c.id for c in chunks] == [f"99_test#{n}" for n in range(1, len(chunks) + 1)]
    assert chunks[1].label == "Product guide: Guide title › First section"


def test_vector_retrieval_ranks_the_relevant_section_first(topics):
    hits = product_kb.retrieve("Which file types can I upload for my resume?", k=3)
    assert hits[0].chunk.id.startswith("03_resume_upload") and hits[0].score >= product_help.ANSWER_THRESHOLD
    assert hits == sorted(hits, key=lambda h: -h.score)
    assert product_kb.retrieve("How does the compatibility score work?")[0].chunk.id.startswith("04_internship_matching")
    assert product_kb.retrieve("What is the capital of France?")[0].score == 0


def test_index_is_rebuilt_when_the_guide_changes(tmp_path):
    (tmp_path / "a.md").write_text("# A\n## Resume\nUpload a PDF resume.\n", encoding="utf-8")
    embedder = TopicEmbedder()
    first = product_kb.get_index(embedder, tmp_path)
    assert product_kb.get_index(embedder, tmp_path) is first                # cached
    (tmp_path / "b.md").write_text("# B\n## Interviews\nPractice mock interviews.\n", encoding="utf-8")
    second = product_kb.get_index(embedder, tmp_path)
    assert second is not first and len(second.chunks) == 2
    product_kb.clear_cache()


# ------------------------------------------------------------------
# Routing: product questions vs the student's own data
# ------------------------------------------------------------------

@pytest.mark.parametrize("text,intent,ordinal,referent,expected", [
    ("How do I upload my resume?", "profile_summary", None, False, True),
    ("How does internship matching work?", "internship_search", None, False, True),
    ("What is mock mode?", "unknown", None, False, True),
    ("What skills are on my resume?", "profile_summary", None, False, False),
    ("show my applications", "application_status", None, False, False),
    ("why is the first one a good match?", "match_explain", 1, False, False),
    ("how can I improve my resume for this internship?", "document_help", None, True, False),
])
def test_product_questions_are_told_apart_from_data_questions(text, intent, ordinal, referent, expected):
    assert product_help.is_product_question(text, intent, ordinal, referent) is expected


def test_product_question_is_answered_from_the_guide_with_cited_sections(client, user, topics):
    cid = new_conversation(client, user)
    answer = ask(client, user, cid, "Which file types can I upload for my resume?")
    assert answer["intent"] == "product_help" and answer["generation_method"] == "deterministic"
    assert answer["content"].startswith("Here is what the CareerNova AI guide says:")
    assert "PDF" in answer["content"] and "DOCX" in answer["content"]
    assert doc_ids(answer) and set(doc_ids(answer)) == {"03_resume_upload"}
    assert all(s["label"].startswith("Product guide: ") and s["available"] for s in answer["sources"])
    chunks = {c.id: c.text for c in product_kb.load_chunks()}
    for line in answer["content"].splitlines()[1:]:                        # every sentence is from the guide
        sentence = line.lstrip("- ").strip()
        assert any(sentence in chunks[s["id"]] for s in answer["sources"]), sentence
    listed = client.get("/assistant/conversations", headers=user["headers"]).json()["items"]
    assert listed[0]["title"] == "About CareerNova AI"


def test_follow_up_question_uses_conversational_memory(client, user, topics, db_session):
    cid = new_conversation(client, user)
    ask(client, user, cid, "How do I upload my resume?")
    follow = ask(client, user, cid, "how big can it be?")              # no topic of its own
    assert follow["intent"] == "product_help" and "03_resume_upload" in doc_ids(follow)
    assert "5 MB" in follow["content"]
    context = db_session.scalars(select(Conversation).where(Conversation.conversation_id == cid)).one().context
    assert set(context["product"]) == {"message_id"}                      # a pointer, never the text

    fresh = new_conversation(client, user)                                 # same words without memory
    alone = ask(client, user, fresh, "how big can it be?")
    assert alone["intent"] != "product_help" and not doc_ids(alone)


def test_a_new_self_contained_question_is_not_mixed_with_the_previous_topic(client, user, topics):
    cid = new_conversation(client, user)
    ask(client, user, cid, "What is mock mode in interview practice?")
    privacy = ask(client, user, cid, "Is my data private?")               # short, but a new topic
    assert privacy["intent"] == "product_help" and set(doc_ids(privacy)) == {"01_overview"}


def test_memory_ends_when_the_conversation_moves_to_the_students_data(client, user, topics, db_session):
    cid = new_conversation(client, user)
    ask(client, user, cid, "How do I upload my resume?")
    ask(client, user, cid, "show my applications")
    context = db_session.scalars(select(Conversation).where(Conversation.conversation_id == cid)).one().context
    assert "product" not in (context or {})
    assert not doc_ids(ask(client, user, cid, "how big can it be?"))


def test_product_topic_missing_from_the_guide_gets_a_safe_fallback(client, user, topics):
    cid = new_conversation(client, user)
    for question in ("Does the platform support dark mode?", "How much does a premium subscription cost?"):
        answer = ask(client, user, cid, question)
        assert answer["intent"] == "product_help" and answer["sources"] == []
        assert "guide doesn't cover that" in answer["content"]


def test_questions_about_other_topics_are_declined(client, user, topics):
    cid = new_conversation(client, user)
    for question in ("What is the capital of France?", "Write me a poem about the sea"):
        answer = ask(client, user, cid, question)
        assert answer["intent"] == "unknown" and answer["sources"] == []
        assert "I can only answer questions about CareerNova AI" in answer["content"]
        assert "Paris" not in answer["content"]


def test_short_unrelated_question_after_a_product_answer_is_declined(client, user, topics):
    # Regression (seen in dev on 2026-11-24): "who is ronaldo" right after a product question was read as a
    # short follow-up, merged with that question and answered with product-guide text.
    cid = new_conversation(client, user)
    assert ask(client, user, cid, "How do I upload my resume?")["intent"] == "product_help"
    for question in ("who is ronaldo", "who won the world cup", "where is paris"):
        answer = ask(client, user, cid, question)
        assert answer["intent"] == "unknown" and answer["sources"] == [], question
        assert "I can only answer questions about CareerNova AI" in answer["content"], question
        assert "guide says" not in answer["content"], question
    # "what about X?" may also be a follow-up about the student's own data ("what about Google?"), so the data
    # tools ask which item is meant - still no product-guide text and no sources.
    messi = ask(client, user, cid, "what about messi?")
    assert messi["intent"] != "product_help" and messi["sources"] == [] and "guide says" not in messi["content"]
    # A real short follow-up that refers back still uses the conversation's memory.
    follow = ask(client, user, cid, "How do I upload my resume?")
    follow = ask(client, user, cid, "how big can it be?")
    assert follow["intent"] == "product_help" and "03_resume_upload" in doc_ids(follow)


# ------------------------------------------------------------------
# Optional AI answer: grounded in the retrieved excerpts, with memory
# ------------------------------------------------------------------

def first_answer(client, user, cid, question):
    plain = ask(client, user, cid, question)
    chunk_id = plain["sources"][0]["id"]
    text = next(c.text for c in product_kb.load_chunks() if c.id == chunk_id)
    return chunk_id, product_kb.split_sentences(text)[0]


def test_grounded_ai_answer_is_used_and_gets_the_conversation_history(client, user, topics, fake_llm):
    cid = new_conversation(client, user)
    chunk_id, sentence = first_answer(client, user, cid, "Which file types can I upload for my resume?")
    provider = fake_llm({"answer": f"In short: {sentence}", "cited": [chunk_id]})
    answer = ask(client, user, cid, "and how big can it be?", use_llm=True, llm_consent=True)
    assert answer["generation_method"] == "llm" and answer["content"] == f"In short: {sentence}"
    assert [s["id"] for s in answer["sources"]] == [chunk_id]
    payload = provider.calls[0]["payload"]
    assert payload["question"] == "and how big can it be?"
    assert payload["earlier_conversation"][0]["question"] == "Which file types can I upload for my resume?"
    assert chunk_id in [e["id"] for e in payload["excerpts"]]
    assert "ONLY the guide excerpts" in provider.calls[0]["system"]


@pytest.mark.parametrize("reply", [
    {"answer": "Premium users get unlimited uploads and automatic LinkedIn sync for free.", "cited": None},
    {"answer": None, "cited": []},
    {"answer": "Uploads work.", "cited": ["99_unknown#1"]},
])
def test_unsupported_ai_answers_fall_back_to_the_guide(client, user, topics, fake_llm, reply):
    cid = new_conversation(client, user)
    chunk_id, _ = first_answer(client, user, cid, "Which file types can I upload for my resume?")
    if reply["cited"] is None:
        reply = {**reply, "cited": [chunk_id]}
    fake_llm(reply)
    answer = ask(client, user, cid, "Which file types can I upload for my resume?", use_llm=True, llm_consent=True)
    assert answer["generation_method"] == "deterministic" and "PDF" in answer["content"]
    assert "Premium" not in answer["content"]
    assert any(w["code"] == "llm_unverified" for w in answer["warnings"])


def test_personal_details_are_removed_before_the_question_is_sent(client, user, topics, fake_llm, db_session):
    cid = new_conversation(client, user)
    provider = fake_llm({"answer": None, "cited": []})
    ask(client, user, cid, f"How do I upload my resume? Reply to {user['email']} or +919876543210",
        use_llm=True, llm_consent=True)
    sent = str(provider.calls[0]["payload"]) if provider.calls else ""
    assert user["email"] not in sent and "9876543210" not in sent


def test_no_ai_call_for_fallbacks_and_declined_questions(client, user, topics, fake_llm):
    provider = fake_llm({"answer": "x", "cited": []})
    cid = new_conversation(client, user)
    for question in ("Does the platform support dark mode?", "What is the capital of France?"):
        answer = ask(client, user, cid, question, use_llm=True, llm_consent=True)
        assert answer["generation_method"] == "deterministic"
    assert provider.calls == []


def test_grounding_check():
    chunk = product_kb.Chunk("x#1", "Resume upload", "Supported files",
                             "You can upload a PDF or DOCX resume of up to 5 MB.")
    assert product_help.grounded("You can upload PDF or DOCX files up to 5 MB.", [chunk])
    assert not product_help.grounded("Premium accounts can sync with LinkedIn automatically.", [chunk])


def test_capabilities_disclose_what_product_questions_send(client, user, fake_llm):
    fake_llm({})
    llm = client.get("/assistant/capabilities", headers=user["headers"]).json()["llm"]
    assert "For questions about how CareerNova AI works" in llm["assistant_disclosure"]
    assert "Never sent: the text of your question" in llm["assistant_disclosure"]


@pytest.mark.parametrize("text,expected", [
    ("What is this application?", True),
    ("What is the price of this product?", True),
    ("How do I use this app?", True),
    ("What is the status of this application?", False),                 # a job application
    ("what happened with my application", False),
    ("Is my application submitted?", False),
])
def test_questions_about_the_product_itself_are_told_apart_from_job_applications(text, expected):
    assert product_help.is_self_reference(text) is expected


def test_guide_vocabulary_has_no_pricing_but_has_features():
    vocabulary = product_help.guide_vocabulary()
    assert product_help._content_words("features") <= vocabulary
    assert not product_help._content_words("price pricing subscription") & vocabulary


def test_product_index_uses_numpy_cosine_ranking_with_safe_edge_cases(topics):
    import numpy as np

    index = product_kb.get_index()
    assert np.allclose(np.linalg.norm(index.vectors[np.linalg.norm(index.vectors, axis=1) > 0], axis=1), 1.0)
    assert index.search("   ") == [] and index.search("resume", k=0) == []
    hits = index.search("resume upload file", k=len(index.chunks) + 5)
    assert len(hits) == len(index.chunks)                                   # k is capped, no padding
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    zero = index.search("What is the capital of France?", k=3)              # zero vector: all scores 0
    assert [h.score for h in zero] == [0.0, 0.0, 0.0]
    assert [h.chunk.id for h in zero] == [c.id for c in index.chunks[:3]]   # ties keep guide order
    assert product_kb.normalize_rows(np.zeros((1, 3))).tolist() == [[0.0, 0.0, 0.0]]
