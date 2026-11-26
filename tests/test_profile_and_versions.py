"""HR feedback: profile picture + bio, multiple resume versions, resume comparison (test database only)."""

import io
import struct
import zlib

import pytest
from docx import Document

from backend.services import avatars

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def png(width=64, height=64) -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x40\xc0" * width for _ in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg(width=80, height=60) -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, height, width, 3) + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + sof + b"\xff\xd9"


def resume(lines) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


V1 = ["Asha Rao", "asha@example.com | +91 90000 00002", "SKILLS", "Python, SQL, Excel, Communication",
      "EDUCATION", "B.Tech Information Technology, Example Institute of Technology, 2026",
      "PROJECTS", "Sales Report", "Built an Excel report for 3 stores."]
V2 = ["Asha Rao", "asha@example.com | +91 90000 00002 | linkedin.com/in/asha-example",
      "SUMMARY", "Data analyst intern candidate who builds SQL and Power BI dashboards.",
      "SKILLS", "Python, SQL, Power BI, Pandas, Statistics, Teamwork",
      "EDUCATION", "B.Tech Information Technology, Example Institute of Technology, 2026",
      "EXPERIENCE", "Data Analyst Intern, Example Analytics, 2025",
      "Cleaned survey data with Pandas and SQL for 4 teams.",
      "PROJECTS", "Sales Report", "Built a Power BI report for 3 stores with SQL queries.",
      "Churn Analysis", "Analysed churn with Python and Statistics.",
      "CERTIFICATIONS", "Google Data Analytics Certificate"]


def upload(client, user, lines, name="cv.docx"):
    response = client.post("/resumes/upload", headers=user["headers"], files={"file": (name, resume(lines), DOCX)})
    assert response.status_code == 201, response.text
    return response.json()["resume_id"]


def h(user):
    return user["headers"]


# ------------------------------------------------------------------
# Profile picture and bio
# ------------------------------------------------------------------

