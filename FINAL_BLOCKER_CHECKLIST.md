# CareerNova AI — Final Blocker Checklist

Audit date: 2026-11-24. Everything below was re-checked against the code, the database and the machine
on that date rather than copied from older reports. Read-only checks only: `career_companion_dev` was not
modified, no migration was run, no email was sent, nothing was deleted, committed or pushed, and
Windows Smart App Control was not bypassed.

> **Update, 2026-11-24 afternoon** (read-only re-checks during the CareerNova redesign; see
> `CAREERNOVA_TRANSFORMATION_REPORT.md`):
> - blocker 1 — done by the owner: `career_companion_dev` is at head `e1f3a5c7b9d2`, and a fresh
>   database and uploads backup exists (13:14);
> - blocker 3 — eased: PyTorch loads again (no Code Integrity block since 12:02; Smart App Control
>   still on) and a dev search index exists (13:27);
> - blocker 4 — configured: SMTP validates with `EMAIL_MODE=smtp` (nothing was sent);
> - branding — done.
>
> Still open: **no super admin** in dev (blocker 2), **production hosting** (blocker 5), and the
> job-data decision.

## Verdict (morning audit): **NOT READY FOR FINAL DEPLOYMENT**

The code is stable and well tested on the test database, but five things stop a real deployment:

1. **The dev database has not been migrated** (`b2e8c4a7d1f5`, three migrations behind). `.env` points the
   backend at `career_companion_dev`, so the current backend **must not be started** until the migration runs
   (the code expects tables/columns that do not exist yet: `users.is_active`, `admin_audit_events`, …).
2. **No super admin exists** (dev has 2 users, both `student`), so nobody can use the admin area.
3. **Semantic AI is not working on this machine.** Smart App Control blocks PyTorch; the app runs in
   keyword/rule fallback mode. Also no search index has been built (`backend/data/faiss_index` is absent).
4. **Real email is not configured** (`MAIL_FROM` is a placeholder; `EMAIL_MODE` defaults to `outbox`), so
   invitations and password resets reach nobody outside the machine.
5. **There is no production hosting setup** — only development instructions (uvicorn on 127.0.0.1, Vite dev
   server). No HTTPS, no production `FRONTEND_URL`/`CORS_ORIGINS`, API docs (`/docs`) publicly exposed.

Plus two product decisions: all 180 jobs are **fictional sample listings**, and the UI still says
**"AI Career Companion"** while emails say "CareerNova AI".

---

## 1. Completed features (verified)

| Area | Status | Evidence |
|---|---|---|
| Accounts: register, verify email, sign in/out, refresh tokens, forgot/reset password | ✅ | `test_auth`, live run 2026-11-24 |
| Roles student/admin/super_admin, deactivation, protected super admin | ✅ | `test_roles`, `test_admin_security` |
| Login throttling (per email + IP, DB-backed), reset/resend cooldowns (60 s) | ✅ | `test_login_throttle` |
| Admin audit log (14 actions, no secrets stored), labelled in the UI | ✅ | admin tests, live |
| Invitations (add user → email → activation page) | ✅ outbox mode | `test_invitations`, live |
| Resume upload (PDF/DOCX, 5 MB, magic-byte check, per-user storage), parsing, correction, duplicates, readiness score | ✅ | resume tests, live (84/100) |
| Matching (best matches + Explore any job), insights, categories | ✅ (semantic part unavailable here — see §3) | matching tests, live |
| Skill gaps, per-job roadmap, persisted progress (4 states) | ✅ | `test_p3_features`, live |
| Career tracks (11 roles, official documentation links only) | ✅ | tests, live |
| Cover letters / resume customisation, interview prep, application tracking | ✅ | existing suites |
| Career assistant (own data + product guide, memory, sources) | ✅ (keyword fallback here) | assistant suites |
| Optional AI writing: Groq or local Ollama, consent + privacy notice, verified fallbacks | ✅ code; Ollama verified live | §3 |
| Job-source fields, freshness, de-duplication, "Sample listing" labels, admin "Mark verified" | ✅ | `test_p3_features` |
| Migrations `c6d2…`, `d8e4…`, `e1f3…` | ✅ rehearsed on a restored copy | `FINAL_DATABASE_MIGRATION_CHECKLIST.md` |

## 2. Remaining bugs

