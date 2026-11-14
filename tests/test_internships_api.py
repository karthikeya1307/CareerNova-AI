"""Phase 2: internship catalog, search and admin APIs."""

import pytest
from sqlalchemy import select

from backend.models import Internship, KnowledgeDocument
from backend.services import vector_index
from backend.services.internship_seed import load_dataset, seed_internships, validate_records

SUBSET = load_dataset()[:25]


@pytest.fixture
def seeded(db_session):
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    return db_session


@pytest.fixture
def student(create_user):
    return create_user()


@pytest.fixture
def admin(create_user):
    return create_user(role="admin")


NEW_INTERNSHIP = {
    "title": "Backend Engineering Intern",
    "company": "Example Labs",
    "description": "Build REST APIs with FastAPI and PostgreSQL.",
    "location": "Bengaluru, India",
    "application_url": "https://example.com/apply",
    "domain": "Software Development",
    "work_mode": "Hybrid",
    "duration_weeks": 12,
    "stipend_per_month": 15000,
    "min_education": "Pursuing B.Tech/B.E.",
    "required_skills": ["Python", "FastAPI", "postgres"],
    "preferred_skills": ["Docker", "Antigravity"],
}


# ------------------------------------------------------------------
# Authentication and authorization
# ------------------------------------------------------------------

@pytest.mark.parametrize("method, path", [
    ("GET", "/internships/"), ("GET", "/internships/filters"),
    ("GET", "/internships/search?q=python"), ("GET", "/internships/1"),
    ("POST", "/internships/"), ("PATCH", "/internships/1"),
    ("DELETE", "/internships/1"),
    ("GET", "/admin/index/status"), ("POST", "/admin/index/rebuild"),
])
def test_login_required(client, method, path):
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize("method, path, body", [
    ("POST", "/internships/", NEW_INTERNSHIP),
    ("PATCH", "/internships/1", {"title": "x"}),
    ("DELETE", "/internships/1", None),
    ("GET", "/admin/index/status", None),
    ("POST", "/admin/index/rebuild", None),
])
def test_students_cannot_use_admin_operations(client, student, seeded, method, path, body):
    response = client.request(method, path, headers=student["headers"], json=body)
    assert response.status_code == 403


# ------------------------------------------------------------------
# Catalog
# ------------------------------------------------------------------

def test_list_and_pagination(client, student, seeded):
    first = client.get("/internships/?limit=10", headers=student["headers"]).json()
    second = client.get("/internships/?limit=10&skip=10", headers=student["headers"]).json()

    assert first["total"] == 25
    assert len(first["items"]) == 10 and len(second["items"]) == 10
    assert {i["internship_id"] for i in first["items"]}.isdisjoint(
        {i["internship_id"] for i in second["items"]}
    )
    item = first["items"][0]
    assert item["required_skills"] and item["skills"]
    assert item["stipend_currency"] == "INR"


def test_filters(client, student, seeded):
    headers = student["headers"]
    sample = SUBSET[0]

    by_domain = client.get(
        "/internships/", params={"domain": sample["domain"], "limit": 100}, headers=headers
    ).json()
    assert by_domain["total"] == sum(1 for r in SUBSET if r["domain"] == sample["domain"])
    assert all(i["domain"] == sample["domain"] for i in by_domain["items"])

    by_mode = client.get(
        "/internships/", params={"work_mode": "remote", "limit": 100}, headers=headers
    ).json()
    assert by_mode["total"] == sum(1 for r in SUBSET if r["mode"] == "Remote")

    skill = sample["required_skills"][0]
    by_skill = client.get(
        "/internships/", params={"skill": skill.lower(), "limit": 100}, headers=headers
    ).json()
    assert by_skill["total"] == sum(
        1 for r in SUBSET if skill in r["required_skills"] + r["preferred_skills"]
    )

    by_text = client.get(
        "/internships/", params={"q": sample["company"]}, headers=headers
    ).json()
    assert any(i["company"] == sample["company"] for i in by_text["items"])

    options = client.get("/internships/filters", headers=headers).json()
    assert sorted(options["domains"]) == sorted({r["domain"] for r in SUBSET})
    assert set(options["work_modes"]) <= {"Onsite", "Hybrid", "Remote"}


def test_detail_and_404(client, student, seeded):
    internship = seeded.scalar(select(Internship).limit(1))
    response = client.get(f"/internships/{internship.internship_id}", headers=student["headers"])
    assert response.status_code == 200
    assert response.json()["title"] == internship.title

    assert client.get("/internships/999999", headers=student["headers"]).status_code == 404


# ------------------------------------------------------------------
# Admin management
# ------------------------------------------------------------------

