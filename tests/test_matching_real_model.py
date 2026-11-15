"""Phase 3: end-to-end matching with the real local model on all 180 postings.

Also re-checks the semantic calibration on the real data so a future model
or dataset change that inflates scores is caught.
"""

import numpy as np
import pytest
from sqlalchemy import select

from backend.models import Resume, ResumeExtraction, User
from backend.services import embeddings, vector_index
from backend.services.compatibility import calibrate_similarity
from backend.services.internship_seed import load_dataset, seed_internships, validate_records
from backend.services.matching_agent import run_matching
from backend.services.resume_skills import sync_resume_skills

PERSONAS = {
    "data_science": (["Python", "Pandas", "NumPy", "Scikit-learn", "Statistics", "Machine Learning", "SQL"],
                     "Aspiring data scientist building ML models.", "Data Science"),
    "frontend": (["JavaScript", "React", "HTML", "CSS", "TypeScript", "Tailwind CSS", "Git"],
                 "Frontend developer building responsive web apps.", "Web Development"),
    "devops": (["Docker", "Kubernetes", "AWS", "Terraform", "Linux", "CI/CD", "Jenkins"],
               "Cloud and DevOps enthusiast.", "DevOps/Cloud"),
}


@pytest.fixture(scope="module")
def real_embedder():
    return embeddings.SentenceTransformerEmbedder()


@pytest.fixture
def full_index(db_session, real_embedder):
    seed_internships(db_session, validate_records(load_dataset()).valid, apply=True)
    db_session.commit()
    embeddings.set_embedder(real_embedder)
    vector_index.rebuild_index(real_embedder)
    return db_session


def make_resume(db, skills, summary):
    user = User(first_name="T", last_name="U", email=f"{summary[:8].replace(' ', '')}@example.com",
                password_hash="x", is_verified=True)
    db.add(user)
    db.flush()
    resume = Resume(user_id=user.user_id, filename="cv.pdf", file_path="uploads/resumes/x/0.pdf",
                    file_type="pdf", status="completed")
    db.add(resume)
    db.flush()
    data = {"skills": skills, "technical_skills": skills, "professional_summary": summary}
    db.add(ResumeExtraction(resume_id=resume.resume_id, parser_type="pypdf",
                            extracted_data=data, status="completed"))
    sync_resume_skills(db, resume.resume_id, data)
    db.commit()
    return resume


@pytest.mark.parametrize("persona", list(PERSONAS))
def test_personas_match_their_domain(full_index, persona):
    skills, summary, domain = PERSONAS[persona]
    resume = make_resume(full_index, skills, summary)

    run = run_matching(full_index, resume, k=5)

    assert run.semantic_available is True
    domains = [i.domain for _, i in run.results]
    assert sum(d == domain for d in domains) >= 4, domains
    assert run.results[0][1].domain == domain
    for result, _ in run.results:
        assert 0 <= result.score <= 100
        assert result.component("semantic").status == "assessed"


def test_unrelated_resume_gets_low_scores(full_index):
    resume = make_resume(full_index, ["Cooking", "Menu Planning", "Food Safety"],
                         "Professional chef.")
    run = run_matching(full_index, resume, k=5)
    # No skill overlaps; semantic-only candidates must not look like good fits.
    for result, _ in run.results:
        assert result.score <= 50
        assert result.label in {"Weak", "Fair"}


def test_calibration_does_not_inflate_on_real_data(full_index, real_embedder):
    loaded = vector_index.load_index()
    total = loaded.index.ntotal
    doc_vectors = np.vstack([loaded.index.reconstruct(int(i)) for i in
                             full_index.scalars(select(vector_index.KnowledgeDocument.document_id)
                                                .where(vector_index.KnowledgeDocument.indexing_status == "indexed"))])
    assert doc_vectors.shape[0] == total == 180

    queries = real_embedder.embed([
        "Skills: Cooking, Menu Planning, Food Safety\nSummary: Professional chef.",
        "Skills: Communication",
    ])
    sims = queries @ doc_vectors.T
    calibrated = np.vectorize(calibrate_similarity)(sims)
    assert calibrated.max() <= 0.15     # unrelated resumes never look semantically similar
