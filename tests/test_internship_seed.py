"""Phase 2: internship dataset validation and idempotent import."""

import copy
import json

import pytest
from sqlalchemy import func, select

from backend import manage
from backend.models import Internship, InternshipSkill, KnowledgeDocument, Skill
from backend.services.internship_seed import (
    load_dataset,
    seed_internships,
    validate_records,
)

DATASET = load_dataset()


def count(db, model, *where):
    query = select(func.count()).select_from(model)
    if where:
        query = query.where(*where)
    return db.scalar(query)


# ------------------------------------------------------------------
# Validation of the real dataset
# ------------------------------------------------------------------

def test_real_dataset_is_fully_valid():
    report = validate_records(DATASET)

    assert report.total == 180
    assert len(report.valid) == 180
    assert report.errors == []
    assert report.duplicate_ids == []
    assert report.unmapped_skills == {}
    assert report.skill_count == 69
    assert report.stipend_range == (8000, 30000)
    assert report.ok


# ------------------------------------------------------------------
# Validation catches bad records
# ------------------------------------------------------------------

def broken(**changes):
    record = copy.deepcopy(DATASET[0])
    for key, value in changes.items():
        if value is ...:
            record.pop(key)
        else:
            record[key] = value
    return record


@pytest.mark.parametrize("record, expected", [
    (broken(company=...), "company"),
    (broken(role_title=""), "role_title"),
    (broken(stipend_inr_per_month=-1), "stipend_inr_per_month"),
    (broken(stipend_inr_per_month=5_000_000), "stipend_inr_per_month"),
    (broken(stipend_inr_per_month="lots"), "stipend_inr_per_month"),
    (broken(mode="Moon"), "mode"),
    (broken(duration_weeks=0), "duration_weeks"),
    (broken(id="not-a-uuid"), "id"),
    (broken(required_skills=[]), "required_skills"),
    (broken(required_skills=["Python", "python"]), "required_skills"),
    (broken(unexpected_field=1), "unexpected_field"),
])
def test_invalid_records_are_reported(record, expected):
    report = validate_records([record])

    assert not report.ok
    assert len(report.valid) == 0
    assert any(expected in error for error in report.errors)


def test_duplicate_ids_are_reported():
    report = validate_records([DATASET[0], copy.deepcopy(DATASET[0])])
    assert report.duplicate_ids == [DATASET[0]["id"]]
    assert not report.ok


def test_required_and_preferred_overlap_is_reported():
    record = broken(required_skills=["Python"], preferred_skills=["python"])
    report = validate_records([record])
    assert any("both required and preferred" in e for e in report.errors)


def test_unmapped_skills_are_reported():
    record = broken(required_skills=["Quantum Basket Weaving"])
    report = validate_records([record])
    assert report.unmapped_skills == {"Quantum Basket Weaving": 1}
    assert not report.ok


def test_non_object_records_are_reported():
    report = validate_records(["oops", 3])
    assert len(report.errors) == 2


# ------------------------------------------------------------------
# Import
# ------------------------------------------------------------------

def test_dry_run_writes_nothing(db_session):
    records = validate_records(DATASET).valid
    result = seed_internships(db_session, records, apply=False)
    db_session.rollback()

    assert (result.created, result.updated, result.unchanged) == (180, 0, 0)
    assert count(db_session, Internship) == 0
    assert count(db_session, InternshipSkill) == 0


def test_apply_imports_everything_correctly(db_session):
    records = validate_records(DATASET).valid
    seed_internships(db_session, records, apply=True)
    db_session.commit()

    assert count(db_session, Internship) == 180
    assert count(db_session, Internship, Internship.source == "dataset") == 180
    assert count(db_session, Internship, Internship.is_active.is_(True)) == 180

    expected_links = sum(
        len(r["required_skills"]) + len(r["preferred_skills"]) for r in DATASET
    )
    assert count(db_session, InternshipSkill) == expected_links

    # No dataset skill falls back to "other".
    assert count(db_session, Skill, Skill.category == "other") == 0
    assert count(db_session, Skill) == 69

    sample = DATASET[0]
    internship = db_session.scalar(
        select(Internship).where(Internship.external_id == sample["id"])
    )
    assert internship.title == sample["role_title"]
    assert internship.work_mode == sample["mode"]
    assert internship.stipend_per_month == sample["stipend_inr_per_month"]
    assert internship.stipend_currency == "INR"
    importance = {l.skill.name: l.importance for l in internship.skill_links}
    assert {k for k, v in importance.items() if v == "required"} == set(
        sample["required_skills"]
    )
    assert {k for k, v in importance.items() if v == "preferred"} == set(
        sample["preferred_skills"]
    )


def test_reimport_is_idempotent(db_session):
    records = validate_records(DATASET).valid
    seed_internships(db_session, records, apply=True)
    db_session.commit()

    result = seed_internships(db_session, records, apply=True)
    db_session.commit()

    assert (result.created, result.updated, result.unchanged) == (0, 0, 180)
    assert count(db_session, Internship) == 180
    assert count(db_session, Skill) == 69


def test_reimport_updates_changes_and_keeps_admin_deactivation(db_session):
    records = validate_records(DATASET).valid
    seed_internships(db_session, records, apply=True)
    db_session.commit()

    first, second = DATASET[0], DATASET[1]
    target = db_session.scalar(
        select(Internship).where(Internship.external_id == first["id"])
    )
    db_session.add(KnowledgeDocument(
        internship_id=target.internship_id, source_type="internship",
        title="x", indexing_status="indexed",
    ))
    deactivated = db_session.scalar(
        select(Internship).where(Internship.external_id == second["id"])
    )
    deactivated.is_active = False
    db_session.commit()

    changed = copy.deepcopy(DATASET)
    changed[0]["stipend_inr_per_month"] = 12345
    changed[0]["preferred_skills"] = ["Docker"] if "Docker" not in changed[0][
        "required_skills"] else ["Git"]

    result = seed_internships(
        db_session, validate_records(changed).valid, apply=True
    )
    db_session.commit()
    db_session.expire_all()

    assert (result.created, result.updated) == (0, 1)
    target = db_session.scalar(
        select(Internship).where(Internship.external_id == first["id"])
    )
    assert target.stipend_per_month == 12345
    assert target.knowledge_documents[0].indexing_status == "pending"

    still_off = db_session.scalar(
        select(Internship).where(Internship.external_id == second["id"])
    )
    assert still_off.is_active is False


def test_manage_seed_command_dry_run_and_apply(db_session, capsys):
    assert manage.main(["seed-internships"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "180 would be created" in out
    assert "career_companion_test" in out
    assert count(db_session, Internship) == 0

    assert manage.main(["seed-internships", "--apply"]) == 0
    assert "180 created" in capsys.readouterr().out
    db_session.expire_all()
    assert count(db_session, Internship) == 180


def test_manage_seed_rejects_invalid_file(db_session, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([DATASET[0], DATASET[0]]), encoding="utf-8")

    assert manage.main(["seed-internships", "--apply", "--file", str(bad)]) == 1
    assert "Nothing was written" in capsys.readouterr().out
    assert count(db_session, Internship) == 0


def test_validate_command(capsys):
    assert manage.main(["validate-internships"]) == 0
    assert "Dataset is valid." in capsys.readouterr().out
