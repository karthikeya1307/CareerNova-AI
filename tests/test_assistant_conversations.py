"""Phase 8: conversation management, validation and ownership."""

import pytest

from assistant_support import ask, new_conversation, other, seeded, student  # noqa: F401 (fixtures)
from backend.services.assistant import service

ENDPOINTS = [
    ("GET", "/assistant/capabilities"), ("POST", "/assistant/conversations"), ("GET", "/assistant/conversations"),
    ("GET", "/assistant/conversations/1"), ("PATCH", "/assistant/conversations/1"),
    ("DELETE", "/assistant/conversations/1"), ("GET", "/assistant/conversations/1/messages"),
    ("POST", "/assistant/conversations/1/messages"),
]


@pytest.mark.parametrize("method, path", ENDPOINTS)
def test_login_required(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_capabilities(client, student):
    body = client.get("/assistant/capabilities", headers=student["headers"]).json()
    assert "internship_search" in body["intents"] and body["llm"]["available"] is False
    assert body["limits"]["message_chars"] == 2000 and body["limits"]["messages_per_minute"] == 10


def test_create_list_get_rename_and_delete(client, student):
    h = student["headers"]
    cid = new_conversation(client, student, resume_id=student["resume_id"])
    ask(client, student, cid, "show my applications")
    listed = client.get("/assistant/conversations", headers=h).json()
    assert listed["total"] == 1 and listed["items"][0]["title"] == "My applications"
    detail = client.get(f"/assistant/conversations/{cid}", headers=h).json()
    assert detail["message_count"] == 2 and [m["sender"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["last_message_at"].endswith("Z")
    renamed = client.patch(f"/assistant/conversations/{cid}", headers=h, json={"title": "Job hunt"}).json()
    assert renamed["title"] == "Job hunt"
    assert client.delete(f"/assistant/conversations/{cid}", headers=h).status_code == 422
    assert client.delete(f"/assistant/conversations/{cid}?confirm=true", headers=h).status_code == 204
    assert client.get(f"/assistant/conversations/{cid}", headers=h).status_code == 404


def test_message_paging(client, student):
    cid = new_conversation(client, student)
    for question in ("hi", "show my applications", "show my reminders"):
        ask(client, student, cid, question)
    page = client.get(f"/assistant/conversations/{cid}/messages?limit=2", headers=student["headers"]).json()
    assert [m["sender"] for m in page] == ["user", "assistant"] and page[0]["content"] == "show my reminders"
    older = client.get(f"/assistant/conversations/{cid}/messages?before_id={page[0]['message_id']}&limit=10",
                       headers=student["headers"]).json()
    assert len(older) == 4 and older[0]["content"] == "hi"


def test_other_students_cannot_see_or_use_a_conversation(client, student, other):
    cid = new_conversation(client, student)
    ask(client, student, cid, "show my applications")
    h = other["headers"]
    for method, path, body in [
        ("GET", f"/assistant/conversations/{cid}", None), ("PATCH", f"/assistant/conversations/{cid}", {"title": "x"}),
        ("DELETE", f"/assistant/conversations/{cid}?confirm=true", None),
        ("GET", f"/assistant/conversations/{cid}/messages", None),
        ("POST", f"/assistant/conversations/{cid}/messages", {"message": "hi"}),
    ]:
        assert client.request(method, path, headers=h, json=body).status_code == 404, (method, path)
    assert client.get("/assistant/conversations", headers=h).json()["total"] == 0
    # Another student's resume cannot be attached.
    assert client.post("/assistant/conversations", headers=h, json={"resume_id": student["resume_id"]}).status_code == 404
    assert client.patch(f"/assistant/conversations/{new_conversation(client, other)}", headers=h,
                        json={"resume_id": student["resume_id"]}).status_code == 404


@pytest.mark.parametrize("body", [
    {"message": ""}, {"message": "   "}, {"message": "x" * 2001}, {"message": "hi", "user_id": 1},
    {"message": "hi", "use_llm": "yes please"}, {},
])
def test_message_validation(client, student, body):
    cid = new_conversation(client, student)
    assert client.post(f"/assistant/conversations/{cid}/messages", headers=student["headers"],
                       json=body).status_code == 422


def test_conversation_and_message_caps(client, student, monkeypatch):
    monkeypatch.setattr(service, "MAX_CONVERSATIONS", 1)
    monkeypatch.setattr(service, "MAX_MESSAGES", 2)
    cid = new_conversation(client, student)
    assert client.post("/assistant/conversations", headers=student["headers"], json={}).status_code == 409
    ask(client, student, cid, "hi")
    assert ask(client, student, cid, "hi again", expect=409)["detail"].startswith("This conversation has reached")