| # | Bug | Status |
|---|---|---|
| 1 | Privacy notices called local Ollama "an external language-model provider" (it runs on this machine). | **Fixed in this audit** (`backend/services/llm/base.py`, `backend/routes/assistant.py`) + regression tests in `tests/test_ollama_provider.py`. |
| 2 | `.env.example` did not document `EMAIL_MODE`, `MAIL_FROM_NAME`, `SMTP_SECURITY`, `FRONTEND_URL`, `OLLAMA_*`. | **Fixed in this audit** (documentation only; `.env` untouched). |
| 3 | Keyword fallback is less precise than the semantic model (e.g. "delete my resume" can surface a neighbouring guide section). | Open — disappears once PyTorch loads (§3). |
| 4 | Branding mismatch: emails/activation say "CareerNova AI", the rest of the UI says "AI Career Companion". | Open — §7. |

No other code defects were found. **No test fails because of a code bug** (see §9).

## 3. Environment blockers — AI and PyTorch

**Exact cause.** Windows **Smart App Control is ON** (`VerifiedAndReputablePolicyState = 1`). Code Integrity
events 3077/3033 (policy `{0283ac0f-fff1-49ae-ada1-8a933130cad6}`) show `python.exe` being refused
`torch\_C.cp313-win_amd64.pyd` because it "did not meet the Enterprise signing level requirements". The file is
**unsigned** (`Get-AuthenticodeSignature` → `NotSigned`) in both environments (torch 2.15.0 in `.venv` and in
`venv-demo`). Smart App Control allows unsigned files only while its cloud reputation service trusts them;
that trust was evidently withdrawn — the first block was **2026-11-24 10:43**, while the same files loaded on
2026-11-19. `import torch` fails today in both environments with
`DLL load failed while importing _C: An Application Control policy has blocked this file.`

**Safe, owner-controlled ways to resolve it** (choose one; I have not done any of them):

| Option | Effect | Notes |
|---|---|---|
| A. **Run the backend on Linux** — WSL 2 on this PC, a Docker container, or the deployment server | Smart App Control does not apply to Linux binaries; nothing on Windows is weakened | **Recommended.** A production deployment would be on a server anyway. |
| B. Run on a different Windows machine without Smart App Control (or in evaluation mode) | Works unchanged | Development/demo only. |
| C. Turn Smart App Control off (Windows Security → App & browser control → Smart App Control) | Unblocks torch for everything on this PC | **Owner's security decision.** Lowers protection against untrusted programs for the whole PC, and Windows has historically not allowed turning it back on without resetting/reinstalling Windows — check the current Windows behaviour first. |
| D. Wait for the reputation to recover / reinstall a different torch build | Uncertain | Not a dependable fix. |

Signing the DLL yourself is **not** an option: Smart App Control only accepts Microsoft-trusted signatures.

**What needs PyTorch and what does not** (checked in code and with the model blocked):

| Feature | Without PyTorch (now) |
|---|---|
| Semantic internship search (`GET /internships/search`) | **Unavailable** — returns a clear "semantic search unavailable" error |
| Best-match scoring | Works; semantic component marked "unavailable", score uses skills/education/location only |
| Explore any job | Works (never used semantic similarity) |
| Assistant: intent detection | Works with rules; the semantic layer is skipped |
| Assistant: product-guide answers | Works with the **keyword TF-IDF fallback** (threshold 0.25) — less precise |
| Assistant internship search tool | Works with keyword fallback + warning `semantic_search_unavailable` |
| Interview answer evaluation | Works; semantic credit for paraphrases is skipped (keyword hits only) |
| Search index rebuild (`manage rebuild-index`, Admin → Index) | **Unavailable** |
| Resume parsing, readiness, skill gaps, tracks, documents, applications, accounts, admin, email | Not affected |

**Semantic AI is therefore NOT working on this machine; all of the above runs in fallback mode.**
In addition, **no production search index exists** (`backend/data/faiss_index` is missing), so semantic search
stays unavailable after PyTorch is unblocked until `rebuild-index --apply` is run.

**LLM providers, checked independently** (no secrets printed):

| Provider | Configuration in `.env` | Result |
|---|---|---|
| None (default) | `LLM_PROVIDER` not set → `none` | AI writing **off**; `llm_status` = unavailable; all features use the deterministic path |
| Groq | `GROQ_API_KEY` **not set** | Selecting `groq` without a key → AI stays off (safe). **Not verified live** — needs the owner's key |
| Ollama | not set in `.env`; server running on `127.0.0.1:11434` with `gemma3:latest` | Selecting `ollama` → provider available, location `local`; a live JSON call succeeded in **19.4 s** (model warm; ~96 s cold on CPU) |

Fallbacks: provider down/timeout/bad JSON/unverifiable sentences → the standard deterministic answer is shown
(covered by `test_ollama_provider`, assistant and document tests). Embedding model failure → `EmbeddingError`,
cached until restart, keyword fallback (`test_model_unavailable`).

