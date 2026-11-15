"""Phase 3: matching agent (candidate retrieval, filtering, persistence)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from backend.models import (
    Internship, MatchResult, Resume, ResumeExtraction, StudentProfile, User,
)
from backend.services import vector_index
from backend.services.candidate_profile import InsufficientResumeDataError, build_candidate
from backend.services.internship_seed import load_dataset, seed_internships, validate_records
from backend.services.matching_agent import run_matching, score_single
from backend.services.resume_skills import sync_resume_skills

SUBSET = load_dataset()[:40]


@pytest.fixture
def seeded(db_session):
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    return db_session


def make_user(db, email="student@example.com"):
    user = User(first_name="T", last_name="U", email=email,
                password_hash="not-used", is_verified=True)
    db.add(user)
    db.flush()
    return user


def make_resume(db, user, skills, summary="", education=None, address=None):
    resume = Resume(user_id=user.user_id, filename="cv.pdf",
                    file_path="uploads/resumes/x/0.pdf", file_type="pdf", status="completed")
    db.add(resume)
    db.flush()
    data = {"technical_skills": skills, "skills": skills, "professional_summary": summary,
            "education": [{"details": education}] if education else [],
            "address": address}
    db.add(ResumeExtraction(resume_id=resume.resume_id, parser_type="pypdf",
                            extracted_data=data, status="completed"))
    sync_resume_skills(db, resume.resume_id, data)
    db.commit()
    return resume


def count(db, model, *where):
    q = select(func.count()).select_from(model)
    return db.scalar(q.where(*where) if where else q)


# ------------------------------------------------------------------
# Candidate profile sources
# ------------------------------------------------------------------

def test_profile_values_take_priority_over_resume(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python"], education="B.Sc Physics", address="Chennai")
    seeded.add(StudentProfile(user_id=user.user_id, degree="B.Tech CSE", location="Pune"))
    seeded.commit()

    candidate = build_candidate(seeded, resume).candidate
    assert (candidate.degree_text, candidate.degree_source) == ("B.Tech CSE", "profile")
    assert (candidate.location_text, candidate.location_source) == ("Pune", "profile")

    override = build_candidate(seeded, resume, location_override="Delhi").candidate
    assert override.location_source == "request"


def test_resume_values_used_when_profile_missing(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python"], education="BCA, Example College", address="Kochi")
    candidate = build_candidate(seeded, resume).candidate
    assert candidate.degree_source == "resume" and candidate.location_source == "resume"


def test_query_text_contains_no_personal_identifiers(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL"], summary="Analyst.")
    text = build_candidate(seeded, resume).query_text
    first_line = text.splitlines()[0]
    assert first_line.startswith("Skills: ")
    assert set(first_line.removeprefix("Skills: ").split(", ")) == {"Python", "SQL"}
    assert "Summary: Analyst." in text
    assert "@" not in text


def test_resume_without_skills_is_rejected(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, [])
    with pytest.raises(InsufficientResumeDataError):
        run_matching(seeded, resume)


# ------------------------------------------------------------------
# Retrieval, filtering, persistence
# ------------------------------------------------------------------

def test_run_without_index_still_scores_skill_candidates(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL", "Docker"])

    run = run_matching(seeded, resume, k=5)

    assert run.semantic_available is False
    assert 1 <= len(run.results) <= 5
    for result, _ in run.results:
        assert result.component("semantic").status == "unavailable"
        assert 0 <= result.score <= 100


def test_run_with_index_uses_semantic(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL", "Docker"])

    run = run_matching(seeded, resume, k=5)

    assert run.semantic_available is True
    assert all(r.component("semantic").status == "assessed" for r, _ in run.results)


def test_skill_overlap_candidates_get_semantic_score_outside_top_n(seeded, test_embedder, monkeypatch):
    vector_index.rebuild_index(test_embedder)
    monkeypatch.setattr("backend.services.matching_agent.MIN_SEMANTIC_POOL", 1)
    monkeypatch.setattr("backend.services.matching_agent.SEMANTIC_POOL_MULTIPLIER", 1)

    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL", "Linux", "Git"])
    run = run_matching(seeded, resume, k=40)

    assert run.candidates_considered > 1   # more than the FAISS top-1
    assert all(r.component("semantic").status == "assessed" for r, _ in run.results)


def test_inactive_and_expired_internships_are_excluded(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    user = make_user(seeded)
    resume = make_resume(seeded, user, SUBSET[0]["required_skills"])

    first = seeded.scalar(select(Internship).where(Internship.external_id == SUBSET[0]["id"]))
    second = seeded.scalar(select(Internship).where(Internship.external_id == SUBSET[1]["id"]))
    first.is_active = False                                       # after index build
    second.deadline = datetime.now(timezone.utc) - timedelta(days=1)
    seeded.commit()

    run = run_matching(seeded, resume, k=40)
    ids = {r.internship_id for r, _ in run.results}
    assert first.internship_id not in ids
    assert second.internship_id not in ids


def test_work_mode_filter(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL", "Linux", "Git", "Docker"])
    run = run_matching(seeded, resume, k=40, work_mode="Remote")
    assert run.results
    assert all(i.work_mode == "Remote" for _, i in run.results)


def test_run_is_persisted_with_ranks_and_history_kept(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL", "Docker"])

    first = run_matching(seeded, resume, k=5)
    second = run_matching(seeded, resume, k=3)

    rows = seeded.scalars(
        select(MatchResult).where(MatchResult.run_id == first.run_id).order_by(MatchResult.rank)
    ).all()
    assert [r.rank for r in rows] == list(range(1, len(first.results) + 1))
    assert all(0 <= r.score <= 100 and r.label and r.breakdown for r in rows)
    assert rows[0].breakdown["run"]["candidates_considered"] == first.candidates_considered
    assert count(seeded, MatchResult, MatchResult.run_id == second.run_id) == len(second.results)
    assert count(seeded, MatchResult) == len(first.results) + len(second.results)


def test_ranking_is_sorted_and_deterministic(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL", "Linux", "Git"])
    a = run_matching(seeded, resume, k=20)
    b = run_matching(seeded, resume, k=20)

    scores = [r.score for r, _ in a.results]
    assert scores == sorted(scores, reverse=True)
    assert [r.internship_id for r, _ in a.results] == [r.internship_id for r, _ in b.results]


def test_score_single_is_not_persisted(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python"])
    internship = seeded.scalar(select(Internship).limit(1))

    result, available = score_single(seeded, resume, internship)
    assert 0 <= result.score <= 100 and available is False
    assert count(seeded, MatchResult) == 0


def test_candidate_sources_never_produce_duplicates(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    user = make_user(seeded)
    # Skills shared by most postings: FAISS and skill-overlap sources overlap heavily.
    resume = make_resume(seeded, user, ["Python", "SQL", "Linux", "Git", "Docker", "AWS"])

    run = run_matching(seeded, resume, k=50)

    ids = [r.internship_id for r, _ in run.results]
    assert len(ids) == len(set(ids))
    assert run.candidates_considered <= 40
    stored = seeded.scalars(
        select(MatchResult.internship_id).where(MatchResult.run_id == run.run_id)
    ).all()
    assert sorted(stored) == sorted(ids)


def test_internship_added_after_index_build_is_reported_as_not_indexed(seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    newcomer = Internship(title="Python Intern", company="Later Labs", work_mode="Remote",
                          source="admin", is_active=True)
    seeded.add(newcomer)
    seeded.flush()
    from backend.services.internship_seed import set_internship_skills
    set_internship_skills(seeded, newcomer, {"Python": "required"})
    seeded.commit()

    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python"])
    run = run_matching(seeded, resume, k=50)

    assert run.semantic_available is True
    by_id = {r.internship_id: r for r, _ in run.results}
    semantic = by_id[newcomer.internship_id].component("semantic")
    assert semantic.status == "unavailable"
    assert "not been indexed yet" in semantic.detail


def test_unexpected_embedding_failure_degrades_gracefully(seeded, test_embedder, monkeypatch):
    vector_index.rebuild_index(test_embedder)

    def broken(_texts):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(test_embedder, "embed", broken)
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL"])

    run = run_matching(seeded, resume, k=5)
    assert run.semantic_available is False
    assert run.results
    assert all(r.component("semantic").status == "unavailable" for r, _ in run.results)


def test_score_single_rejects_inactive_and_expired(seeded):
    from backend.services.matching_agent import InternshipNotEligibleError

    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python"])
    internship = seeded.scalar(select(Internship).limit(1))

    internship.deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    seeded.commit()
    with pytest.raises(InternshipNotEligibleError):
        score_single(seeded, resume, internship)

    internship.deadline = None
    internship.is_active = False
    seeded.commit()
    with pytest.raises(InternshipNotEligibleError):
        score_single(seeded, resume, internship)


def test_concurrent_runs_are_each_complete_and_consistent(seeded):
    import threading

    from backend import database

    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL", "Linux", "Git"])
    resume_id = resume.resume_id
    outcomes, errors = [], []
    barrier = threading.Barrier(4)

    def worker():
        session = database.SessionLocal()
        try:
            barrier.wait(10)
            own = session.get(Resume, resume_id)
            outcomes.append(run_matching(session, own, k=10))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)

    assert errors == []
    assert len({o.run_id for o in outcomes}) == 4

    seeded.expire_all()
    for outcome in outcomes:
        rows = seeded.scalars(
            select(MatchResult).where(MatchResult.run_id == outcome.run_id)
            .order_by(MatchResult.rank)
        ).all()
        assert [r.rank for r in rows] == list(range(1, len(outcome.results) + 1))
        assert [r.internship_id for r in rows] == [r.internship_id for r, _ in outcome.results]
    # Identical inputs -> identical rankings in every run.
    rankings = {tuple(r.internship_id for r, _ in o.results) for o in outcomes}
    assert len(rankings) == 1


def test_deleting_resume_or_user_removes_match_results(seeded):
    user = make_user(seeded)
    resume = make_resume(seeded, user, ["Python", "SQL"])
    other = make_resume(seeded, user, ["Python", "SQL"])
    run_matching(seeded, resume, k=3)
    run_matching(seeded, other, k=3)
    internships_before = count(seeded, Internship)

    seeded.delete(seeded.get(Resume, resume.resume_id))
    seeded.commit()
    assert count(seeded, MatchResult, MatchResult.resume_id == resume.resume_id) == 0
    assert count(seeded, MatchResult, MatchResult.resume_id == other.resume_id) > 0

    seeded.delete(seeded.get(User, user.user_id))
    seeded.commit()
    assert count(seeded, MatchResult) == 0
    assert count(seeded, Internship) == internships_before
