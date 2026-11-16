"""Phase 8: account/resume deletion cascades and what conversation history keeps."""

import json

from sqlalchemy import func, select

from assistant_support import ask, new_conversation, result_ids, seeded, student, upload  # noqa: F401
from backend.models import Conversation, Message, User


def messages(seeded, cid):
    seeded.expire_all()
    return seeded.scalars(select(Message).where(Message.conversation_id == cid).order_by(Message.message_id)).all()


def test_context_stores_pointers_only(client, student, seeded):
    cid = new_conversation(client, student)
    ask(client, student, cid, "Find internships about data")
    ask(client, student, cid, "tell me more about the first one")
    ask(client, student, cid, "What skills are on my resume?")
    seeded.expire_all()
    context = seeded.get(Conversation, cid).context
    assert set(context) <= {"last_result_message_id", "focus"}
    assert context["focus"] is None or set(context["focus"]) == {"type", "id", "message_id"}
    text = json.dumps(context).lower()
    for leaked in ("python", "asha", "resume", "example.com"):
        assert leaked not in text


def test_resume_deletion_removes_turns_that_used_it(client, student, seeded):
    h, rid = student["headers"], student["resume_id"]
    cid = new_conversation(client, student, resume_id=rid)
    ask(client, student, cid, "show my applications")                     # does not use the resume
    profile = ask(client, student, cid, "What skills are on my resume?")  # uses the resume
    assert "Python" in profile["content"]
    assert client.delete(f"/resumes/{rid}", headers=h).status_code == 204

    remaining = messages(seeded, cid)
    assert [m.content for m in remaining if m.sender == "user"] == ["show my applications"]
    assert all("Python" not in m.content for m in remaining)
    seeded.expire_all()
    conversation = seeded.get(Conversation, cid)
    assert conversation.resume_id is None
    detail = client.get(f"/assistant/conversations/{cid}", headers=h).json()
    assert len(detail["messages"]) == 2


def test_followups_after_the_listed_turn_was_deleted(client, student, seeded):
    h, rid = student["headers"], student["resume_id"]
    client.post(f"/matches/resumes/{rid}?k=5", headers=h)
    cid = new_conversation(client, student)
    top = ask(client, student, cid, "show my top matches")               # a resume-derived list
    assert result_ids(top)
    client.delete(f"/resumes/{rid}", headers=h)
    stale = ask(client, student, cid, "why is the second one a good match?")
    assert "no longer available" in stale["content"] and stale["sources"] == []


def test_account_deletion_removes_conversations_and_messages(client, student, seeded):
    cid = new_conversation(client, student)
    ask(client, student, cid, "What skills are on my resume?")
    seeded.delete(seeded.get(User, student["user_id"]))
    seeded.commit()
    assert seeded.scalar(select(func.count()).select_from(Conversation)) == 0
    assert seeded.scalar(select(func.count()).select_from(Message)) == 0


def test_switching_resume_keeps_answers_scoped(client, student, seeded):
    second = upload(client, student, name="Asha Rao")
    cid = new_conversation(client, student, resume_id=student["resume_id"])
    first_answer = ask(client, student, cid, "What skills are on my resume?")
    assert [s["id"] for s in first_answer["sources"] if s["type"] == "resume"] == [str(student["resume_id"])]
    client.patch(f"/assistant/conversations/{cid}", headers=student["headers"], json={"resume_id": second})
    second_answer = ask(client, student, cid, "What skills are on my resume?")
    assert [s["id"] for s in second_answer["sources"] if s["type"] == "resume"] == [str(second)]


def test_trashed_application_is_marked_unavailable_and_not_resolved(client, student):
    h = student["headers"]
    app = client.post("/applications", headers=h, json={"company_name": "Acme Robotics",
                                                        "title": "Software Intern"}).json()
    cid = new_conversation(client, student)
    listing = ask(client, student, cid, "show my applications")
    client.delete(f"/applications/{app['application_id']}?confirm=true", headers=h)
    follow = ask(client, student, cid, "tell me more about the first one")
    assert "couldn't find that application" in follow["content"]
    history = client.get(f"/assistant/conversations/{cid}/messages", headers=h).json()
    shown = next(m for m in history if m["message_id"] == listing["message_id"])
    assert shown["sources"][0]["available"] is False