def test_admin_create_normalizes_skills(client, admin):
    response = client.post("/internships/", headers=admin["headers"], json=NEW_INTERNSHIP)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["source"] == "admin"
    assert data["required_skills"] == ["FastAPI", "PostgreSQL", "Python"]
    assert set(data["preferred_skills"]) == {"Docker", "Antigravity"}
    categories = {s["name"]: s["category"] for s in data["skills"]}
    assert categories["Antigravity"] == "other"


@pytest.mark.parametrize("change", [
    {"work_mode": "Moon"},
    {"stipend_per_month": -5},
    {"duration_weeks": 0},
    {"application_url": "javascript:alert(1)"},
    {"stipend_currency": "rupees"},
    {"title": "   "},
])
def test_admin_create_validation(client, admin, change):
    response = client.post(
        "/internships/", headers=admin["headers"], json={**NEW_INTERNSHIP, **change}
    )
    assert response.status_code == 422


def test_admin_update_marks_index_pending(client, admin, seeded, test_embedder):
    vector_index.rebuild_index(test_embedder)
    internship = seeded.scalar(select(Internship).limit(1))

    response = client.patch(
        f"/internships/{internship.internship_id}",
        headers=admin["headers"],
        json={"stipend_per_month": 22222, "preferred_skills": ["Kubernetes"]},
    )
    assert response.status_code == 200
    assert response.json()["stipend_per_month"] == 22222
    assert response.json()["preferred_skills"] == ["Kubernetes"]

    seeded.expire_all()
    status = seeded.scalar(
        select(KnowledgeDocument.indexing_status).where(
            KnowledgeDocument.internship_id == internship.internship_id
        )
    )
    assert status == "pending"

    assert client.patch(
        f"/internships/{internship.internship_id}", headers=admin["headers"], json={}
    ).status_code == 400


def test_soft_delete_hides_from_students_but_not_admins(client, admin, student, seeded):
    internship = seeded.scalar(select(Internship).limit(1))
    path = f"/internships/{internship.internship_id}"

    assert client.delete(path, headers=admin["headers"]).status_code == 204

    seeded.expire_all()
    assert seeded.get(Internship, internship.internship_id).is_active is False

    assert client.get(path, headers=student["headers"]).status_code == 404
    assert client.get(path, headers=admin["headers"]).status_code == 200

    student_list = client.get(
        "/internships/?include_inactive=true&limit=100", headers=student["headers"]
    ).json()
    assert student_list["total"] == 24

    admin_list = client.get(
        "/internships/?include_inactive=true&limit=100", headers=admin["headers"]
    ).json()
    assert admin_list["total"] == 25


# ------------------------------------------------------------------
# Search and index endpoints
# ------------------------------------------------------------------

def test_search_without_index_returns_503(client, student, seeded):
    response = client.get("/internships/search?q=python", headers=student["headers"])
    assert response.status_code == 503


def test_admin_rebuild_status_and_search(client, admin, student, seeded, monkeypatch, test_embedder):
    monkeypatch.setenv("EMBEDDING_MODEL", test_embedder.model_name)
    monkeypatch.setenv("EMBEDDING_MODEL_REVISION", test_embedder.revision)

    rebuild = client.post("/admin/index/rebuild", headers=admin["headers"])
    assert rebuild.status_code == 200
    assert rebuild.json()["indexed"] == 25

    status = client.get("/admin/index/status", headers=admin["headers"]).json()
    assert status["built"] is True and status["stale"] is False

    target = seeded.scalar(select(Internship).limit(1))
    query = f"{target.title} {target.company}"
    response = client.get(
        "/internships/search", params={"q": query, "k": 5}, headers=student["headers"]
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["internship"]["internship_id"] == target.internship_id
    assert 0 < results[0]["similarity"] <= 1.0

    # Deactivated internships disappear from search immediately.
    client.delete(f"/internships/{target.internship_id}", headers=admin["headers"])
    response = client.get(
        "/internships/search", params={"q": query, "k": 25}, headers=student["headers"]
    )
    assert target.internship_id not in {
        r["internship"]["internship_id"] for r in response.json()["results"]
    }

    status = client.get("/admin/index/status", headers=admin["headers"]).json()
    assert status["stale"] is True


def test_rebuild_busy_returns_409(client, admin, monkeypatch):
    def busy(_embedder):
        raise vector_index.IndexBusyError("An index rebuild is already running")

    monkeypatch.setattr(vector_index, "rebuild_index", busy)
    response = client.post("/admin/index/rebuild", headers=admin["headers"])
    assert response.status_code == 409


def test_search_query_validation(client, student):
    assert client.get("/internships/search?q=a", headers=student["headers"]).status_code == 422
    assert client.get(
        "/internships/search?q=python&k=500", headers=student["headers"]
    ).status_code == 422
