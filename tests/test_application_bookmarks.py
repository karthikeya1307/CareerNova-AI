"""Phase 7: internship bookmarks."""

from datetime import timedelta

from sqlalchemy import func, select

from applications_support import internal, now_utc, other, seeded, student  # noqa: F401 (fixtures)
from backend.models import Internship, SavedInternship, User


def save(client, user, internship_id):
    return client.post(f"/applications/bookmarks/{internship_id}", headers=user["headers"])


def test_save_list_check_and_remove(client, student):
    h, iid = student["headers"], student["internships"][0]
    created = save(client, student, iid)
    assert created.status_code == 201
    body = created.json()
    assert body["internship_id"] == iid and body["internship"]["is_active"] is True
    assert body["application_id"] is None and body["created_at"].endswith("Z")

    status = client.get(f"/applications/bookmarks/{iid}", headers=h).json()
    assert status["saved"] is True and status["bookmark"]["bookmark_id"] == body["bookmark_id"]
    listing = client.get("/applications/bookmarks", headers=h).json()
    assert listing["total"] == 1 and listing["items"][0]["internship"]["title"]

    assert client.delete(f"/applications/bookmarks/{iid}", headers=h).status_code == 204
    assert client.get(f"/applications/bookmarks/{iid}", headers=h).json() == {"saved": False, "bookmark": None}
    assert client.delete(f"/applications/bookmarks/{iid}", headers=h).status_code == 404


def test_duplicate_bookmark_is_idempotent(client, student, seeded):
    iid = student["internships"][0]
    first = save(client, student, iid)
    second = save(client, student, iid)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["bookmark_id"] == second.json()["bookmark_id"]
    assert seeded.scalar(select(func.count()).select_from(SavedInternship)) == 1


def test_missing_inactive_and_expired_internships_cannot_be_saved(client, student, seeded):
    iid_inactive, iid_expired = student["internships"][1], student["internships"][2]
    seeded.get(Internship, iid_inactive).is_active = False
    seeded.get(Internship, iid_expired).deadline = now_utc() - timedelta(days=1)
    seeded.commit()
    assert save(client, student, 999999).status_code == 404
    assert save(client, student, iid_inactive).status_code == 404
    assert save(client, student, iid_expired).status_code == 404


def test_bookmark_shows_existing_application(client, student):
    iid = student["internships"][0]
    save(client, student, iid)
    application = internal(client, student)
    listing = client.get("/applications/bookmarks", headers=student["headers"]).json()
    assert listing["items"][0]["application_id"] == application["application_id"]


def test_saved_internship_turning_inactive_stays_listed_with_flag(client, student, seeded):
    iid = student["internships"][0]
    save(client, student, iid)
    seeded.get(Internship, iid).is_active = False
    seeded.commit()
    item = client.get("/applications/bookmarks", headers=student["headers"]).json()["items"][0]
    assert item["internship"]["is_active"] is False


def test_bookmarks_are_private(client, student, other):
    iid = student["internships"][0]
    save(client, student, iid)
    assert client.get("/applications/bookmarks", headers=other["headers"]).json()["total"] == 0
    assert client.get(f"/applications/bookmarks/{iid}", headers=other["headers"]).json()["saved"] is False
    assert client.delete(f"/applications/bookmarks/{iid}", headers=other["headers"]).status_code == 404
    assert client.get(f"/applications/bookmarks/{iid}", headers=student["headers"]).json()["saved"] is True


def test_bookmark_pagination(client, student):
    for iid in student["internships"][:3]:
        save(client, student, iid)
    page = client.get("/applications/bookmarks?skip=1&limit=1", headers=student["headers"]).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["skip"] == 1
    assert client.get("/applications/bookmarks?limit=101", headers=student["headers"]).status_code == 422


def test_user_deletion_removes_bookmarks(client, student, seeded):
    save(client, student, student["internships"][0])
    seeded.delete(seeded.get(User, student["user_id"]))
    seeded.commit()
    assert seeded.scalar(select(func.count()).select_from(SavedInternship)) == 0
