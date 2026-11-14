"""Phase 2: the real local embedding model (offline) and startup behaviour.

These tests load the pinned all-MiniLM-L6-v2 model from the local
.models folder. They never download anything.
"""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from backend.models import Internship
from backend.services import embeddings, vector_index
from backend.services.internship_seed import load_dataset, seed_internships, validate_records

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real_embedder():
    return embeddings.SentenceTransformerEmbedder()


def test_model_files_are_safetensors_only():
    path = embeddings.local_model_path()
    names = {p.name for p in path.rglob("*") if p.is_file()}

    assert "model.safetensors" in names
    assert not [n for n in names if n.endswith(embeddings.FORBIDDEN_SUFFIXES)]


def test_real_model_vectors(real_embedder):
    vectors = real_embedder.embed(["python developer", "graphic designer"])

    assert real_embedder.dimension == 384
    assert vectors.shape == (2, 384)
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4)
    assert real_embedder.revision == embeddings.DEFAULT_REVISION


def test_real_model_semantic_ranking(real_embedder):
    query, backend, design = real_embedder.embed([
        "python backend API developer",
        "Build REST APIs with FastAPI and PostgreSQL",
        "Design mobile app wireframes in Figma",
    ])
    assert float(query @ backend) > float(query @ design) + 0.2


def test_full_dataset_index_with_real_model(db_session, real_embedder):
    seed_internships(db_session, validate_records(load_dataset()).valid, apply=True)
    db_session.commit()

    result = vector_index.rebuild_index(real_embedder)
    assert result.indexed == 180
    assert result.dimension == 384

    hits = vector_index.search(
        db_session, "machine learning with python, pandas and scikit-learn",
        5, real_embedder,
    )
    assert len(hits) == 5
    assert hits[0].similarity > 0.3
    assert sum(1 for h in hits if h.internship.domain == "Data Science") >= 3


def test_api_startup_does_not_load_the_model():
    code = (
        "import sys, backend.main; "
        "loaded = [m for m in ('torch', 'sentence_transformers', 'transformers') "
        "if m in sys.modules]; "
        "print(loaded); sys.exit(1 if loaded else 0)"
    )
    env = {**os.environ, "DB_NAME": "career_companion_test"}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT_ROOT, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
