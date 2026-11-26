# Super Admin Setup — CareerNova AI

CareerNova AI has three roles:

| Role | Can |
|---|---|
| `student` | Use the career features with their own data. Default for every registered account. |
| `admin` | Everything a student can, plus: list/search users, create pending student accounts, deactivate/reactivate students, manage internships and the search index, read the audit log. |
| `super_admin` | Everything an admin can, plus: change roles (student ↔ admin), create admin accounts, deactivate/reactivate admins. Exactly **one** can exist (enforced by the database). |

The super admin account **cannot be demoted, deactivated or deleted through the app or API**, and the
`super_admin` role is **never granted through the API** — only with the command below.

## Prerequisite

The account-security migration (`c6d2a8f4b1e3`) must be applied first — see `DATABASE_MIGRATION_GUIDE.md`.

## Create the super admin (owner runs this)

From the project folder in PowerShell:

```powershell
$env:DB_NAME = 'career_companion_dev'
.\.venv\Scripts\python.exe -m backend.manage create-superadmin --email owner@yourdomain.com --first-name Ada --last-name Owner
```

* The password is asked for **twice with hidden input**. It is never a command-line argument, never
  printed and never logged. Rules: 8–128 characters with at least one letter and one number.
* The account is created verified and active, and one `superadmin.bootstrap` audit event is written.
* Running the command again with the same email changes nothing (exit 0). A different email is
  refused while a super admin exists (exit 1).

To make an **existing** verified, active account the super admin (its password stays the same):

```powershell
.\.venv\Scripts\python.exe -m backend.manage create-superadmin --email existing@yourdomain.com --promote-existing
```

Recommendation: use a dedicated account for the super admin, not a student demo account.

## Other administrators

* In the app: Admin → Users → **Make admin** (super admin only), or **Add user** with role Admin.
* Or from the command line: `.\.venv\Scripts\python.exe -m backend.manage set-role <email> admin`
  (cannot grant or change `super_admin`; audited).

## Security notes

* Every authenticated request rejects deactivated accounts, including tokens issued before the
  deactivation; deactivation also signs the user out of every session.
* Failed sign-ins: 5 per email (50 per client address) per 15 minutes, then HTTP 429 with `Retry-After`.
* The audit log (Admin → Audit log) never stores passwords, hashes, tokens or credentials.
