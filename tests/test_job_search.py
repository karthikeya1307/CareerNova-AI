"""Natural-language internship search (test database, synthetic internships only).

Acceptance: a Java query returns Java internships; React returns React roles; a location is respected; an unrelated
query does not return the dataset; empty results explain why; browsing everything still works; failures don't crash.
"""

import pytest

from backend.models import Internship
from backend.services import job_search, vector_index
from backend.services.internship_seed import set_internship_skills

CATALOGUE = [
    ("Java Developer Intern", "Acme Systems", "Hyderabad, India", "Onsite", "Software Development", {"Java": "required", "Spring Boot": "required", "SQL": "preferred"}),
    ("Backend Developer Intern", "Orbit Labs", "Pune, India", "Remote", "Software Development", {"Java": "required", "REST APIs": "required"}),
    ("React Developer Intern", "Pixel Works", "Bengaluru, India", "Hybrid", "Web Development", {"React": "required", "JavaScript": "required", "CSS": "preferred"}),
    ("Frontend Intern", "Bright Apps", "Remote", "Remote", "Web Development", {"React": "required", "HTML": "required"}),
    ("Machine Learning Intern", "Data Forge", "Hyderabad, India", "Hybrid", "AI/ML", {"Python": "required", "Machine Learning": "required"}),
    ("Data Analyst Intern", "Number Co", "Chennai, India", "Onsite", "Data Analytics", {"SQL": "required", "Excel": "required", "Python": "preferred"}),
    ("Content Marketing Intern", "Story Hub", "Mumbai, India", "Remote", "Marketing", {"Communication": "required"}),
]


@pytest.fixture
def catalogue(db_session):
    db_session.query(Internship).update({Internship.is_active: False})       # only this test's postings are active
    rows = []
    for n, (title, company, location, mode, domain, skills) in enumerate(CATALOGUE, start=1):
        i = Internship(title=title, company=company, location=location, work_mode=mode, domain=domain,
                       description=f"{title} at {company}.", source="manual", is_active=True,
                       external_id=f"search-test-{n}", stipend_currency="INR")
        db_session.add(i)
        db_session.flush()
        set_internship_skills(db_session, i, skills)
        rows.append(i)
    db_session.commit()
    return rows


def titles(results):
    return [r.internship.title for r in results]


def test_java_query_returns_only_java_internships(db_session, catalogue):
    it, results, mode, message = job_search.search(db_session, "Java developer internships for freshers", 10)
    assert it.skills == ["Java"] and it.fresher and mode == "keyword"
    assert set(titles(results)) == {"Java Developer Intern", "Backend Developer Intern"}
    assert all("skills: Java" in r.reasons[0] for r in results)


def test_react_query_returns_react_roles(db_session, catalogue):
    _, results, _, _ = job_search.search(db_session, "React developer internships", 10)
    assert set(titles(results)) == {"React Developer Intern", "Frontend Intern"}


def test_location_and_work_mode_are_respected(db_session, catalogue):
    it, results, _, message = job_search.search(db_session, "Entry-level AI/ML jobs in Hyderabad", 10)
    assert it.location == "Hyderabad" and it.roles == ["ai/ml"] and it.asks_for_jobs
    assert titles(results) == ["Machine Learning Intern"]
    assert "internships only" in message                                   # no invented jobs
    _, remote, _, _ = job_search.search(db_session, "Remote React internships", 10)
    assert titles(remote) == ["Frontend Intern"]
    _, none, _, message = job_search.search(db_session, "Java internships in Chennai", 10)
    assert none == [] and "Chennai" in message and "browse all" in message


def test_remote_search_uses_the_work_mode_not_a_remote_location_text(db_session, catalogue):
    # Some curated postings say location "Remote" but are Onsite; they must not appear for a remote search.
    odd = Internship(title="React UI Intern", company="Mixed Signals", location="Remote", work_mode="Onsite",
                     domain="Web Development", description="React UI Intern.", source="manual", is_active=True,
                     external_id="search-test-odd", stipend_currency="INR")
    db_session.add(odd)
    db_session.flush()
    set_internship_skills(db_session, odd, {"React": "required"})
    db_session.commit()
    _, remote, _, _ = job_search.search(db_session, "remote React internship", 10)
    assert titles(remote) == ["Frontend Intern"]
    assert all(r.internship.work_mode == "Remote" for r in remote)
    _, react, _, _ = job_search.search(db_session, "React internship", 10)
    assert "React UI Intern" in titles(react)                                  # still found without the filter


