"""Phase 7: status rules, corrections, history, concurrency and transaction rollback."""

import threading

import pytest
from sqlalchemy import func, select

from applications_support import external, internal, other, seeded, set_status, student  # noqa: F401
from backend import database
from backend.models import Application, ApplicationActivity, ApplicationStatusHistory
from backend.services import application_service as svc

ALL = ["SAVED", "APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"]


def statuses(client, user, aid):
    return [(h["from_status"], h["to_status"], h["change_type"])
            for h in client.get(f"/applications/{aid}/history", headers=user["headers"]).json()["status_history"]]


def force_status(db, aid, status):
    app = db.get(Application, aid)
    app.status = status
    db.commit()


@pytest.mark.parametrize("start", ALL)
def test_transition_table(client, student, seeded, start):
    for target in ALL:
        if target == start:
            continue
        app = external(client, student, title=f"{start}-{target}")
        force_status(seeded, app["application_id"], start)
        response = set_status(client, student, app["application_id"], target)
        allowed = target in svc.TRANSITIONS[start]
        assert response.status_code == (200 if allowed else 409), (start, target, response.text)
        if not allowed:
            assert "Cannot change status" in response.json()["detail"]


def test_full_happy_path_and_history(client, student):
    app = internal(client, student)
    aid = app["application_id"]
    for status in ("APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED"):
        body = set_status(client, student, aid, status).json()
        assert body["changed"] is True and body["to_status"] == status
    assert statuses(client, student, aid) == [
        (None, "SAVED", "created"), ("SAVED", "APPLIED", "manual"), ("APPLIED", "SHORTLISTED", "manual"),
        ("SHORTLISTED", "INTERVIEW_SCHEDULED", "manual"), ("INTERVIEW_SCHEDULED", "SELECTED", "manual")]
    detail = client.get(f"/applications/{aid}", headers=student["headers"]).json()
    assert detail["applied_at"] and detail["status_changed_at"].endswith("Z")


def test_same_status_records_no_history(client, student):
    app = external(client, student, status="APPLIED")
    body = set_status(client, student, app["application_id"], "APPLIED").json()
    assert body["changed"] is False and body["from_status"] == body["to_status"] == "APPLIED"
    assert len(statuses(client, student, app["application_id"])) == 1


def test_invalid_values_are_rejected(client, student):
    app = external(client, student)
    for value in ("applied", "OFFER", "", None):
        assert set_status(client, student, app["application_id"], value).status_code == 422
    assert client.patch(f"/applications/{app['application_id']}/status", headers=student["headers"],
                        json={"status": "APPLIED", "extra": 1}).status_code == 422


def test_correction_undoes_only_the_last_change(client, student):
    app = external(client, student)
    aid = app["application_id"]
    set_status(client, student, aid, "APPLIED")
    set_status(client, student, aid, "REJECTED")
    assert set_status(client, student, aid, "APPLIED").status_code == 409                 # final without correction
    assert set_status(client, student, aid, "SAVED", correction=True).status_code == 409   # not the previous one
    undo = set_status(client, student, aid, "APPLIED", correction=True)
    assert undo.status_code == 200 and undo.json()["to_status"] == "APPLIED"
    assert statuses(client, student, aid)[-1] == ("REJECTED", "APPLIED", "correction")
    # The last change is now the correction itself, so undoing again goes back to REJECTED.
    assert set_status(client, student, aid, "SAVED", correction=True).status_code == 409
    assert set_status(client, student, aid, "REJECTED", correction=True).status_code == 200

    fresh = external(client, student, title="Undo to saved")
    set_status(client, student, fresh["application_id"], "APPLIED")
    back = set_status(client, student, fresh["application_id"], "SAVED", correction=True).json()
    assert back["application"]["status"] == "SAVED" and back["application"]["applied_at"] is None


def test_correction_with_nothing_to_undo(client, student):
    app = external(client, student)
    assert set_status(client, student, app["application_id"], "APPLIED", correction=True).status_code == 409


def test_applied_at_rules(client, student):
    withdrawn_early = external(client, student)
    body = set_status(client, student, withdrawn_early["application_id"], "WITHDRAWN").json()
    assert body["application"]["applied_at"] is None                 # never submitted
    app = external(client, student, title="Other", status="APPLIED", applied_at="2026-10-01T09:00:00+05:30")
    body = set_status(client, student, app["application_id"], "SHORTLISTED").json()
    assert body["application"]["applied_at"] == "2026-10-01T03:30:00Z"   # entered date is kept


def test_stale_expected_status_is_rejected(client, student):
    app = external(client, student)
    set_status(client, student, app["application_id"], "APPLIED")
    stale = set_status(client, student, app["application_id"], "WITHDRAWN", expected_status="SAVED")
    assert stale.status_code == 409 and "now APPLIED" in stale.json()["detail"]
    ok = set_status(client, student, app["application_id"], "SHORTLISTED", expected_status="APPLIED")
    assert ok.status_code == 200


def test_trashed_application_status_cannot_change(client, student):
    app = external(client, student)
    client.delete(f"/applications/{app['application_id']}?confirm=true", headers=student["headers"])
    assert set_status(client, student, app["application_id"], "APPLIED").status_code == 404


def test_failure_while_writing_history_rolls_everything_back(student, seeded, monkeypatch, client):
    app = external(client, student)
    aid = app["application_id"]

    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure while writing activity")

    monkeypatch.setattr(svc, "record_activity", broken)
    db = database.SessionLocal()
    try:
        with pytest.raises(RuntimeError):
            svc.change_status(db, student["user_id"], aid, "APPLIED")
        db.rollback()
    finally:
        db.close()
    seeded.expire_all()
    assert seeded.get(Application, aid).status == "SAVED"
    assert seeded.scalar(select(func.count()).select_from(ApplicationStatusHistory)
                         .where(ApplicationStatusHistory.application_id == aid)) == 1
    assert seeded.scalar(select(func.count()).select_from(ApplicationActivity)
                         .where(ApplicationActivity.application_id == aid)) == 1      # only 'created'


def test_concurrent_status_updates_are_serialised(student, seeded, client):
    """Two sessions race to change the same application; the row lock makes one wait."""
    app = external(client, student)
    aid, uid = app["application_id"], student["user_id"]
    results, start = {}, threading.Barrier(2)

    def worker(name, target):
        db = database.SessionLocal()
        try:
            start.wait()
            try:
                _, changed, previous = svc.change_status(db, uid, aid, target)
                results[name] = ("ok", previous, changed)
            except svc.ApplicationError as exc:
                db.rollback()
                results[name] = ("error", exc.status_code)
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=("a", "APPLIED")),
               threading.Thread(target=worker, args=("b", "WITHDRAWN"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    seeded.expire_all()
    final = seeded.get(Application, aid).status
    history = seeded.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == aid)
                             .order_by(ApplicationStatusHistory.history_id)).all()
    # Every successful change has exactly one history row, chained from the previous status.
    successes = [r for r in results.values() if r[0] == "ok"]
    assert len(history) == 1 + len(successes)
    for before, after in zip(history, history[1:]):
        assert after.from_status == before.to_status
    assert history[-1].to_status == final
    assert final in ("APPLIED", "WITHDRAWN")