def test_avatar_upload_replace_serve_and_remove(client, create_user, tmp_path):
    user = create_user()
    assert client.get("/profiles/me/avatar", headers=h(user)).status_code == 404
    r = client.post("/profiles/me/avatar", headers=h(user), files={"file": ("me.png", png(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["has_avatar"] is True and r.json()["avatar_updated_at"]       # profile created on demand
    got = client.get("/profiles/me/avatar", headers=h(user))
    assert got.status_code == 200 and got.content == png() and got.headers["content-type"] == "image/png"
    assert got.headers["x-content-type-options"] == "nosniff" and "no-store" in got.headers["cache-control"]
    first = list((avatars.AVATAR_DIR / str(user["user_id"])).iterdir())

    r = client.post("/profiles/me/avatar", headers=h(user), files={"file": ("me.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 200
    files = list((avatars.AVATAR_DIR / str(user["user_id"])).iterdir())
    assert len(files) == 1 and files != first                                       # old picture replaced
    assert client.get("/profiles/me/avatar", headers=h(user)).headers["content-type"] == "image/jpeg"

    assert client.delete("/profiles/me/avatar", headers=h(user)).status_code == 204
    assert client.get("/profiles/me/avatar", headers=h(user)).status_code == 404
    assert list((avatars.AVATAR_DIR / str(user["user_id"])).iterdir()) == []
    assert client.get("/profiles/me", headers=h(user)).json()["has_avatar"] is False


@pytest.mark.parametrize("name,data,mime,status", [
    ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml", 415),
    ("x.gif", b"GIF89a" + b"\x00" * 20, "image/gif", 415),
    ("fake.png", b"not an image at all", "image/png", 415),
    ("empty.png", b"", "image/png", 422),
    ("tiny.png", png(8, 8), "image/png", 422),
    ("big.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024 + 10), "image/png", 413),
])
def test_avatar_validation(client, create_user, name, data, mime, status):
    user = create_user()
    r = client.post("/profiles/me/avatar", headers=h(user), files={"file": (name, data, mime)})
    assert r.status_code == status, r.text
    assert client.get("/profiles/me/avatar", headers=h(user)).status_code == 404


def test_avatars_are_private(client, create_user):
    owner, other = create_user(), create_user()
    client.post("/profiles/me/avatar", headers=h(owner), files={"file": ("me.png", png(), "image/png")})
    assert client.get("/profiles/me/avatar").status_code == 401
    assert client.get("/profiles/me/avatar", headers=h(other)).status_code == 404        # only ever your own
    assert client.delete("/profiles/me/avatar", headers=h(other)).status_code == 404
    assert client.get("/profiles/me/avatar", headers=h(owner)).status_code == 200
    assert avatars.resolve(other["user_id"], f"{owner['user_id']}/x.png") is None         # no cross-folder paths
    assert avatars.resolve(owner["user_id"], "../../etc/passwd") is None


def test_bio_create_update_clear_and_validate(client, create_user):
    user = create_user()
    r = client.post("/profiles/", headers=h(user), json={"degree": "B.Tech", "bio": "  Aspiring data analyst.\r\n\n\n\nI like SQL.  "})
    assert r.status_code == 201 and r.json()["bio"] == "Aspiring data analyst.\n\nI like SQL."
    r = client.patch("/profiles/me", headers=h(user), json={"bio": "Backend developer in training."})
    assert r.status_code == 200 and r.json()["bio"] == "Backend developer in training."
    assert client.get("/profiles/me", headers=h(user)).json()["bio"] == "Backend developer in training."
    assert client.patch("/profiles/me", headers=h(user), json={"bio": "x" * 601}).status_code == 422
    assert client.patch("/profiles/me", headers=h(user), json={"bio": "   "}).json()["bio"] is None


# ------------------------------------------------------------------
# Resume versions
# ------------------------------------------------------------------

def test_versions_are_kept_named_and_one_is_preferred(client, create_user):
    user = create_user()
    v1 = upload(client, user, V1, "resume_v1.docx")
    v2 = upload(client, user, V2, "resume_v2.docx")
    listed = {r["resume_id"]: r for r in client.get("/resumes/", headers=h(user)).json()}
    assert listed[v1]["version"] == 1 and listed[v2]["version"] == 2                     # nothing overwritten
    assert not listed[v1]["is_preferred"] and not listed[v2]["is_preferred"]

    r = client.patch(f"/resumes/{v1}", headers=h(user), json={"label": "  Original   resume ", "is_preferred": True})
    assert r.status_code == 200 and r.json()["label"] == "Original resume" and r.json()["is_preferred"]
    r = client.patch(f"/resumes/{v2}", headers=h(user), json={"is_preferred": True})
    listed = {r["resume_id"]: r for r in client.get("/resumes/", headers=h(user)).json()}
    assert listed[v2]["is_preferred"] and not listed[v1]["is_preferred"]                # only one preferred
    assert listed[v1]["label"] == "Original resume"
    assert client.patch(f"/resumes/{v1}", headers=h(user), json={}).status_code == 400
    assert client.patch(f"/resumes/{v1}", headers=h(user), json={"label": "x" * 121}).status_code == 422

    # The preferred version is what the assistants use by default (even though it is not the newest).
    client.patch(f"/resumes/{v1}", headers=h(user), json={"is_preferred": True})
    prep = client.get("/prep/profile", headers=h(user)).json()
    assert prep["resume_id"] == v1


def test_compare_two_versions_with_measured_evidence(client, create_user, db_session):
    user = create_user()
    v1 = upload(client, user, V1, "resume_v1.docx")
    v2 = upload(client, user, V2, "resume_v2.docx")
    r = client.get(f"/resumes/compare?a={v1}&b={v2}&role=data-analyst", headers=h(user))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["a"]["resume_id"] == v1 and c["b"]["resume_id"] == v2
    assert {"Power BI", "Pandas", "Statistics"} <= set(c["skills"]["technical"]["added"])
    assert "Excel" in c["skills"]["technical"]["removed"]
    assert "Teamwork" in c["skills"]["soft"]["added"] and "Communication" in c["skills"]["soft"]["removed"]
    # V2's two plain-paragraph projects are extracted as two projects (they used to be merged into one):
    # "Sales Report" changed its description and "Churn Analysis" is a new project.
    modified = c["sections"]["project"]["modified"]
    assert [m_["title"] for m_ in modified] == ["Sales Report"]
    assert modified[0]["lines_added"] == ["Built a Power BI report for 3 stores with SQL queries."]
    assert modified[0]["lines_removed"] == ["Built an Excel report for 3 stores."]
    assert c["sections"]["project"]["added"] == ["Churn Analysis"]
    assert c["sections"]["certification"]["added"] and c["sections"]["experience"]["added"]
    assert c["sections"]["education"]["unchanged"]
    linkedin = next(x for x in c["contact"] if x["field"] == "linkedin")
    assert linkedin["status"] == "added"
    assert c["summary"] == "added"
    m = c["metrics"]
    assert m["readiness"]["b"] > m["readiness"]["a"] and m["readiness"]["change"] == round(m["readiness"]["b"] - m["readiness"]["a"], 1)
    assert m["role"]["b"] > m["role"]["a"]
    assert c["verdict"]["stronger"] == "b" and c["verdict"]["reasons"]
    assert any("Excel" in w for w in c["weaknesses_introduced_in_b"])
    assert c["improvements_in_b"] and isinstance(c["recommendations_for_weaker"], list)

    # Same engine both ways: swapping the versions mirrors the result.
    swapped = client.get(f"/resumes/compare?a={v2}&b={v1}&role=data-analyst", headers=h(user)).json()
    assert swapped["metrics"]["readiness"]["change"] == -m["readiness"]["change"]
    assert swapped["verdict"]["stronger"] == "a"


def test_compare_with_an_internship_uses_the_ats_report(client, create_user, db_session):
    from assistant_support import SUBSET
    from backend.services.internship_seed import seed_internships, validate_records
    seed_internships(db_session, validate_records(SUBSET).valid, apply=True)
    db_session.commit()
    from sqlalchemy import select
    from backend.models import Internship
    internship = db_session.scalars(select(Internship).where(Internship.is_active.is_(True))).first()
    user = create_user()
    v1, v2 = upload(client, user, V1), upload(client, user, V2)
    c = client.get(f"/resumes/compare?a={v1}&b={v2}&internship_id={internship.internship_id}", headers=h(user)).json()
    ats = c["metrics"]["ats"]
    assert ats["internship_id"] == internship.internship_id
    for side in ("a", "b"):
        assert {"required", "preferred", "checks_passed", "checks_total", "missing_keywords"} <= set(ats[side])
    assert ats["b"]["checks_passed"] >= ats["a"]["checks_passed"]


def test_compare_validation_and_isolation(client, create_user):
    owner, other = create_user(), create_user()
    v1, v2 = upload(client, owner, V1), upload(client, owner, V2)
    theirs = upload(client, other, V1)
    assert client.get(f"/resumes/compare?a={v1}&b={v2}").status_code == 401
    assert client.get(f"/resumes/compare?a={v1}&b={theirs}", headers=h(owner)).status_code == 404
    assert client.get(f"/resumes/compare?a={v1}&b={v2}", headers=h(other)).status_code == 404
    assert client.patch(f"/resumes/{v1}", headers=h(other), json={"label": "mine"}).status_code == 404
    assert client.get(f"/resumes/compare?a={v1}&b={v1}", headers=h(owner)).status_code == 422
    assert client.get(f"/resumes/compare?a={v1}&b={v2}&role=astronaut", headers=h(owner)).status_code == 404
    close = client.get(f"/resumes/compare?a={v1}&b={v2}", headers=h(owner)).json()
    assert close["verdict"]["basis"].startswith("readiness-v1")