def test_company_name_does_not_make_a_role_match_and_titles_rank_first(db_session, catalogue):
    # A mobile posting at a company called "... AI Pvt Ltd" is not an AI/ML internship.
    ios = Internship(title="iOS Developer Intern", company="Granite AI Pvt Ltd", location="Pune, India", work_mode="Onsite",
                     domain="Mobile Development", description="iOS Developer Intern.", source="manual", is_active=True,
                     external_id="search-test-ios", stipend_currency="INR")
    db_session.add(ios)
    db_session.flush()
    set_internship_skills(db_session, ios, {"Swift": "required", "Java": "preferred"})
    db_session.commit()
    _, aiml, _, _ = job_search.search(db_session, "AI/ML internship", 10)
    assert titles(aiml) == ["Machine Learning Intern"]
    _, company, _, _ = job_search.search(db_session, "internships at Granite", 10)
    assert titles(company) == ["iOS Developer Intern"]                       # the company still finds its postings
    _, java, _, _ = job_search.search(db_session, "Java internship", 10)
    assert titles(java)[0] == "Java Developer Intern"                         # title names the skill: ranked first
    assert titles(java)[-1] == "iOS Developer Intern"                         # only lists Java: still shown, last


def test_unrelated_query_returns_nothing_with_an_explanation(db_session, catalogue):
    _, results, _, message = job_search.search(db_session, "pizza delivery driver", 10)
    assert results == [] and "No internships in the catalogue match" in message


def test_empty_catalogue_is_explained(db_session):
    db_session.query(Internship).update({Internship.is_active: False})
    db_session.commit()
    _, results, _, message = job_search.search(db_session, "Python internships", 10)
    assert results == [] and "no active internships" in message


def test_semantic_similarity_is_used_when_available(db_session, catalogue, monkeypatch):
    by_title = {i.title: i for i in catalogue}

    def fake_search(db, query, k, embedder):
        sims = {"Machine Learning Intern": 0.71, "Data Analyst Intern": 0.55, "Content Marketing Intern": 0.12}
        return [vector_index.SearchHit(internship=by_title[t], similarity=s) for t, s in sims.items()]

    monkeypatch.setattr(vector_index, "search", fake_search)
    _, results, mode, _ = job_search.search(db_session, "systems that learn from examples", 10, embedder=object())
    assert mode == "hybrid" and titles(results)[0] == "Machine Learning Intern"
    assert "Content Marketing Intern" not in titles(results)               # low similarity, no keyword match


def test_index_or_model_failure_falls_back_to_keywords(db_session, catalogue, monkeypatch):
    def broken(*args, **kwargs):
        raise vector_index.IndexNotReadyError("not built")

    monkeypatch.setattr(vector_index, "search", broken)
    _, results, mode, _ = job_search.search(db_session, "React internships", 10, embedder=object())
    assert mode == "keyword" and set(titles(results)) == {"React Developer Intern", "Frontend Intern"}


def test_api_search_and_browse_still_work(client, create_user, catalogue):
    student = create_user()
    # Browsing lists every active posting; search narrows it.
    browse = client.get("/internships/", headers=student["headers"], params={"limit": 50})
    assert browse.status_code == 200 and browse.json()["total"] == len(CATALOGUE)
    found = client.get("/internships/search", headers=student["headers"], params={"q": "Java developer internships"})
    body = found.json()
    assert found.status_code == 200 and body["interpretation"]["skills"] == ["Java"]
    assert {r["internship"]["title"] for r in body["results"]} == {"Java Developer Intern", "Backend Developer Intern"}
    assert all(r["reasons"] for r in body["results"])
    empty = client.get("/internships/search", headers=student["headers"], params={"q": "pizza delivery driver"}).json()
    assert empty["results"] == [] and empty["message"]
