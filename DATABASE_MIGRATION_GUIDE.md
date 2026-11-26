# Database Migration Guide — CareerNova AI

This guide covers the pending migrations, the verified backup, the rehearsal on a restored copy,
and the exact steps to migrate `career_companion_dev` **after owner approval**.

> Nothing in this guide has been run against `career_companion_dev`. As of 2026-11-19 it is at
> revision `b2e8c4a7d1f5` (Phase 8, conversational assistant).

## 1. Pending migration: `c6d2a8f4b1e3` — account security (Phase 1)

File: `migrations/versions/c6d2a8f4b1e3_account_security.py` (revises `b2e8c4a7d1f5`).

| Change | Effect on existing data |
|---|---|
| `users.is_active` BOOLEAN NOT NULL DEFAULT true | Every existing user becomes active (unchanged behaviour). |
| `users.deactivated_at`, `users.last_login_at` (nullable) | NULL for everyone. |
| CHECK `ck_users_role`: role in (student, admin, super_admin) | Upgrade first verifies stored roles; if any other value exists it **refuses and changes nothing**. |
| Partial unique index `uq_users_single_super_admin` | At most one super admin can ever exist. |
| New table `admin_audit_events` | Empty. |
| New table `auth_rate_limits` | Empty (failed sign-in counters, hashed keys). |

No row is deleted or rewritten; passwords, resumes, applications, conversations and documents are untouched.

**Downgrade** refuses (changes nothing) while audit events, a super admin or deactivated accounts
exist, because dropping `is_active` would silently re-enable deactivated accounts. It can be forced
with `-x accounts_allow_data_loss=true` (a super admin then becomes an admin).

**After this migration the backend requires it**: start the new backend code only after
`alembic upgrade head` has run, otherwise user queries fail (`users.is_active` missing).

## 1b. Pending migration: `d8e4b2c6a9f1` — invitations and email log (Phase 2)

File: `migrations/versions/d8e4b2c6a9f1_invitations_and_email_log.py` (revises `c6d2a8f4b1e3`).

| Change | Effect on existing data |
|---|---|
| New table `user_invitations` (single-use, expiring activation links; token stored only as SHA-256 hash; delivery status) | Empty. |
| New table `email_deliveries` (kind, recipient, status, error code — no body, links or tokens) | Empty. |

Purely additive. Downgrade refuses while either table has rows unless `-x invitations_allow_data_loss=true`.

## 2. Backup verification (done 2026-11-19, no change to the original)

Backup: `<backup-folder>\career_companion_dev_20261119_100709.dump` (189,789 bytes).

| Check | Result |
|---|---|
| `pg_restore --list` | exit 0, 290 TOC entries, 29 table-data entries |
| Restore into new database `careernova_restore_test_20261119_101233` | exit 0 (`--no-owner --no-privileges --exit-on-error`) |
| Alembic revision (restored vs original) | `b2e8c4a7d1f5` = `b2e8c4a7d1f5` |
| Tables / foreign keys / indexes | 29 / 44 / 88 on both |
| Row counts in every table | identical (e.g. users 2, resumes 11, internships 180, match_results 135, messages 12) |

The `.dump` contains database rows only. **Uploaded resume files (`uploads/resumes/`) are not in it**;
copy that folder too before migrating (step 4.1).

The temporary database `careernova_restore_test_20261119_101233` still exists. It can be removed
with `dropdb` once you no longer need it (owner approval; see section 5).

## 3. Rehearsal on the restored copy (done 2026-11-19)

Run only against `careernova_restore_test_20261119_101233` (the script refuses any other name):

| Step | Result |
|---|---|
| upgrade `b2e8c4a7d1f5` → `c6d2a8f4b1e3` | success |
| Row counts in 14 data tables | unchanged |
| User rows (id, email, role, verified, password hash) | unchanged |
| New columns | 2/2 users active, no deactivation, no last login |
| New tables | present; 0 super admins |
| `alembic check` (model vs migration drift) | no drift |
| downgrade to `b2e8c4a7d1f5`, then upgrade again | success, data unchanged both times |
| upgrade `c6d2a8f4b1e3` → `d8e4b2c6a9f1` | success; row counts and user rows (incl. `is_active`) unchanged; new tables present |
| `alembic check` at `d8e4b2c6a9f1` | no drift |
| downgrade to `c6d2a8f4b1e3`, then upgrade again | success, data unchanged both times |

The restored copy is now at `d8e4b2c6a9f1`.

## 4. Migrating `career_companion_dev` (owner approval required)

Run in PowerShell from the project folder, with the backend **stopped**:

```powershell
# 4.1 Fresh database backup and a copy of the uploaded resume files
$stamp = Get-Date -Format yyyyMMdd_HHmmss
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" -h localhost -U postgres -Fc -f "$HOME\CareerNova_Backups\career_companion_dev_$stamp.dump" career_companion_dev
Copy-Item -Recurse uploads "$HOME\CareerNova_Backups\uploads_$stamp"

# 4.2 Show where the database is, then upgrade
$env:DB_NAME = 'career_companion_dev'
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current      # expect d8e4b2c6a9f1 (head)
```

(`pg_dump` asks for the database password; use your own `-U` user if it is not `postgres`.)

`alembic upgrade head` applies both pending migrations in order (`c6d2a8f4b1e3`, then `d8e4b2c6a9f1`).

Rollback, if ever needed and before any super admin/deactivation/invitation exists:
`.\.venv\Scripts\python.exe -m alembic downgrade b2e8c4a7d1f5` — or restore the 4.1 backup into a
new database and point `DB_NAME` at it.

## 5. Removing the temporary restore database (optional, owner approval)

```powershell
& "C:\Program Files\PostgreSQL\17\bin\dropdb.exe" -h localhost -U postgres careernova_restore_test_20261119_101233
```
