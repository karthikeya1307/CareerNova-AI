"""Phase 2: vector index build, safety and search (NumPy index, fast test embedder)."""

import json
import threading
import time

import pytest
from sqlalchemy import select

from backend.models import Internship, KnowledgeDocument
from backend.services import embeddings, vector_index
from backend.services.internship_seed import load_dataset, seed_internships, validate_records

SUBSET = load_dataset()[:30]


@pytest.fixture
def seeded(db_session):
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    return db_session


def internship_by_external(db, index):
    return db.scalar(
        select(Internship).where(Internship.external_id == SUBSET[index]["id"])
    )


def document_text(db, internship):
    return db.scalar(
        select(KnowledgeDocument.content).where(
            KnowledgeDocument.internship_id == internship.internship_id
        )
    )


# ------------------------------------------------------------------
# Build
# ------------------------------------------------------------------

def test_rebuild_writes_native_index_and_manifest(seeded, test_embedder, isolated_index):
    result = vector_index.rebuild_index(test_embedder)

    assert result.indexed == 30
    files = sorted(p.name for p in isolated_index.iterdir())
    assert "manifest.json" in files
    index_files = [f for f in files if f.endswith(".npz")]
    assert len(index_files) == 1
    assert not [f for f in files if f.endswith((".pkl", ".pickle", ".tmp"))]

    manifest = json.loads((isolated_index / "manifest.json").read_text())
    assert manifest["count"] == 30
    assert manifest["dimension"] == test_embedder.dimension
    assert manifest["index_file"] == index_files[0]

    seeded.expire_all()
    statuses = seeded.scalars(select(KnowledgeDocument.indexing_status)).all()
    assert statuses == ["indexed"] * 30


def test_rebuild_replaces_old_index_file(seeded, test_embedder, isolated_index):
    vector_index.rebuild_index(test_embedder)
    first = json.loads((isolated_index / "manifest.json").read_text())["index_file"]

    vector_index.rebuild_index(test_embedder)
    files = [p.name for p in isolated_index.iterdir() if p.suffix == ".npz"]

    assert len(files) == 1 and files[0] != first


def test_rebuild_with_no_internships_creates_empty_index(test_embedder):
    result = vector_index.rebuild_index(test_embedder)
    assert result.indexed == 0
    assert vector_index.load_index().index.ntotal == 0


# ------------------------------------------------------------------
# Search goes through PostgreSQL
# ------------------------------------------------------------------

def test_search_finds_exact_posting_first(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    target = internship_by_external(seeded, 7)
    query = document_text(seeded, target)

    hits = vector_index.search(seeded, query, 5, test_embedder)

    assert hits[0].internship.internship_id == target.internship_id
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-3)
    assert len(hits) == 5