## 4. Database actions

**Current state (read-only check, 2026-11-24):** `career_companion_dev` at **`b2e8c4a7d1f5`**; users 2 (both
`student`), resumes 11, internships 180, match results 135, applications 2, generated documents 9.
`skill_progress`, `admin_audit_events`, `user_invitations`, `email_deliveries`, `auth_rate_limits` and
`users.is_active` do **not** exist yet.

**Pending migrations, verified with `alembic history` (single head `e1f3a5c7b9d2`):**

1. `b2e8c4a7d1f5 → c6d2a8f4b1e3` account security (is_active, roles check, audit log, rate limits)
2. `c6d2a8f4b1e3 → d8e4b2c6a9f1` invitations and email delivery log
3. `d8e4b2c6a9f1 → e1f3a5c7b9d2` skill progress and job-source tracking (dedup keys backfilled)

**Checklist vs code — verified:**

- `DB_NAME` from the shell overrides `.env` (`load_dotenv` does not override existing variables) ✅
- Alembic connects through `backend.database` (so `$env:DB_NAME` selects the database) ✅; Alembic 1.20.1 supports `alembic check` ✅
- `manage create-superadmin --email --first-name --last-name` exists; password asked with hidden input ✅
- Uploads live in `uploads\resumes\<user id>\` (15 files, 1.2 MB) — **must be backed up with the database** ✅ (in the checklist)
- Email outbox writes to `uploads\email_outbox` by default — included in that uploads copy ✅
- Index location `FAISS_INDEX_DIR` default `backend\data\faiss_index` ✅ — **step 4 (rebuild-index) cannot run until PyTorch loads**
- The only backup is **5 days old** (`career_companion_dev_20261119_100709.dump`) and **there is no uploads backup** → a fresh backup of both is mandatory before migrating.
- The restore-rehearsal database `careernova_restore_test_20261119_101233` still exists (kept).

## 5. Job integrations

**What is sample vs live:** all **180 listings are fictional sample data** from `backend/data/internships.json`
(invented companies such as "Basecrest Ventures Inc"; no source URL, application URL, posted date or
verification date in the file). They are labelled "Sample listing (curated dataset)" / "sample data" in the
UI. **Nothing is live.** No verification dates were invented — `last_verified_at` is only set when an admin
presses "Mark verified". Career-track resources are real official documentation links (27, curated), not jobs.

**Legitimate sources that could be integrated** (each needs the owner to accept its terms and, where noted,
obtain a key; confirm current terms before building):

| Source | Access | Fit |
|---|---|---|
| Adzuna Jobs API | free developer key; has India (`/jobs/in/search`) | Best general fit for Indian internships |
| Jooble API | key on request | Aggregator, India covered |
| Greenhouse Job Board API (`boards-api.greenhouse.io/v1/boards/{company}/jobs`) | public, per company | Exact postings from chosen companies |
| Lever Postings API (`api.lever.co/v0/postings/{company}`) | public, per company | Same, Lever customers |
| Remotive / Arbeitnow APIs | public, attribution required | Remote / Europe roles |
| USAJOBS API | free key | US government only |

LinkedIn, Indeed, Naukri and Internshala offer **no open public jobs API**; scraping them would breach their
terms — **do not integrate them that way**. Integration work (not started, by instruction): an importer that
stores `source` / `source_url` / `posted_at`, uses the existing de-duplication, sets `last_verified_at` only
from the feed, and expires listings.

## 6. Email

**Missing for real delivery** (`manage email-check` with `EMAIL_MODE=smtp` simulated, nothing sent):

- `EMAIL_MODE=smtp` — not set (default `outbox`)
- `MAIL_FROM` — **placeholder** → problem "MAIL_FROM still looks like a placeholder address"
- With Gmail, `MAIL_FROM` must equal `SMTP_USERNAME` (or a verified alias) — warning raised
- `SMTP_PASSWORD` — present (for Gmail it must be a 16-character **App Password**, not the account password)
- `FRONTEND_URL` — not set (defaults to `http://localhost:5173`); must be the public site URL in production, or links in emails will point at localhost
- `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, security `starttls` — OK

**Outbox flows verified:** invitation, resend/revoke, activation, verification, password reset and the
"account activated" notice are covered by `test_invitations`, `test_mailer` and `test_auth` (see §9 for this
run) and by the live walkthrough. No real email was sent.

## 7. Branding and UI

`"AI Career Companion"` still appears in **33 places in `frontend/src` (non-test)** plus:
`frontend/index.html` (title + meta description), `frontend/package.json`, the logo text in
`components/brand/BrandMark.jsx`, the mobile home link in `layouts/AppLayout.jsx`, every page's
`document.title` (`AuthHeader.jsx` and ~25 feature pages), the API title/welcome text in `backend/main.py`, the
assistant's product-help texts (`routes/assistant.py`, `services/assistant/product_help.py`,
`services/assistant/service.py`), the product guide (`backend/data/product_docs/01_overview.md` ×3,
`07_applications_and_assistant.md` ×2), `resume_parser.py` docstring, README/docs and 4 test files.

Already "CareerNova AI": email templates and sender name, the invitation/activation page, Career Tracks.

**Work needed (small, no redesign):** one product-name constant in the frontend and backend, replace the
user-visible strings, update the two product-guide files (and the assistant tests that quote the guide),
keep docs in step. Estimated a few hours including tests.

**Responsiveness:** sign-in, password reset and activation pages checked again at 375 px and desktop — no
horizontal overflow. Signed-in pages (dashboard, resumes, matches/Explore, career tracks, roadmap, admin
users/audit) were checked at 375 px on 2026-11-24 earlier; the one overlap found (Explore cards) was fixed.

## 8. Security review

| Area | Finding |
|---|---|
| Passwords | Argon2 hashes (`pwdlib` recommended); never logged; super-admin password by hidden prompt |
| Tokens | JWT HS256, 64-char secret (not a placeholder), 15-min access tokens bound to a DB session, 30-day refresh; deactivation revokes sessions |
| Authorisation | role checks server-side (`require_roles`); students only see their own resumes/documents/applications (ownership tests); protected super admin |
| Uploads | 5 MB limit (413), extension check (415) + `%PDF-` magic bytes / DOCX structure check (400), server-generated names, per-user folder, path confined to the upload root |
| Rate limiting | login throttled per email + IP (DB-backed, survives restarts); forgot-password and resend-verification 60 s per-account cooldown with generic answers (no account enumeration); assistant per-minute/day limits; invitation resend cooldown |
| Audit | 14 admin/security actions; details never contain secrets; append-only from the API |
| CORS | explicit origins only (`*` refused at start-up) |
| API errors | consistent 401/403/404/409/413/415/422/429 with safe messages |
| **Open — deployment hardening** | `/docs` and `/openapi.json` are public (disable or protect in production); no HTTPS/reverse proxy or security headers (HSTS, CSP) configured; public registration has per-account but no per-IP limit; `.env` holds real secrets on disk (git-ignored — keep it so) |

No exploitable defect was found in the application code.

## 9. Tests — exact state

Last **full** run (2026-11-24, before this audit's small fix): backend **1140 passed, 0 failed, 0 skipped,
63 errors**; frontend **390 passed**; production build OK.

**All 63 errors are environmental, not code bugs:** they are the five real-model files
(`test_answer_evaluation_real_model` 12, `test_assistant_intents_real_model` 14,
`test_assistant_product_rag_real_model` 29, `test_embeddings_model` 3, `test_matching_real_model` 5). Each loads
the real sentence-transformers model → `import torch` → blocked by Smart App Control. They passed on
2026-11-19 (1170 passed). They will run again only where PyTorch loads (§3).

This audit's targeted re-run (security, email, uploads, migrations, P3, end-to-end): see the result line below.

| Re-run (2026-11-24, `career_companion_test`) | Result |
|---|---|
| Security, email, uploads, migrations, P3, end-to-end — 14 files (`test_auth`, `test_roles`, `test_admin_security`, `test_login_throttle`, `test_invitations`, `test_mailer`, `test_profiles_resumes`, `test_resume_lifecycle`, `test_assistant_rate_limit`, `test_model_unavailable`, `test_e2e_workflow`, `test_p3_features`, `test_ollama_provider`, `test_migrations`) | **180 passed, 0 failed** (5 min) |
| After the privacy-notice fix: every file using `llm_status` / disclosures (`test_assistant_conversations`, `test_assistant_product_rag`, `test_assistant_review_fixes`, `test_documents_api`, `test_llm_provider`, `test_ollama_provider`) | 129 passed, 1 failed — the failure was my new test being too strict (the notice rightly mentions "external applications"); assertion narrowed → `test_ollama_provider` + `test_llm_provider` **23 passed** |
| Frontend | not re-run: no frontend file changed in this audit (last run 390 passed) |

A full backend re-run was not repeated (26 min, and the 63 environment errors would recur).

**Safe final test plan** (test database only; no real emails):

1. On a machine where PyTorch loads (WSL/Linux/other PC): `python -m pytest tests -q` → expect **0 failed, 0 errors**.
2. `cd frontend; npm test -- --run` → all pass; `npm run build` → OK.
3. After the owner migrates dev: the "quick checks" in `FINAL_DATABASE_MIGRATION_CHECKLIST.md`.
4. After SMTP is configured: `manage email-check`, then one `--send-test` to the owner's own address.
5. Manual smoke test on the deployed site at phone and desktop width: sign in, upload, matches, roadmap, assistant, admin.

---

## 10. Exact next actions, in priority order

1. **Decide how to run PyTorch** (Option A recommended: Linux/WSL/server). — owner
2. **Back up the dev database and the uploads folder** (commands below). — owner
3. **Migrate `career_companion_dev`** to `e1f3a5c7b9d2`, then run the quick checks. — owner
4. **Create the real super admin.** — owner
5. **Rebuild the search index** (only where PyTorch loads), then `index-status`. — owner
6. **Finish the CareerNova rename** in the UI and product guide (small code change; I can do it on request).
7. **Configure SMTP** (`MAIL_FROM`, App Password, `EMAIL_MODE=smtp`, `FRONTEND_URL`) and send one test email. — owner
8. **Choose the job-data policy**: keep labelled samples, or approve one API (Adzuna recommended) to integrate.
9. **Prepare production hosting**: HTTPS reverse proxy, `uvicorn` without `--reload`, built frontend served
   statically, production `FRONTEND_URL`/`CORS_ORIGINS`, `/docs` disabled, backups scheduled.
10. Run the full final test plan (§9) on the deployment environment.
11. Optionally drop the rehearsal database `careernova_restore_test_20261119_101233`.

## 11. Exact commands requiring owner approval

Run from the project folder in PowerShell, **backend stopped**. `pg_dump`/`psql` ask for the PostgreSQL
password (nothing is stored in the commands).

```powershell
cd "<project-root>"
$pg = "C:\Program Files\PostgreSQL\17\bin"
$backup = "$HOME\CareerNova_Backups"   # any folder outside the project
$stamp = Get-Date -Format yyyyMMdd_HHmmss
```

**A. Backup database + uploads (non-destructive)**

```powershell
& "$pg\pg_dump.exe" -h localhost -U postgres -Fc -f "$backup\career_companion_dev_$stamp.dump" career_companion_dev
Copy-Item -Recurse uploads "$backup\uploads_$stamp"
& "$pg\pg_restore.exe" --list "$backup\career_companion_dev_$stamp.dump" | Select-Object -First 5   # backup is readable
(Get-ChildItem -Recurse -File "$backup\uploads_$stamp").Count                                       # expect 15 (or more)
```

**B. Migrate the dev database (changes the schema — needs approval)**

```powershell
$env:DB_NAME = 'career_companion_dev'
.\.venv\Scripts\python.exe -m alembic current      # expect b2e8c4a7d1f5
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current      # expect e1f3a5c7b9d2 (head)
.\.venv\Scripts\python.exe -m alembic check        # expect: No new upgrade operations detected.
```

Rollback if needed before any new data exists: `.\.venv\Scripts\python.exe -m alembic downgrade b2e8c4a7d1f5`;
otherwise restore backup A into a new database (`createdb` + `pg_restore --no-owner`).

**C. Create the super admin (creates an account — needs approval)**

```powershell
.\.venv\Scripts\python.exe -m backend.manage create-superadmin --email <owner email> --first-name <First> --last-name <Last>
```

**D. Rebuild the search index (only where `import torch` works)**

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__)"   # must succeed first
.\.venv\Scripts\python.exe -m backend.manage rebuild-index               # dry run
.\.venv\Scripts\python.exe -m backend.manage rebuild-index --apply
.\.venv\Scripts\python.exe -m backend.manage index-status
```

**E. Real email (sends a real email — needs approval)** — after editing `.env` yourself:
`EMAIL_MODE=smtp`, `MAIL_FROM=<the Gmail address you sign in with>`, `SMTP_USERNAME=<same>`,
`SMTP_PASSWORD=<Gmail App Password>`, `FRONTEND_URL=<public site URL>`.

```powershell
.\.venv\Scripts\python.exe -m backend.manage email-check
.\.venv\Scripts\python.exe -m backend.manage email-check --send-test <your own address>
```

**F. Optional clean-up (irreversible — only if you no longer need the rehearsal copy)**

```powershell
& "$pg\dropdb.exe" -h localhost -U postgres careernova_restore_test_20261119_101233
```
