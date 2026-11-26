"""Regression: the app keeps working when the embedding model cannot be loaded.

Reproduces what Windows Application Control did on 2026-11-24 (torch's native DLL blocked): loading
the model raises OSError/ImportError. Before the fix this escaped as a raw exception (500s on product
questions and semantic search) and torch was re-imported on every request.
"""

import pytest

from assistant_support import seeded, student  # noqa: F401
from backend.services import embeddings, product_kb


@pytest.fixture
def blocked_model(monkeypatch):
    attempts = []

    class Blocked:
        def __init__(self):
            attempts.append(1)
            raise OSError("[WinError 4551] An Application Control policy has blocked this file.")

    monkeypatch.setattr(embeddings, "SentenceTransformerEmbedder", Blocked)
    embeddings.set_embedder(None)            # no test embedder: use the (blocked) real model
    product_kb.clear_cache()
    yield attempts
    product_kb.clear_cache()


def test_load_failure_becomes_embedding_error_and_is_not_retried(blocked_model):
    for _ in range(3):
        with pytest.raises(embeddings.EmbeddingError, match="could not be loaded \\(OSError\\)"):
            embeddings.get_embedder()
    assert len(blocked_model) == 1                          # torch is not imported again and again
    embeddings.set_embedder(None)                           # an explicit reset allows one new attempt
    with pytest.raises(embeddings.EmbeddingError):
        embeddings.get_embedder()
    assert len(blocked_model) == 2


def test_product_guide_falls_back_to_keyword_retrieval(blocked_model):
    embedder = product_kb.default_embedder()
    assert isinstance(embedder, product_kb.KeywordEmbedder)
    hit = product_kb.retrieve("Which file types can I upload?", embedder=embedder)[0]
    assert hit.chunk.id.startswith("03_resume_upload") and hit.score >= product_kb.KEYWORD_ANSWER_THRESHOLD
    assert product_kb.retrieve("What is the capital of France?", embedder=embedder)[0].score == 0


def test_assistant_answers_product_questions_without_the_model(client, student, blocked_model):  # noqa: F811
    cid = client.post("/assistant/conversations", headers=student["headers"], json={}).json()["conversation_id"]
    reply = client.post(f"/assistant/conversations/{cid}/messages", headers=student["headers"],
                        json={"message": "Which file types can I upload?"})
    assert reply.status_code == 201
    message = reply.json()["assistant_message"]
    assert message["intent"] == "product_help" and "PDF" in message["content"]
    assert {s["id"].split("#")[0] for s in message["sources"]} == {"03_resume_upload"}
    data = client.post(f"/assistant/conversations/{cid}/messages", headers=student["headers"],
                       json={"message": "What skills are on my resume?"}).json()["assistant_message"]
    assert "Python" in data["content"]
    off = client.post(f"/assistant/conversations/{cid}/messages", headers=student["headers"],
                      json={"message": "What is the capital of France?"}).json()["assistant_message"]
    assert "I can only answer questions about CareerNova AI" in off["content"]


def test_semantic_search_reports_unavailable_and_matching_still_works(client, student, blocked_model):  # noqa: F811
    search = client.get("/internships/search", headers=student["headers"], params={"q": "python backend"})
    assert search.status_code in (200, 503)                 # a clear answer, never a crash
    run = client.post(f"/matches/resumes/{student['resume_id']}?k=3", headers=student["headers"])
    assert run.status_code == 201 and run.json()["semantic_available"] is False


def test_missing_model_is_reported_without_importing_pytorch(tmp_path, monkeypatch):
    """On a small server (Render free: 512 MB) a missing model must not load PyTorch just to fail."""
    import sys

    from backend.services import embeddings

    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "no-model-here"))
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)    # any import attempt would fail loudly
    with pytest.raises(embeddings.EmbeddingError, match="not downloaded"):
        embeddings.SentenceTransformerEmbedder()