def test_inactive_internship_never_returned_even_with_old_index(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    target = internship_by_external(seeded, 3)
    query = document_text(seeded, target)

    target.is_active = False  # index on disk is now old
    seeded.commit()

    hits = vector_index.search(seeded, query, 30, test_embedder)
    assert target.internship_id not in {h.internship.internship_id for h in hits}


def test_deleted_internship_never_returned(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    target = internship_by_external(seeded, 4)
    query = document_text(seeded, target)
    target_id = target.internship_id

    seeded.delete(target)
    seeded.commit()

    hits = vector_index.search(seeded, query, 30, test_embedder)
    assert target_id not in {h.internship.internship_id for h in hits}


def test_rebuild_removes_inactive_documents(seeded, test_embedder):
    target = internship_by_external(seeded, 5)
    target.is_active = False
    seeded.commit()

    result = vector_index.rebuild_index(test_embedder)
    assert result.indexed == 29
    assert vector_index.load_index().index.ntotal == 29


# ------------------------------------------------------------------
# Loader safety
# ------------------------------------------------------------------

def test_missing_index_is_not_ready(db_session, test_embedder):
    with pytest.raises(vector_index.IndexNotReadyError):
        vector_index.search(db_session, "python", 5, test_embedder)


def test_pickle_files_are_never_loaded(db_session, test_embedder, isolated_index):
    isolated_index.mkdir(parents=True, exist_ok=True)
    (isolated_index / "index.pkl").write_bytes(b"\x80\x04 not a real pickle")
    (isolated_index / "index.faiss").write_bytes(b"supplied index")

    # Supplied files alone do not make an index.
    with pytest.raises(vector_index.IndexNotReadyError):
        vector_index.load_index()

    # A manifest pointing at them is rejected by name.
    for name in ("index.pkl", "index.faiss", "index.npz", "../index.npz"):
        (isolated_index / "manifest.json").write_text(json.dumps({
            "format_version": vector_index.MANIFEST_FORMAT_VERSION, "index_file": name, "sha256": "x",
            "model_name": "m", "model_revision": "r", "dimension": 256,
            "count": 0, "built_at": "now",
        }))
        vector_index.clear_cache()
        with pytest.raises(vector_index.IndexNotReadyError, match="Invalid index file"):
            vector_index.load_index()


def test_tampered_index_file_is_rejected(seeded, test_embedder, isolated_index):
    vector_index.rebuild_index(test_embedder)
    manifest = json.loads((isolated_index / "manifest.json").read_text())
    path = isolated_index / manifest["index_file"]
    path.write_bytes(path.read_bytes()[:-8] + b"tampered")
    vector_index.clear_cache()

    with pytest.raises(vector_index.IndexNotReadyError, match="checksum"):
        vector_index.load_index()


def test_index_from_other_model_is_rejected(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    other = type(test_embedder)(model_name="different-model")
    with pytest.raises(vector_index.IndexNotReadyError, match="different embedding"):
        vector_index.search(seeded, "python", 5, other)


# ------------------------------------------------------------------
# Atomicity and concurrency
# ------------------------------------------------------------------

class SlowEmbedder:
    def __init__(self, inner, delay=2.0):
        self.inner, self.delay = inner, delay
        self.model_name, self.revision = inner.model_name, inner.revision
        self.dimension = inner.dimension
        self.started = threading.Event()

    def embed(self, texts):
        self.started.set()
        time.sleep(self.delay)
        return self.inner.embed(texts)


def test_concurrent_rebuild_is_refused_and_index_stays_valid(
    seeded, test_embedder, isolated_index
):
    vector_index.rebuild_index(test_embedder)
    old_manifest = (isolated_index / "manifest.json").read_text()

    slow = SlowEmbedder(test_embedder)
    outcome = {}

    def run():
        outcome["result"] = vector_index.rebuild_index(slow)

    worker = threading.Thread(target=run)
    worker.start()
    assert slow.started.wait(10)

    # While the first rebuild runs: a second one is refused...
    with pytest.raises(vector_index.IndexBusyError):
        vector_index.rebuild_index(test_embedder)

    # ...and readers still get the complete previous index.
    assert (isolated_index / "manifest.json").read_text() == old_manifest
    assert vector_index.load_index().index.ntotal == 30

    worker.join(30)
    assert outcome["result"].indexed == 30

    files = [p.name for p in isolated_index.iterdir()]
    assert len([f for f in files if f.endswith(".npz")]) == 1
    assert not [f for f in files if f.endswith(".tmp")]
    vector_index.clear_cache()
    assert vector_index.load_index().index.ntotal == 30

    # Lock is released afterwards.
    assert vector_index.rebuild_index(test_embedder).indexed == 30


class FailingEmbedder:
    def __init__(self, inner):
        self.model_name, self.revision = inner.model_name, inner.revision
        self.dimension = inner.dimension

    def embed(self, texts):
        raise RuntimeError("model crashed")


def test_failed_rebuild_keeps_previous_index(seeded, test_embedder, isolated_index):
    vector_index.rebuild_index(test_embedder)
    manifest_before = (isolated_index / "manifest.json").read_text()

    with pytest.raises(RuntimeError):
        vector_index.rebuild_index(FailingEmbedder(test_embedder))

    assert (isolated_index / "manifest.json").read_text() == manifest_before
    vector_index.clear_cache()
    assert vector_index.load_index().index.ntotal == 30

    seeded.expire_all()
    statuses = set(seeded.scalars(select(KnowledgeDocument.indexing_status)))
    assert statuses == {"failed"}
    assert vector_index.index_status(seeded)["stale"] is True


# ------------------------------------------------------------------
# Status
# ------------------------------------------------------------------

def test_status_reports_staleness(seeded, test_embedder, monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", test_embedder.model_name)
    monkeypatch.setenv("EMBEDDING_MODEL_REVISION", test_embedder.revision)

    status = vector_index.index_status(seeded)
    assert status["built"] is False and status["stale"] is True

    vector_index.rebuild_index(test_embedder)
    status = vector_index.index_status(seeded)
    assert status["built"] is True
    assert status["stale"] is False
    assert status["indexed_vectors"] == 30
    assert status["active_internships"] == 30

    internship_by_external(seeded, 0).is_active = False
    seeded.commit()
    assert vector_index.index_status(seeded)["stale"] is True


def test_rebuild_dry_run_plan(seeded):
    plan = vector_index.plan_rebuild(seeded)
    assert plan == {"active_internships": 30, "new_or_changed": 30}


# ------------------------------------------------------------------
# NumPy index (replaces FAISS): ranking, persistence, corrupt and old files
# ------------------------------------------------------------------

def unit(rows):
    import numpy as np

    rows = np.asarray(rows, dtype="float32")
    return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def test_numpy_index_ranks_by_cosine_similarity_with_document_ids():
    import numpy as np

    index = vector_index.NumpyIndex(3)
    index.add_with_ids(unit([[1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 0, 1]]), np.array([10, 20, 30, 40]))
    scores, ids = index.search(unit([[1, 0.2, 0]]), 3)
    assert ids.tolist() == [[10, 30, 20]]
    assert scores[0].tolist() == sorted(scores[0].tolist(), reverse=True)
    assert scores[0][0] == pytest.approx(float(unit([[1, 0.2, 0]])[0] @ unit([[1, 0, 0]])[0]), abs=1e-6)
    assert index.ntotal == 4 and index.d == 3
    assert index.reconstruct(30).tolist() == pytest.approx(unit([[1, 1, 0]])[0].tolist())
    with pytest.raises(KeyError):
        index.reconstruct(99)


def test_numpy_index_pads_like_faiss_and_keeps_ties_in_insertion_order():
    import numpy as np

    index = vector_index.NumpyIndex(2)
    index.add_with_ids(unit([[1, 0], [1, 0], [0, 1]]), np.array([7, 5, 9]))
    scores, ids = index.search(unit([[1, 0]]), 5)
    assert ids.tolist() == [[7, 5, 9, -1, -1]]                           # ties: insertion order
    assert np.isneginf(scores[0][3:]).all()
    empty_scores, empty_ids = vector_index.NumpyIndex(2).search(unit([[1, 0]]), 3)
    assert empty_ids.tolist() == [[-1, -1, -1]]
    with pytest.raises(ValueError):
        index.add_with_ids(np.ones((1, 3), dtype="float32"), np.array([1]))   # wrong dimension


def test_numpy_index_serialization_round_trip_including_empty():
    import numpy as np

    index = vector_index.NumpyIndex(4)
    index.add_with_ids(unit([[1, 2, 3, 4], [4, 3, 2, 1]]), np.array([3, 8]))
    copy = vector_index.deserialize_index(vector_index.serialize_index(index))
    assert copy.d == 4 and copy.ids.tolist() == [3, 8]
    assert np.array_equal(copy.vectors, index.vectors)
    query = unit([[1, 2, 3, 3]])
    assert [a.tolist() for a in copy.search(query, 2)] == [a.tolist() for a in index.search(query, 2)]

    empty = vector_index.deserialize_index(vector_index.serialize_index(vector_index.NumpyIndex(4)))
    assert empty.ntotal == 0 and empty.d == 4


@pytest.mark.parametrize("make", [
    lambda np, io: b"not an index at all",
    lambda np, io: b"PK\x03\x04 truncated zip",
    lambda np, io: _npz(np, io, ids=np.array([1], dtype="int64")),                                   # missing vectors
    lambda np, io: _npz(np, io, ids=np.array([1], dtype="int64"), vectors=np.ones((1, 2), "float32"),
                        extra=np.zeros(1)),                                                          # unexpected array
    lambda np, io: _npz(np, io, ids=np.array([1.5]), vectors=np.ones((1, 2), "float32")),          # float ids
    lambda np, io: _npz(np, io, ids=np.array([1, 2], dtype="int64"), vectors=np.ones((1, 2), "float32")),  # mismatch
    lambda np, io: _npz(np, io, ids=np.array([1], dtype="int64"), vectors=np.array([[np.nan, 1]], "float32")),
    lambda np, io: _npz(np, io, ids=np.array([{"x": 1}], dtype=object), vectors=np.ones((1, 2), "float32")),  # pickle
])
def test_corrupt_or_unsafe_index_data_is_rejected(make):
    import io

    import numpy as np

    with pytest.raises(vector_index.IndexNotReadyError):
        vector_index.deserialize_index(make(np, io))


def _npz(np, io, **arrays):
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    return buffer.getvalue()


def _write_manifest(directory, index_file, data, format_version, count=1, dimension=256):
    import hashlib

    (directory / index_file).write_bytes(data)
    (directory / "manifest.json").write_text(json.dumps({
        "format_version": format_version, "index_file": index_file,
        "sha256": hashlib.sha256(data).hexdigest(), "model_name": "test-hashing", "model_revision": "test",
        "dimension": dimension, "count": count, "built_at": "2026-01-01T00:00:00+00:00",
    }))
    vector_index.clear_cache()


def test_old_faiss_index_is_never_read_and_requires_a_rebuild(seeded, test_embedder, isolated_index):
    isolated_index.mkdir(parents=True, exist_ok=True)
    name = "internships-" + "a" * 32 + ".faiss"
    _write_manifest(isolated_index, name, b"IxMp legacy faiss bytes", format_version=1)
    with pytest.raises(vector_index.IndexNotReadyError, match="Unsupported index format"):
        vector_index.load_index()
    with pytest.raises(vector_index.IndexNotReadyError):
        vector_index.search(seeded, "python", 5, test_embedder)
    assert vector_index.index_status(seeded)["stale"] is True

    # Matching keeps working without semantic scores; a rebuild replaces the old index.
    from backend.services import matching_agent
    assert matching_agent.build_semantic_context(seeded, "python", 10).available is False
    assert vector_index.rebuild_index(test_embedder).indexed == 30
    assert vector_index.load_index().index.ntotal == 30


def test_valid_checksum_but_unreadable_content_is_rejected(isolated_index):
    isolated_index.mkdir(parents=True, exist_ok=True)
    _write_manifest(isolated_index, "internships-" + "b" * 32 + ".npz", b"garbage", vector_index.MANIFEST_FORMAT_VERSION)
    with pytest.raises(vector_index.IndexNotReadyError, match="unreadable"):
        vector_index.load_index()


def test_count_or_dimension_mismatch_is_rejected(isolated_index):
    import numpy as np

    index = vector_index.NumpyIndex(256)
    index.add_with_ids(unit([[1.0] * 256]), np.array([1]))
    isolated_index.mkdir(parents=True, exist_ok=True)
    _write_manifest(isolated_index, "internships-" + "c" * 32 + ".npz", vector_index.serialize_index(index),
                    vector_index.MANIFEST_FORMAT_VERSION, count=2)
    with pytest.raises(vector_index.IndexNotReadyError, match="does not match its manifest"):
        vector_index.load_index()


def test_search_ranking_matches_brute_force_cosine(seeded, test_embedder):
    import numpy as np

    vector_index.rebuild_index(test_embedder)
    documents = seeded.execute(select(KnowledgeDocument.document_id, KnowledgeDocument.content)
                               .order_by(KnowledgeDocument.document_id)).all()
    query = "python machine learning internship with sql"
    expected_scores = test_embedder.embed([c for _, c in documents]) @ test_embedder.embed([query])[0]
    expected = [documents[i][0] for i in np.argsort(-expected_scores, kind="stable")[:5]]
    _, ids = vector_index.load_index().index.search(test_embedder.embed([query]), 5)
    assert ids[0].tolist() == expected
