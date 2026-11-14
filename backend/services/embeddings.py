"""Text embeddings behind a small provider-independent interface.

Default provider: a local Sentence Transformers model.

Safety and privacy rules:
* The model is downloaded ONCE, explicitly, with
  ``python -m backend.manage download-embedding-model``. Only safetensors
  weights, configs and tokenizer files are fetched; pickle-based weight
  files (``*.bin``, ``*.pt``, ``*.pkl``) are never downloaded or loaded.
* At runtime the model is loaded from the local folder only
  (``local_files_only=True``), never from the network, and with
  ``trust_remote_code=False``.
* The model is loaded lazily on first use, never during API startup.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Protocol

import numpy as np
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

ALLOWED_MODEL_FILES = [
    "model.safetensors",
    "config.json",
    "config_sentence_transformers.json",
    "sentence_bert_config.json",
    "modules.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "1_Pooling/config.json",
]

FORBIDDEN_SUFFIXES = (".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt", ".h5")


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be produced."""


class Embedder(Protocol):
    model_name: str
    revision: str
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return float32 array (n, dimension), L2-normalized rows."""


def embedding_settings() -> dict[str, str | Path]:
    cache_dir = Path(os.getenv("EMBEDDING_CACHE_DIR", ".models"))
    if not cache_dir.is_absolute():
        cache_dir = PROJECT_ROOT / cache_dir

    return {
        "model_name": os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL),
        "revision": os.getenv("EMBEDDING_MODEL_REVISION", DEFAULT_REVISION),
        "cache_dir": cache_dir,
    }


def _check_no_pickle_files(model_dir: Path) -> None:
    unsafe = [
        p.name for p in model_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in FORBIDDEN_SUFFIXES
    ]
    if unsafe:
        raise EmbeddingError(
            f"Refusing to load model: pickle-based files present {unsafe}"
        )
    if not (model_dir / "model.safetensors").is_file():
        raise EmbeddingError("Refusing to load model: model.safetensors missing")


def download_model() -> Path:
    """One-time download of the pinned model revision (network)."""

    from huggingface_hub import snapshot_download

    settings = embedding_settings()
    path = Path(snapshot_download(
        repo_id=settings["model_name"],
        revision=settings["revision"],
        cache_dir=str(settings["cache_dir"]),
        allow_patterns=ALLOWED_MODEL_FILES,
    ))
    _check_no_pickle_files(path)
    return path


def local_model_path() -> Path:
    """Locate the downloaded model without any network access."""

    from huggingface_hub import snapshot_download

    settings = embedding_settings()
    try:
        path = Path(snapshot_download(
            repo_id=settings["model_name"],
            revision=settings["revision"],
            cache_dir=str(settings["cache_dir"]),
            allow_patterns=ALLOWED_MODEL_FILES,
            local_files_only=True,
        ))
    except Exception as exc:
        raise EmbeddingError(
            "Embedding model is not downloaded. Run "
            "`python -m backend.manage download-embedding-model` once."
        ) from exc

    _check_no_pickle_files(path)
    return path


class SentenceTransformerEmbedder:
    """Local Sentence Transformers model on CPU."""

    def __init__(self) -> None:
        settings = embedding_settings()
        self.model_name = str(settings["model_name"])
        self.revision = str(settings["revision"])

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            str(local_model_path()),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
        )
        get_dimension = getattr(
            self._model, "get_embedding_dimension", None
        ) or self._model.get_sentence_embedding_dimension
        dimension = get_dimension()
        if not dimension:
            raise EmbeddingError("Could not determine embedding dimension")
        self.dimension = int(dimension)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype="float32")

        vectors = self._model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.ascontiguousarray(vectors, dtype="float32")


# ------------------------------------------------------------------
# Process-wide provider (lazy, thread-safe)
# ------------------------------------------------------------------

_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = SentenceTransformerEmbedder()
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Replace the provider (used by tests and future providers)."""
    global _embedder
    with _embedder_lock:
        _embedder = embedder
