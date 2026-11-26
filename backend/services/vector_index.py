"""Vector index for internships (NumPy), rebuilt from PostgreSQL.

PostgreSQL is the single source of truth. The index only maps
``knowledge_documents.document_id`` -> vector. Every search result is
re-checked against PostgreSQL, so inactive or deleted internships never
appear, even when the index on disk is old.

Files (in FAISS_INDEX_DIR, gitignored):
    manifest.json                 commit point: describes the live index
    internships-<build id>.npz    NumPy arrays ``ids`` (int64) and ``vectors``
                                  (float32); loaded with allow_pickle=False

Search is exact inner product on L2-normalised vectors (cosine similarity),
the same ranking as the FAISS ``IndexFlatIP`` used before. Indexes written by
FAISS (manifest format 1, ``*.faiss``) are rejected: rebuild required.

Rebuild safety:
* A PostgreSQL advisory lock allows only one rebuild at a time across
  all processes; a concurrent request fails fast with IndexBusyError.
* The new index is written to a new file, fsynced, then the manifest is
  replaced with ``os.replace`` (atomic). Readers see either the old or
  the new index, never a partial one. Old index files are removed after.
* The loader verifies the file's SHA-256, vector count and dimension
  from the manifest, and ignores every other file in the folder
  (including any ``*.pkl``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import io
import zipfile

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from backend import database
from backend.models import Internship, InternshipSkill, KnowledgeDocument
from backend.services.embeddings import Embedder, embedding_settings
from backend.services.internship_text import build_internship_text, content_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_NAME = "manifest.json"
INDEX_FILE_PATTERN = re.compile(r"^internships-[0-9a-f]{32}\.npz$")
MANIFEST_FORMAT_VERSION = 2          # 1 = FAISS binary (no longer readable)
SOURCE_TYPE = "internship"

# Arbitrary constant key for pg_try_advisory_lock.
REBUILD_LOCK_KEY = 74_251_903

MIN_CANDIDATES = 50
CANDIDATE_MULTIPLIER = 5


class VectorIndexError(RuntimeError):
    """Base class for index problems."""


class IndexNotReadyError(VectorIndexError):
    """No usable index (missing, corrupt or built with another model)."""


class IndexBusyError(VectorIndexError):
    """Another rebuild is already running."""


# ============================================================
# NUMPY INDEX (replaces FAISS IndexIDMap2(IndexFlatIP))
# ============================================================

class NumpyIndex:
    """Exact inner-product index with document ids.

    Same interface as the FAISS index it replaces: ``d``, ``ntotal``,
    ``add_with_ids`` and ``search`` returning ``(scores, ids)`` arrays of
    shape (n_queries, k), padded with score -inf and id -1 when k > ntotal.
    Vectors are expected to be L2-normalised, so scores are cosine similarity.
    """

    def __init__(self, d: int):
        if int(d) <= 0:
            raise ValueError("dimension must be positive")
        self.d = int(d)
        self.vectors = np.zeros((0, self.d), dtype="float32")
        self.ids = np.zeros(0, dtype="int64")

    @property
    def ntotal(self) -> int:
        return int(self.ids.shape[0])

    def add_with_ids(self, vectors: np.ndarray, ids: np.ndarray) -> None:
        vectors = np.ascontiguousarray(vectors, dtype="float32")
        ids = np.ascontiguousarray(ids, dtype="int64")
        if vectors.ndim != 2 or vectors.shape[1] != self.d or ids.shape != (vectors.shape[0],):
            raise ValueError("vectors must be (n, d) and ids (n,)")
        self.vectors = np.concatenate([self.vectors, vectors])
        self.ids = np.concatenate([self.ids, ids])

    def reconstruct(self, document_id: int) -> np.ndarray:
        """The stored vector for a document id (like FAISS ``IndexIDMap2.reconstruct``)."""
        positions = np.flatnonzero(self.ids == int(document_id))
        if positions.size == 0:
            raise KeyError(f"document id {document_id} is not in the index")
        return self.vectors[positions[0]].copy()

    def search(self, queries: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        queries = np.ascontiguousarray(queries, dtype="float32")
        if queries.ndim != 2 or queries.shape[1] != self.d:
            raise ValueError("queries must be (n, d)")
        k = int(k)
        scores = np.full((queries.shape[0], k), -np.inf, dtype="float32")
        ids = np.full((queries.shape[0], k), -1, dtype="int64")
        take = min(k, self.ntotal)
        if take <= 0:
            return scores, ids
        similarity = queries @ self.vectors.T                     # (n_queries, ntotal)
        for row, values in enumerate(similarity):
            # Highest score first; ties keep insertion order (stable sort).
            order = np.argsort(-values, kind="stable")[:take]
            scores[row, :take] = values[order]
            ids[row, :take] = self.ids[order]
        return scores, ids


def serialize_index(index: NumpyIndex) -> bytes:
    buffer = io.BytesIO()
    np.savez(buffer, ids=index.ids, vectors=index.vectors)
    return buffer.getvalue()


def deserialize_index(data: bytes) -> NumpyIndex:
    """Load an index written by ``serialize_index``. Never unpickles anything."""
    try:
        with np.load(io.BytesIO(data), allow_pickle=False) as archive:
            if set(archive.files) != {"ids", "vectors"}:
                raise ValueError("unexpected arrays")
            ids, vectors = archive["ids"], archive["vectors"]
    except (ValueError, OSError, EOFError, KeyError, zipfile.BadZipFile) as exc:
        raise IndexNotReadyError("Index file is unreadable; rebuild required") from exc
    if (ids.dtype != np.int64 or vectors.dtype != np.float32 or ids.ndim != 1 or vectors.ndim != 2
            or vectors.shape[0] != ids.shape[0] or vectors.shape[1] == 0
            or not np.isfinite(vectors).all()):
        raise IndexNotReadyError("Index file is invalid; rebuild required")
    index = NumpyIndex(vectors.shape[1])
    index.vectors, index.ids = np.ascontiguousarray(vectors), np.ascontiguousarray(ids)
    return index


# ============================================================
# PATHS AND MANIFEST
# ============================================================

def index_dir() -> Path:
    configured = Path(os.getenv("FAISS_INDEX_DIR", "backend/data/faiss_index"))
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


def _fsync_write(path: Path, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def read_manifest() -> dict[str, Any] | None:
    path = index_dir() / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = {"format_version", "index_file", "sha256", "model_name",
                "model_revision", "dimension", "count", "built_at"}
    if not isinstance(manifest, dict) or not required <= manifest.keys():
        return None
    return manifest


# ============================================================
# LOADING (cached, verified)
# ============================================================

@dataclass
class LoadedIndex:
    index: Any
    manifest: dict[str, Any]


_cache: LoadedIndex | None = None
_cache_lock = threading.Lock()


def clear_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def load_index() -> LoadedIndex:
    """Return the live index, verifying it against its manifest."""

    global _cache
    manifest = read_manifest()

    if manifest is None:
        raise IndexNotReadyError("Search index has not been built yet")

    with _cache_lock:
        if _cache is not None and _cache.manifest == manifest:
            return _cache

        if manifest["format_version"] != MANIFEST_FORMAT_VERSION:
            # Includes indexes written by FAISS (format 1): they are never read.
            raise IndexNotReadyError("Unsupported index format; rebuild required")

        file_name = str(manifest["index_file"])
        if not INDEX_FILE_PATTERN.fullmatch(file_name):
            raise IndexNotReadyError("Invalid index file name in manifest")

        path = index_dir() / file_name
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise IndexNotReadyError("Index file is missing; rebuild required") from exc

        if hashlib.sha256(data).hexdigest() != manifest["sha256"]:
            raise IndexNotReadyError("Index file checksum mismatch; rebuild required")

        index = deserialize_index(data)

        if index.ntotal != manifest["count"] or index.d != manifest["dimension"]:
            raise IndexNotReadyError("Index does not match its manifest; rebuild required")

        _cache = LoadedIndex(index=index, manifest=manifest)
        return _cache


# ============================================================
# REBUILD
# ============================================================

@dataclass
class RebuildResult:
    indexed: int
    deactivated_documents: int
    built_at: str
    model_name: str
    dimension: int


def _active_internships(db: Session) -> list[Internship]:
    return list(db.scalars(
        select(Internship)
        .where(Internship.is_active.is_(True))
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
        .order_by(Internship.internship_id)
    ))


def plan_rebuild(db: Session) -> dict[str, int]:
    """Dry-run summary (no embedding, no writes)."""
    active = _active_internships(db)
    documents = {
        d.internship_id: d for d in db.scalars(
            select(KnowledgeDocument).where(KnowledgeDocument.source_type == SOURCE_TYPE)
        )
    }
    changed = sum(
        1 for i in active
        if i.internship_id not in documents
        or documents[i.internship_id].content_hash != content_hash(build_internship_text(i))
        or documents[i.internship_id].indexing_status != "indexed"
    )
    return {"active_internships": len(active), "new_or_changed": changed}


def rebuild_index(embedder: Embedder) -> RebuildResult:
    """Rebuild the index from PostgreSQL. One rebuild at a time."""

    with database.engine.connect() as lock_conn:
        acquired = lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": REBUILD_LOCK_KEY}
        ).scalar()
        if not acquired:
            raise IndexBusyError("An index rebuild is already running")
        try:
            return _rebuild_locked(embedder)
        finally:
            lock_conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": REBUILD_LOCK_KEY}
            )
            lock_conn.commit()


def _rebuild_locked(embedder: Embedder) -> RebuildResult:
    directory = index_dir()
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    with database.SessionLocal() as db:
        internships = _active_internships(db)
        active_ids = {i.internship_id for i in internships}

        documents = {
            d.internship_id: d for d in db.scalars(
                select(KnowledgeDocument).where(KnowledgeDocument.source_type == SOURCE_TYPE)
            )
        }

        # 1. Upsert one knowledge document per active internship.
        ordered_docs: list[KnowledgeDocument] = []
        for internship in internships:
            content = build_internship_text(internship)
            document = documents.get(internship.internship_id)
            if document is None:
                document = KnowledgeDocument(
                    internship_id=internship.internship_id,
                    source_type=SOURCE_TYPE,
                    title=f"{internship.title} at {internship.company}"[:300],
                )
                db.add(document)
            document.content = content
            document.content_hash = content_hash(content)
            document.embedding_model = embedder.model_name
            document.indexing_status = "pending"
            document.error_message = None
            ordered_docs.append(document)

        # Documents of inactive or deleted internships leave the index.
        deactivated = 0
        for internship_id, document in documents.items():
            if internship_id not in active_ids and document.indexing_status != "inactive":
                document.indexing_status = "inactive"
                document.indexed_at = None
                deactivated += 1

        db.flush()  # assigns document_id values

        # 2. Embed.
        try:
            vectors = embedder.embed([d.content for d in ordered_docs])
        except Exception as exc:
            for document in ordered_docs:
                document.indexing_status = "failed"
                document.error_message = f"Embedding failed: {type(exc).__name__}"[:1000]
            db.commit()
            raise

        if vectors.shape != (len(ordered_docs), embedder.dimension):
            db.rollback()
            raise VectorIndexError("Embedder returned vectors of unexpected shape")

        # 3. Build the index (cosine similarity on unit vectors).
        index = NumpyIndex(embedder.dimension)
        if ordered_docs:
            ids = np.array([d.document_id for d in ordered_docs], dtype="int64")
            index.add_with_ids(np.ascontiguousarray(vectors, dtype="float32"), ids)

        data = serialize_index(index)
        index_file = f"internships-{uuid.uuid4().hex}.npz"
        manifest = {
            "format_version": MANIFEST_FORMAT_VERSION,
            "index_file": index_file,
            "sha256": hashlib.sha256(data).hexdigest(),
            "model_name": embedder.model_name,
            "model_revision": embedder.revision,
            "dimension": embedder.dimension,
            "count": len(ordered_docs),
            "built_at": now.isoformat(),
        }

        # 4. Write new files, then atomically swap the manifest.
        _fsync_write(directory / index_file, data)
        fd, tmp_name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(json.dumps(manifest, indent=2).encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, directory / MANIFEST_NAME)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            (directory / index_file).unlink(missing_ok=True)
            db.rollback()
            raise

        # 5. Record success in PostgreSQL.
        for document in ordered_docs:
            document.indexing_status = "indexed"
            document.indexed_at = now
        db.commit()

    clear_cache()

    # 6. Remove superseded index files (only our own naming pattern).
    for old in directory.iterdir():
        if INDEX_FILE_PATTERN.fullmatch(old.name) and old.name != index_file:
            try:
                old.unlink()
            except OSError:
                pass

    return RebuildResult(
        indexed=len(ordered_docs),
        deactivated_documents=deactivated,
        built_at=manifest["built_at"],
        model_name=embedder.model_name,
        dimension=embedder.dimension,
    )


# ============================================================
# SEARCH
# ============================================================

@dataclass
class SearchHit:
    internship: Internship
    similarity: float


def ensure_compatible(manifest: dict[str, Any], embedder: Embedder) -> None:
    if (
        manifest["model_name"] != embedder.model_name
        or manifest["model_revision"] != embedder.revision
        or manifest["dimension"] != embedder.dimension
    ):
        raise IndexNotReadyError(
            "Index was built with a different embedding model; rebuild required"
        )


def search(db: Session, query: str, k: int, embedder: Embedder) -> list[SearchHit]:
    """Semantic search. Results are filtered through PostgreSQL."""

    loaded = load_index()
    ensure_compatible(loaded.manifest, embedder)

    if loaded.index.ntotal == 0:
        return []

    vector = embedder.embed([query])
    candidates = min(loaded.index.ntotal, max(k * CANDIDATE_MULTIPLIER, MIN_CANDIDATES))
    scores, ids = loaded.index.search(np.ascontiguousarray(vector, dtype="float32"), candidates)

    ranked = [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]
    if not ranked:
        return []

    rows = db.execute(
        select(KnowledgeDocument.document_id, Internship)
        .join(Internship, Internship.internship_id == KnowledgeDocument.internship_id)
        .where(
            KnowledgeDocument.document_id.in_([doc_id for doc_id, _ in ranked]),
            KnowledgeDocument.source_type == SOURCE_TYPE,
            KnowledgeDocument.indexing_status == "indexed",
            Internship.is_active.is_(True),
        )
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
    ).all()
    allowed = {doc_id: internship for doc_id, internship in rows}

    hits = [
        SearchHit(internship=allowed[doc_id], similarity=round(score, 4))
        for doc_id, score in ranked if doc_id in allowed
    ]
    return hits[:k]


# ============================================================
# STATUS
# ============================================================

def index_status(db: Session) -> dict[str, Any]:
    manifest = read_manifest()
    settings = embedding_settings()

    active = db.scalar(
        select(func.count()).select_from(Internship).where(Internship.is_active.is_(True))
    )
    counts = dict(db.execute(
        select(KnowledgeDocument.indexing_status, func.count())
        .where(KnowledgeDocument.source_type == SOURCE_TYPE)
        .group_by(KnowledgeDocument.indexing_status)
    ).tuples().all())

    indexed_active = db.scalar(
        select(func.count()).select_from(KnowledgeDocument)
        .join(Internship, Internship.internship_id == KnowledgeDocument.internship_id)
        .where(
            KnowledgeDocument.source_type == SOURCE_TYPE,
            KnowledgeDocument.indexing_status == "indexed",
            Internship.is_active.is_(True),
        )
    )

    built = manifest is not None
    model_matches = built and (
        manifest["model_name"] == settings["model_name"]
        and manifest["model_revision"] == settings["revision"]
    )
    stale = (
        not built
        or not model_matches
        or indexed_active != active
        # The index still holds vectors of internships no longer active.
        or manifest["count"] != indexed_active
        or counts.get("pending", 0) > 0
        or counts.get("failed", 0) > 0
    )

    return {
        "built": built,
        "built_at": manifest["built_at"] if built else None,
        "model_name": manifest["model_name"] if built else None,
        "model_revision": manifest["model_revision"] if built else None,
        "dimension": manifest["dimension"] if built else None,
        "indexed_vectors": manifest["count"] if built else 0,
        "configured_model": settings["model_name"],
        "model_matches_configuration": bool(model_matches),
        "active_internships": active,
        "document_status_counts": counts,
        "stale": bool(stale),
    }
