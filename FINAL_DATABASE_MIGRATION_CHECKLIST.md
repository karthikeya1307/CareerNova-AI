# Final Database Migration Checklist — CareerNova AI

> **Status 2026-11-25: both migrations are APPLIED to `career_companion_dev`** (owner-approved, 13:23 IST), after a
> fresh, verified backup. Dev is at head `a7c9e1b3d5f6`. The procedure below is kept as the record and for other
> environments; do not repeat it on dev.
>
> Paths: `<project-root>` is the folder that holds this repository; `<backup-folder>` is the owner's backup folder
> outside the project (the commands below use `$HOME\CareerNova_Backups`; use any folder you prefer).

## What was done on dev (2026-11-25, each step approved by the owner)

| Step | Result |
|---|---|
| 1. Fresh backup | `<backup-folder>\career_companion_dev_20261125_132146.dump` (240,548 bytes, SHA-256 `d432d3e75ba1bbfc87fd271c41f8bb89121d6e2af4d4236a4ea38a149b883c22`) and `uploads_20261125_132146\` |
| 1b. Integrity check | `pg_restore --list` OK (343 entries); restored into the separate database `career_companion_restorecheck` with no errors; all 34 tables' row counts, the revision and content fingerprints of users / student_profiles / resumes identical; uploads 27 files / 1,719,466 bytes, every file's SHA-256 identical. Record: `backup_verification_20261125_132146.txt` |
| 2. Migration | backend stopped, 0 other sessions; `alembic current` = `e1f3a5c7b9d2` → `alembic upgrade head` (`f2b4d6a8c0e1`, `a7c9e1b3d5f6`) → `alembic current` = **`a7c9e1b3d5f6` (head)**; `alembic check`: *No new upgrade operations detected* |
| 2b. Data check | all 34 existing tables: row counts unchanged; fingerprints of users / student_profiles / resumes (original columns) unchanged; new tables empty; new columns empty / false on every existing row; user 5 untouched |
| 2c. Schema check | new columns, the partial unique index `uq_resumes_one_preferred_per_user` (`WHERE is_preferred`), study-document indexes, unique / check constraints and `ON DELETE CASCADE` foreign keys all present. Record: `migration_verification_20261125_132356.txt` |
| 3. Post-migration checks | backend on dev: `/health` = `career_companion_dev`; signed-out requests 401; new routes registered; endpoint functions run read-only for existing students (resume versions V1…, none preferred; profile with initials; both assistants' chat lists; prep roles) |
| 3b. Signed-in UI (owner signed in) | dashboard, resumes, profile, Application Assistant and Interview Prep Assistant load correctly; server log: only GET requests besides sign-in / token refresh; dev snapshot afterwards: only `auth_sessions` +1 (the sign-in) |

Kept, not deleted (owner decides): the backups above and the scratch database `career_companion_restorecheck`.
User 5 (`priya.test@example.com`, created accidentally on 2026-11-24) is still untouched.

## The two migrations (additive only; no existing row or value is changed)

| Order | Revision | What it adds | Existing data | Downgrade |
|---|---|---|---|---|
| 1 | `f2b4d6a8c0e1` study documents | Tables `study_documents` (owner, file name, type, size, sha256, page/section/char/chunk counts, warnings) and `study_document_chunks` (passage text, page, section). Cascade deletes with the user. The original files are not stored | none | refuses while any study document exists, unless `-x study_allow_data_loss=true` |
| 2 | `a7c9e1b3d5f6` profile + resume versions | `student_profiles.bio`, `avatar_path`, `avatar_content_type`, `avatar_updated_at` (all NULL). `resumes.label` (NULL), `resumes.is_preferred` (false). Partial unique index: at most one preferred resume per student | every existing profile and resume keeps its values; new fields are empty/false, so the app behaves as before until a student uses them | refuses while any bio, picture, resume name or preferred resume exists, unless `-x profile_allow_data_loss=true` (picture files are never deleted by a migration) |

The current backend code needs both migrations; an environment without them must run the older code.

## Verification evidence (test database only)

- `tests/test_migrations.py` (**15 tests**):
  - single head `a7c9e1b3d5f6`;
  - every migration up → down → up;
  - no model/migration drift (`alembic check`);
  - the study-documents migration is additive, its downgrade refuses while documents exist, and documents cascade on user delete;
  - the profile/resume-version migration keeps existing profile and resume rows unchanged, enforces one preferred resume per student, and its downgrade refuses while new data exists.
- The full backend suite builds the schema from head on `career_companion_test`: final run 2026-11-25,
  **1333 passed, 0 failed** on 2026-11-26 (see `CAREERNOVA_TEST_REPORT.md`).
- Every automated test run, evaluation and demo targeted `career_companion_test` (checked before each run). The only
  commands run against `career_companion_dev` were the owner-approved backup, migration and read-only checks above.

## Production database (2026-11-26 - prepared, not created)

- A fresh production database is created empty and brought to head by `alembic upgrade head` (Render runs it as the
  pre-deploy command, see `render.yaml`). No dev data is copied to production.
- Managed PostgreSQL needs TLS: set `DB_SSLMODE=require` (Neon or external URLs). Verified locally that the setting
  reaches the driver.
- Latest regression on the test database: **1333 passed, 0 failed, 0 errors** (2026-11-26), including the 15 migration tests.

## Final audit note (2026-11-26)

- No new migration was needed for the final audit (parser, assistant guide and readiness changes are code-only).
- Dev was only read during the audit (revision `a7c9e1b3d5f6`, row counts unchanged apart from the owner's own sign-ins
  and uploads). Existing dev resumes keep their stored extractions until the owner presses Re-parse; the dev backend
  must be restarted to load the new parser before doing so.

## Procedure (as run on dev on 2026-11-25; backend stopped)

```powershell
cd "<project-root>"
$pg = "C:\Program Files\PostgreSQL\17\bin"
$backup = "$HOME\CareerNova_Backups"   # any folder outside the project
$stamp = Get-Date -Format yyyyMMdd_HHmmss
```

**1. Fresh backup of the database AND the uploads folder** (non-destructive; PostgreSQL asks for its password):
```powershell
& "$pg\pg_dump.exe" -h localhost -U postgres -Fc -f "$backup\career_companion_dev_$stamp.dump" career_companion_dev
Copy-Item -Recurse uploads "$backup\uploads_$stamp"
& "$pg\pg_restore.exe" --list "$backup\career_companion_dev_$stamp.dump" | Select-Object -First 5
```

**2. Check, migrate, check** (changes the dev schema — needs approval):
```powershell
$env:DB_NAME = 'career_companion_dev'
.\.venv\Scripts\python.exe -m alembic current      # expect e1f3a5c7b9d2
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current      # expect a7c9e1b3d5f6 (head)
.\.venv\Scripts\python.exe -m alembic check        # expect: No new upgrade operations detected.
```

**3. Quick checks after migrating:**
- `GET /health` is Healthy; an existing student can sign in.
- Resumes page: every existing resume is listed with V1, V2… and none is marked preferred.
- Profile page: picture shows initials; the bio is empty.
- Interview Preparation Assistant: upload a small PDF and ask about it.

## Rollback

- **Before anyone uses the new features:**
  ```powershell
  .\.venv\Scripts\python.exe -m alembic downgrade e1f3a5c7b9d2
  ```
- **Otherwise:** restore the step-1 backup into a **new** database (`createdb` + `pg_restore --no-owner`), point `DB_NAME` at it, and copy the `uploads_<stamp>` folder back if needed.
- **Never** drop or overwrite `career_companion_dev` itself.

## Earlier migrations (already applied to dev by the owner)

`c6d2a8f4b1e3` account security → `d8e4b2c6a9f1` invitations/email log → `e1f3a5c7b9d2` skill progress/job sources —
rehearsed on a restored copy on 2026-11-24 (row counts and password hashes unchanged).
