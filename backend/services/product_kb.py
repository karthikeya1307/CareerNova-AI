"""Product knowledge base for the career assistant.

The product guide lives in ``backend/data/product_docs/*.md``. Each Markdown file is split into
chunks (one per ``##`` section; long sections are split into overlapping windows of sentences),
embedded with the same local sentence-embedding model the rest of the app uses, and searched by
exact cosine similarity in a separate in-memory NumPy matrix. It is independent of the internship
search index: it is never written to disk and never touches the internship catalogue.

The index is rebuilt automatically when the guide files or the embedding model change.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DOCS_DIR = Path(__file__).resolve().parents[1] / "data" / "product_docs"
MAX_CHUNK_CHARS = 700          # longer sections are split into sentence windows of about this size
OVERLAP_SENTENCES = 1          # sentences repeated between neighbouring windows


@dataclass(frozen=True)
class Chunk:
    id: str                    # "<file stem>#<n>", e.g. "03_resume_upload#2"
    document: str              # document title (the "# " heading)
    heading: str               # section title (the "## " heading)
    text: str

    @property
    def label(self) -> str:
        return f"Product guide: {self.document} › {self.heading}"

    @property
    def embed_text(self) -> str:
        # The titles give short sections enough context for retrieval.
        return f"{self.document}. {self.heading}. {self.text}"


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float               # cosine similarity, -1..1


# ------------------------------------------------------------------
# Loading and chunking
# ------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])", text) if s.strip()]


def _windows(sentences: list[str]) -> list[str]:
    windows, current = [], []
    for sentence in sentences:
        if current and len(" ".join([*current, sentence])) > MAX_CHUNK_CHARS:
            windows.append(" ".join(current))
            current = current[-OVERLAP_SENTENCES:] if OVERLAP_SENTENCES else []
        current.append(sentence)
    if current:
        windows.append(" ".join(current))
    return windows


def chunk_markdown(stem: str, markdown: str) -> list[Chunk]:
    """Split one guide into chunks: one per ``##`` section, long sections into sentence windows."""
    title, heading, lines, sections = stem, "Overview", [], []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            if lines:
                sections.append((heading, lines))
            heading, lines = line[3:].strip(), []
        elif line.strip():
            lines.append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip())
    if lines:
        sections.append((heading, lines))

    chunks: list[Chunk] = []
    for heading, body in sections:
        text = " ".join(body)
        parts = [text] if len(text) <= MAX_CHUNK_CHARS else _windows(split_sentences(text))
        for part in parts:
            chunks.append(Chunk(f"{stem}#{len(chunks) + 1}", title, heading, part))
    return chunks


def load_chunks(directory: Path = DOCS_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        chunks += chunk_markdown(path.stem, path.read_text(encoding="utf-8"))
    return chunks


def docs_fingerprint(directory: Path = DOCS_DIR) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.md")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


# ------------------------------------------------------------------
# Vector index (in memory, separate from the internship index)
# ------------------------------------------------------------------

def normalize_rows(vectors) -> np.ndarray:
    """L2-normalise each row; an all-zero row stays zero (it then scores 0 against everything)."""
    vectors = np.ascontiguousarray(vectors, dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class ProductIndex:
    """Exact cosine-similarity search over the guide chunks (NumPy, in memory)."""

    def __init__(self, chunks: list[Chunk], embedder):
        self.chunks = chunks
        self.embedder = embedder
        self.vectors = (normalize_rows(embedder.embed([c.embed_text for c in chunks])) if chunks
                        else np.zeros((0, 1), dtype="float32"))

    def search(self, query: str, k: int = 4) -> list[Hit]:
        if not query.strip() or not self.chunks or k <= 0:
            return []
        question = self.embed([query])[0]
        scores = self.vectors @ question
        order = np.argsort(-scores, kind="stable")[:min(k, len(self.chunks))]   # best first; ties keep guide order
        return [Hit(self.chunks[i], round(float(scores[i]), 4)) for i in order]

    def embed(self, texts: list[str]) -> np.ndarray:
        return normalize_rows(self.embedder.embed(texts))


# ------------------------------------------------------------------
# Keyword fallback (no neural model): TF-IDF over stemmed content words
# ------------------------------------------------------------------

STOPWORDS = frozenset(
    "the a an and or but of to in on for with by from at as is are was were be been being it its this that these "
    "those you your yours i me my we our they them their can could will would should do does did not no yes if "
    "then than so such also only just more most very any each every all some there here when where which who "
    "whom what why how have has had into about after before over under up down out off again once get gets one "
    "two use used using need needs please tell explain show".split())

# Retrieval with the keyword fallback scores lower than with the neural model; its own threshold
# was calibrated on the same covered / uncovered / unrelated question sets (see tests).
KEYWORD_ANSWER_THRESHOLD = 0.25


def keyword_terms(text: str) -> list[str]:
    return [w[:6] for w in re.findall(r"[a-z0-9+#]+", text.lower()) if len(w) > 2 and w not in STOPWORDS]


class KeywordEmbedder:
    """Deterministic TF-IDF vectors over the guide's vocabulary. Used only when the neural embedding
    model cannot be loaded, so product questions are still answered from the guide."""

    model_name = "keyword-tfidf"
    revision = "1"
    answer_threshold = KEYWORD_ANSWER_THRESHOLD

    def __init__(self, chunks: list[Chunk]):
        import math

        docs = [set(keyword_terms(c.embed_text)) for c in chunks]
        vocabulary = sorted(set().union(*docs)) if docs else []
        self.index = {term: i for i, term in enumerate(vocabulary)}
        self.idf = np.array([math.log((1 + len(docs)) / (1 + sum(term in d for d in docs))) + 1 for term in vocabulary],
                            dtype="float32")
        self.dimension = max(1, len(vocabulary))

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype="float32")
        for row, text in enumerate(texts):
            for term in keyword_terms(text):
                col = self.index.get(term)
                if col is not None:
                    vectors[row, col] += self.idf[col]
        return vectors


_cache: dict[str, ProductIndex] = {}
_lock = threading.Lock()
_keyword: dict[str, KeywordEmbedder] = {}


def default_embedder(directory: Path = DOCS_DIR):
    """The neural model when it loads; otherwise the keyword fallback (never an exception)."""
    from backend.services import embeddings

    try:
        return embeddings.get_embedder()
    except embeddings.EmbeddingError:
        fingerprint = docs_fingerprint(directory)
        if fingerprint not in _keyword:
            _keyword.clear()
            _keyword[fingerprint] = KeywordEmbedder(load_chunks(directory))
        return _keyword[fingerprint]


def answer_threshold(embedder, default: float) -> float:
    return getattr(embedder, "answer_threshold", default)


def get_index(embedder=None, directory: Path = DOCS_DIR) -> ProductIndex:
    """The product index for the current guide files and embedding model (built once, then cached)."""
    embedder = embedder or default_embedder(directory)
    key = "|".join([docs_fingerprint(directory), str(directory), getattr(embedder, "model_name", "?"),
                    getattr(embedder, "revision", "?"), str(getattr(embedder, "dimension", "?")), str(id(embedder))])
    with _lock:
        if key not in _cache:
            _cache.clear()
            _cache[key] = ProductIndex(load_chunks(directory), embedder)
        return _cache[key]


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def retrieve(query: str, k: int = 4, embedder=None) -> list[Hit]:
    return get_index(embedder).search(query, k)
