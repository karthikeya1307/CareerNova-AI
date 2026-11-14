"""Regression tests for existing profile and resume endpoints."""

import io

from docx import Document


def make_docx() -> bytes:
    document = Document()
    for line in [
        "Asha Rao",
        "asha@example.com | +91 98765 43210",
        "SKILLS",
        "Python, SQL, FastAPI, Communication",
        "EDUCATION",
        "B.Tech Computer Science, Example Institute of Technology, 2026",
    ]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_profile_create_get_update(client, create_user):
    user = create_user()
    headers = user["headers"]

    assert client.get("/profiles/me", headers=headers).status_code == 404

    created = client.post("/profiles/", headers=headers, json={
        "college": " Example Institute ", "degree": "B.Tech",
        "graduation_year": 2026, "location": "Pune",
    })
    assert created.status_code == 201
    assert created.json()["college"] == "Example Institute"

    assert client.post(
        "/profiles/", headers=headers, json={}
    ).status_code == 409

    updated = client.patch(
        "/profiles/me", headers=headers, json={"location": "Chennai"}
    )
    assert updated.status_code == 200
    assert updated.json()["location"] == "Chennai"
    assert updated.json()["degree"] == "B.Tech"


def test_resume_upload_list_and_detail(client, create_user, isolated_uploads):
    user = create_user()
    headers = user["headers"]

    response = client.post(
        "/resumes/upload",
        headers=headers,
        files={"file": (
            "resume.docx", make_docx(),
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document",
        )},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["file_type"] == "docx"
    assert data["extracted_data"]["email"] == "asha@example.com"

    # File was written to the isolated temp directory only.
    stored = list(isolated_uploads.rglob("*.docx"))
    assert len(stored) == 1

    listing = client.get("/resumes/", headers=headers)
    assert [r["resume_id"] for r in listing.json()] == [data["resume_id"]]

    detail = client.get(f"/resumes/{data['resume_id']}", headers=headers)
    assert detail.status_code == 200


def test_resume_is_private_to_owner(client, create_user):
    owner = create_user()
    other = create_user()

    upload = client.post(
        "/resumes/upload",
        headers=owner["headers"],
        files={"file": ("cv.docx", make_docx(), "application/octet-stream")},
    )
    resume_id = upload.json()["resume_id"]

    assert client.get(
        f"/resumes/{resume_id}", headers=other["headers"]
    ).status_code == 404


def test_resume_rejects_bad_files(client, create_user):
    headers = create_user()["headers"]

    wrong_type = client.post(
        "/resumes/upload", headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert wrong_type.status_code == 415

    fake_pdf = client.post(
        "/resumes/upload", headers=headers,
        files={"file": ("cv.pdf", b"not a pdf", "application/pdf")},
    )
    assert fake_pdf.status_code == 400
