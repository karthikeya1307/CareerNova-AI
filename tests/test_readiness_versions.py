"""Resume readiness score: calculated per version from real content, recalculated on change, never stale.

Regression for "the score always shows 69": the score must follow the scored version's own content, say
which version it belongs to, flag versions with identical content (identical content = identical score),
and ignore profile details (they are not an input). Test database only.
"""

from sqlalchemy import select

from backend.models import Resume
from test_profile_and_versions import V1, V2, h, upload

SPARSE = ["Ravi Kumar", "ravi@example.com", "SKILLS", "Excel"]


def readiness(client, user, rid):
    response = client.get(f"/resumes/{rid}/readiness", headers=h(user))
    assert response.status_code == 200, response.text
    return response.json()


def test_each_version_is_scored_from_its_own_content(client, create_user):
    user = create_user()
    sparse, basic, rich = (upload(client, user, lines, name) for lines, name in
                           ((SPARSE, "sparse.docx"), (V1, "basic.docx"), (V2, "rich.docx")))
    scores = {rid: readiness(client, user, rid) for rid in (sparse, basic, rich)}
    assert scores[sparse]["score"] < scores[basic]["score"] < scores[rich]["score"]
    for version, rid, name in ((1, sparse, "sparse.docx"), (2, basic, "basic.docx"), (3, rich, "rich.docx")):
        body = scores[rid]
        assert body["resume_id"] == rid and body["version"] == version and body["filename"] == name
        assert body["basis"] == "resume_content" and body["same_content_as"] == []
        assert body["label"] in ("Excellent", "Good", "Fair", "Needs work")         # the score's label
        assert round(sum(c["score"] for c in body["categories"])) == body["score"]  # total = its categories


def test_identical_content_gets_the_same_score_and_is_flagged(client, create_user):
    user = create_user()
    first = upload(client, user, V2, "first.docx")
    other = upload(client, user, V1, "other.docx")
    again = upload(client, user, V2, "again.docx")                         # the same resume uploaded again
    a, b = readiness(client, user, first), readiness(client, user, again)
    assert a["score"] == b["score"]
    assert b["same_content_as"] == [{"resume_id": first, "version": 1}]
    assert a["same_content_as"] == [{"resume_id": again, "version": 3}]
    assert readiness(client, user, other)["same_content_as"] == []


def test_correction_recalculates_and_ends_the_identical_content_link(client, create_user):
    user = create_user()
    first = upload(client, user, V1, "a.docx")
    again = upload(client, user, V1, "b.docx")
    before = readiness(client, user, again)
    assert before["same_content_as"] == [{"resume_id": first, "version": 1}]
    detail = client.get(f"/resumes/{again}", headers=h(user)).json()["extracted_data"]
    corrected = {**detail, "linkedin": "linkedin.com/in/asha-example",
                 "certifications": ["Google Data Analytics Certificate"], "achievements": ["Hackathon finalist 2025"]}
    assert client.put(f"/resumes/{again}/extracted-data", headers=h(user), json=corrected).status_code == 200
    after = readiness(client, user, again)
    assert after["corrected"] is True and after["score"] > before["score"]      # recalculated, not cached
    assert after["same_content_as"] == []
    assert readiness(client, user, first)["score"] == before["score"]        # the other version is unchanged


def test_profile_details_do_not_change_the_resume_score(client, create_user):
    user = create_user()
    rid = upload(client, user, V1)
    before = readiness(client, user, rid)["score"]
    assert client.post("/profiles/", headers=h(user), json={"degree": "B.Tech", "college": "Example Institute",
                                                            "graduation_year": 2026, "location": "Pune",
                                                            "bio": "Aspiring data analyst."}).status_code == 201
    assert readiness(client, user, rid)["score"] == before


def test_unparsed_or_foreign_resume_has_no_score(client, create_user, db_session):
    owner, other = create_user(), create_user()
    rid = upload(client, owner, V1)
    assert client.get(f"/resumes/{rid}/readiness", headers=h(other)).status_code == 404
    assert client.get(f"/resumes/{rid}/readiness").status_code == 401
    pending = Resume(user_id=owner["user_id"], filename="pending.pdf", file_path="x/pending.pdf",
                     file_type="pdf", status="processing")
    db_session.add(pending)
    db_session.commit()
    response = client.get(f"/resumes/{pending.resume_id}/readiness", headers=h(owner))
    assert response.status_code == 409 and "no successful extraction" in response.json()["detail"]
    assert db_session.scalar(select(Resume).where(Resume.resume_id == pending.resume_id)) is not None
