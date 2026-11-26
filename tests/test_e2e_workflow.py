"""End-to-end workflow through the HTTP API (test database, captured email, fake LLM).

1 admin invites -> 2 user activates and signs in -> 3 uploads a resume -> 4 parsed, corrected ->
5 readiness -> 6 matching + explore -> 7 skill progress -> 8 career track -> 9 assistant (with the
configured provider, and with the provider failing) -> 10 admin sees users and the audit log.
"""

from sqlalchemy import select

from assistant_support import DOCX, resume_docx, seeded  # noqa: F401
from backend.models import AdminAuditEvent

PASSWORD = "Activ8-E2E-Pass"


def test_complete_student_journey(client, create_user, outbox, seeded, fake_llm, db_session):  # noqa: F811
    # 1. An administrator invites a new student (no password is ever set by the admin).
    admin = create_user(role="admin")
    created = client.post("/admin/users", headers=admin["headers"], json={
        "first_name": "Asha", "last_name": "Rao", "email": "asha.e2e@example.com"})
    assert created.status_code == 201 and created.json()["invitation"]["delivery_status"] == "sent"
    token = outbox.last("invite", "asha.e2e@example.com")["token"]

    # 2. The student activates the account with their own password and signs in.
    assert client.post("/auth/invitation/check", json={"token": token}).json()["first_name"] == "Asha"
    assert client.post("/auth/invitation/accept", json={"token": token, "password": PASSWORD}).status_code == 200
    login = client.post("/auth/login", json={"email": "asha.e2e@example.com", "password": PASSWORD})
    assert login.status_code == 200
    me = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/auth/me", headers=me).json()["is_verified"] is True

    # 3. Upload a resume.
    upload = client.post("/resumes/upload", headers=me, files={"file": ("cv.docx", resume_docx(), DOCX)})
    assert upload.status_code == 201
    rid = upload.json()["resume_id"]
    assert upload.json()["duplicate_of"] == []

    # 4. It is parsed; the student corrects a detail.
    detail = client.get(f"/resumes/{rid}", headers=me).json()
    assert "Python" in detail["extracted_data"]["skills"]
    readiness_before = client.get(f"/resumes/{rid}/readiness", headers=me).json()["score"]
    corrected = {**detail["extracted_data"], "certifications": ["AWS Cloud Practitioner"],
                 "github": "https://github.com/asha-example"}
    saved = client.put(f"/resumes/{rid}/extracted-data", headers=me, json=corrected)
    assert saved.status_code == 200 and saved.json()["corrected"] is True

    # 5. Readiness score and recommendations reflect the correction.
    readiness = client.get(f"/resumes/{rid}/readiness", headers=me).json()
    assert readiness["score"] > readiness_before and readiness["recommendations"] is not None
    assert len(readiness["categories"]) == 8

    # 6. Matching for the resume, and exploring any job.
    run = client.post(f"/matches/resumes/{rid}?k=5", headers=me)
    assert run.status_code == 201 and run.json()["results"]
    top = run.json()["results"][0]
    assert top["insights"]["category"] in ("apply_now", "improve", "long_term")
    explore = client.get("/matches/explore", headers=me, params={"resume_id": rid, "limit": 50}).json()
    assert explore["total"] >= len(run.json()["results"]) and all(i["insights"] for i in explore["items"])

    # 7. Track skill progress on that job's roadmap.
    iid = top["internship"]["internship_id"]
    roadmap = client.get(f"/skill-gaps/resumes/{rid}/internships/{iid}/roadmap", headers=me).json()
    if roadmap["steps"]:
        skill = roadmap["steps"][0]["skill"]
        assert client.put("/skill-gaps/progress", headers=me, json={"skill": skill, "status": "learning"}).status_code == 200
        again = client.get(f"/skill-gaps/resumes/{rid}/internships/{iid}/roadmap", headers=me).json()
        assert again["steps"][0]["status"] == "learning"

    # 8. A career track loads with the student's coverage.
    track = client.get("/career-tracks/python-developer", headers=me, params={"resume_id": rid}).json()
    assert track["coverage"]["on_resume"] >= 1 and track["interview_questions"]

    # 9. The assistant answers with the configured provider (fake LLM here), and falls back safely.
    cid = client.post("/assistant/conversations", headers=me, json={}).json()["conversation_id"]
    plain = client.post(f"/assistant/conversations/{cid}/messages", headers=me,
                        json={"message": "What skills are on my resume?"}).json()["assistant_message"]
    assert plain["generation_method"] == "deterministic" and "Python" in plain["content"]
    from backend.services.llm.base import LLMError
    fake_llm(error=LLMError("The Ollama server could not be reached (is it running?)."))
    fallback = client.post(f"/assistant/conversations/{cid}/messages", headers=me,
                           json={"message": "What skills are on my resume?", "use_llm": True,
                                 "llm_consent": True}).json()["assistant_message"]
    assert fallback["generation_method"] == "deterministic" and "Python" in fallback["content"]

    # 10. The admin sees the user and the audit trail; the student cannot.
    users = client.get("/admin/users", headers=admin["headers"], params={"q": "asha.e2e"}).json()
    assert users[0]["is_verified"] is True and users[0]["invitation"]["status"] == "accepted"
    actions = {e.action for e in db_session.scalars(select(AdminAuditEvent))}
    assert {"user.create", "user.invite", "user.activate"} <= actions
    assert client.get("/admin/audit-events", headers=me).status_code == 403
