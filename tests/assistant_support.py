"""Shared fixtures and helpers for the Phase 8 assistant tests."""

import io

import pytest
from docx import Document
from sqlalchemy import select

from backend.models import Internship
from backend.services.internship_seed import load_dataset, seed_internships, validate_records
from backend.services.matching_agent import is_eligible

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUBSET = load_dataset()[:20]


def resume_docx(name="Asha Rao", email="asha@example.com", phone="+91 90000 00002",
                address="12 MG Road, Indiranagar, Bengaluru 560001"):
    document = Document()
    for line in [
        name, f"{email} | {phone}", address,
        "SUMMARY", "Backend developer who designs REST APIs.",
        "SKILLS", "Python, FastAPI, PostgreSQL, Docker, Git, SQL",
        "EDUCATION", "B.Tech Information Technology, Example Institute of Technology, 2026",
        "EXPERIENCE", "Software Intern, Example Systems, 2025",
        "Built 12 REST endpoints with FastAPI and PostgreSQL.",
        "PROJECTS", "Inventory API", "Deployed a Docker service used by 20 users.",
    ]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def seeded(db_session):
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    return db_session


def upload(client, user, **kwargs):
    response = client.post("/resumes/upload", headers=user["headers"],
                           files={"file": ("cv.docx", resume_docx(**kwargs), DOCX)})
    assert response.status_code == 201, response.text
    return response.json()["resume_id"]


@pytest.fixture
def student(client, create_user, seeded):
    user = create_user()
    user["resume_id"] = upload(client, user)
    user["open"] = [i.internship_id for i in seeded.scalars(
        select(Internship).where(Internship.is_active.is_(True)).order_by(Internship.internship_id)) if is_eligible(i)]
    return user


@pytest.fixture
def other(client, create_user, seeded):
    user = create_user()
    user["resume_id"] = upload(client, user, name="Ravi Kumar", email="ravi@example.com", phone="+91 90000 00009",
                               address="7 Park Street, Kolkata 700016")
    return user


def new_conversation(client, user, **body):
    response = client.post("/assistant/conversations", headers=user["headers"], json=body)
    assert response.status_code == 201, response.text
    return response.json()["conversation_id"]


def ask(client, user, conversation_id, message, expect=201, **extra):
    response = client.post(f"/assistant/conversations/{conversation_id}/messages", headers=user["headers"],
                           json={"message": message, **extra})
    assert response.status_code == expect, response.text
    return response.json()["assistant_message"] if expect == 201 else response.json()


def source_ids(answer, kind):
    return [s["id"] for s in answer["sources"] if s["type"] == kind]


def result_ids(answer):
    return [item["id"] for item in (answer["result_set"] or {}).get("items", [])]
