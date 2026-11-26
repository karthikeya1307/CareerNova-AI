# CareerNova AI — Deployment and Handover Guide

*Your Skills. Your Potential. Your Career.*

Stack: FastAPI (Python 3.13) · PostgreSQL 17 · Alembic · React + Vite + Tailwind · local sentence-embedding model
(MiniLM, CPU) · optional LLM (Groq or local Ollama + Gemma 3). Branch `careernova/dashboard-redesign`
(work not yet committed). HR has approved GitHub publication and deployment; each step still needs the owner's go-ahead (see §7).

## 1. Start the project (development)

```powershell
cd "<project-root>"
# Backend (http://127.0.0.1:8000, API docs at /docs)
$env:DB_NAME = 'career_companion_dev'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
```powershell
# Frontend (http://localhost:5173) - second terminal
cd "<project-root>\frontend"; npm install; npm run dev
```

The dev database is at Alembic head `a7c9e1b3d5f6` (2026-11-25). Restart the backend after pulling new code (it does
not auto-reload). Check `http://127.0.0.1:8000/health` shows `Healthy` and the expected database.

## 2. Environment variables (`.env`, never committed; documented in `.env.example`)

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection |
| `DB_SSLMODE` | `require` for managed/cloud PostgreSQL (Neon, external URLs); empty locally |
| `TEST_DB_NAME` | Test database (must end with `_test`; default `career_companion_test`) |
| `JWT_SECRET_KEY` | Signs access tokens (long random value; new value per environment) |
| `FRONTEND_URL`, `APP_BASE_URL` | Public URLs used in email links |
| `CORS_ORIGINS` | Exact frontend origins (comma-separated; `*` is refused) |
| `EMAIL_MODE` | `outbox` (default: nothing sent, `.eml` files in `EMAIL_OUTBOX_DIR`), `smtp`, `disabled` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM`, `MAIL_FROM_NAME`, `SMTP_TIMEOUT_SECONDS` | Real email — see `SMTP_SETUP.md` |
| `LLM_PROVIDER` | `none` (default), `groq` (+ `GROQ_API_KEY`, `GROQ_MODEL`, `LLM_TIMEOUT_SECONDS`) or `ollama` (+ `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`) |
| `EMBEDDING_MODEL`, `EMBEDDING_MODEL_REVISION`, `EMBEDDING_CACHE_DIR` | Local embedding model (downloaded once: `python -m backend.manage download-embedding-model`) |
| `FAISS_INDEX_DIR` | Folder for the internship search index (NumPy format; name kept for compatibility) |

## 3. Database

1. Back up the database **and** `uploads/` first (`FINAL_DATABASE_MIGRATION_CHECKLIST.md` has the exact commands and an
   integrity check: restore into a separate database and compare row counts).
2. `alembic current` → `alembic upgrade head` → `alembic check`.
3. Seed or update the curated internship dataset only if needed: `python -m backend.manage seed-internships --apply`.
4. Rebuild the search index: `python -m backend.manage rebuild-index --apply` (or Admin → Search index).

## 4. Super admin, admins and onboarding

* Create the single super admin: `python -m backend.manage create-superadmin --email … --first-name … --last-name …`
  (password asked twice, hidden). Details: `SUPER_ADMIN_SETUP.md`.
* **Invite a user:** Admin → Users → *Add user* (72 h single-use invitation; the person sets their own password).
* Students can self-register (`/register`) and verify by email.
* Deactivate/reactivate and role changes from Admin → Users; everything is recorded in Admin → Audit log.

## 5. Using the product

| Task | Where |
|---|---|
| Profile, picture (PNG/JPEG/WebP ≤ 2 MB), bio | Profile |
| Upload resume versions (PDF/DOCX ≤ 5 MB), name them, set the preferred one, compare two | Resumes (identical uploads are flagged) |
| Review/correct extracted details | Resumes → *Edit details*. Your version is used everywhere; *Re-parse* reads the file again and **asks first** if you have corrections. The original file is never changed |
| Resume readiness (0–100, resume content only) | Resumes → readiness panel (names the scored version) |
| ATS keyword checks for one posting | Dashboard → ATS check (after matching) |
| Job matching, skill gaps, roadmap | Matches, Skill gaps |
| Career tracks (14 roles) | Career tracks |
| Tailored resume, cover letter | Documents |
| Mock interviews | Interview practice |
| Application tracking | Applications |
| How to use CareerNova, your data | **Application Assistant** (step-by-step guide, product guide, your data; declines other topics) |
| Roles, interview questions, guidance, roadmap, study-document Q&A | **Interview Preparation Assistant** |

## 6. AI providers

* Off by default; every feature works without AI (deterministic, sourced answers).
* **Local Gemma 3 (Ollama):** install Ollama, `ollama pull gemma3`, set `LLM_PROVIDER=ollama`. On a CPU, answers took
  15-60 s here (first answer longer while the model loads). Nothing leaves the machine.
* **Groq:** `LLM_PROVIDER=groq`, `GROQ_API_KEY=…` (external service; students consent per request; not tested live).
* If the provider is down or an answer cannot be verified against the sources, the standard answer is shown with a note.

## 7. Production deployment (your accounts only)

Everything below runs in **your own** GitHub, Vercel, Render and database accounts, signed in through your own
browser. No credential is stored in the repository or in any Claude configuration. Status of each step is recorded
in `CAREERNOVA_IMPLEMENTATION_REPORT.md`.

### 7.1 Architecture (Render free plan + Neon + Vercel)

```
Browser ──HTTPS──> Vercel (frontend/dist, React) ──HTTPS + Bearer token──> Render free web service (FastAPI)
                                                                              ├──TLS──> Neon PostgreSQL (DB_SSLMODE=require)
                                                                              └──HTTPS──> Brevo email API (verification links)
AI rewording: off (LLM_PROVIDER=none) or Groq (hosted). Ollama/Gemma 3 is local-only and does not run on Render.
```

**Render free-plan limits (render.com/docs/free) and how the project handles them**

| Limit | Effect on CareerNova | Handling |
|---|---|---|
| 512 MB RAM | PyTorch + the embedding model need ~1 GB | Model not downloaded; semantic search/matching use the tested keyword fallback; PyTorch is never loaded |
| No pre-deploy command, no shell | Cannot run migrations or CLI commands on the server | `backend/deploy_db.py` runs in the **build command** |
| No persistent disk | Uploaded files (resumes, pictures) disappear after each deploy/restart/sleep | Extracted resume data stays in PostgreSQL; re-upload a file to download it again. For permanent files: paid plan + disk |
| SMTP ports 25/465/587 blocked | Gmail SMTP cannot send verification emails | `EMAIL_MODE=brevo` (HTTPS API, free 300 emails/day) |
| Sleeps after 15 min idle | First request after a pause takes ~1 minute | Open `/health` first before a demo |

### 7.2 Database (Neon)
Create a Neon project and copy host, database, role and password into the Render environment (7.3) with
`DB_SSLMODE=require`. **Do not run `alembic upgrade head` on an empty database**: the migration history starts from
an empty baseline (`9c59adb5cc64`, recorded on a database whose tables already existed), so it fails with
`relation "users" does not exist`. Use `python -m backend.deploy_db` instead:

| Database state | What `deploy_db` does |
|---|---|
| empty (or only a leftover `alembic_version` row from a failed attempt) | creates the current schema from the models and stamps head **in one transaction** |
| managed by Alembic | normal `alembic upgrade head` (no-op when current) |
| tables but no Alembic version | stops and changes nothing |

`--check` reports what would happen without changing anything; `--seed-if-empty` loads the 180 curated internships
only when the catalogue is empty. The create-and-stamp schema was compared with a database migrated through the full
history: identical tables, columns, defaults, constraints, partial/functional indexes and sequences
(`tests/test_deploy_db.py`, `tests/test_migrations.py`).

### 7.3 Backend on Render (free plan)
Settings (Dashboard → `careernova-api` → Settings; the same values are in `render.yaml`):

| Field | Value |
|---|---|
| Branch | `careernova/dashboard-redesign` (or `main` after merging) |
| Root directory | *(empty)* |
| Runtime / plan | Python 3 / Free |
| Build command | `pip install --upgrade pip && pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt && python -m backend.deploy_db --seed-if-empty` |
| Start command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` |
| Health check path | `/health` |
| Pre-deploy command | *(empty - not available on free)* |

`--forwarded-allow-ips='*'` makes the app see each visitor's own IP behind Render's proxy; without it every visitor
shares one login-throttle bucket.

Environment variables: `PYTHON_VERSION=3.13.13`, `DB_HOST`, `DB_PORT=5432`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`DB_SSLMODE=require`, `JWT_SECRET_KEY` (long random value), `CORS_ORIGINS` and `FRONTEND_URL` (your Vercel URL, no
trailing slash), `EMAIL_MODE=brevo`, `BREVO_API_KEY`, `MAIL_FROM` (sender verified in Brevo), `MAIL_FROM_NAME=CareerNova AI`,
`LLM_PROVIDER=none`. Do not set `FAISS_INDEX_DIR`, `EMBEDDING_CACHE_DIR` or `APP_BASE_URL` (unused).

Super admin (optional, run on your computer against Neon in a PowerShell window; values exist only in that window):
`python -m backend.manage create-superadmin --email <you> --first-name <..> --last-name <..>`.

### 7.4 Frontend on Vercel
1. Vercel (your account) → **Add New → Project** → import `CareerNova-AI` → branch as above.
2. **Root Directory: `frontend`** · Framework: Vite · Build: `npm run build` · Output: `dist` (`frontend/vercel.json`
   adds SPA routing and security headers).
3. Environment variable (Production): `VITE_API_BASE_URL = https://<your-render-service>.onrender.com` (no trailing slash).
   It is built into the JavaScript, so change it → redeploy.
4. Deploy, then put the final Vercel URL into Render's `CORS_ORIGINS` and `FRONTEND_URL` and redeploy the backend.

### 7.5 After deployment - smoke test
`https://<backend>/health` → `Healthy` · `https://<backend>/internships/filters` needs a login (401) · open the Vercel URL
→ register with your own email → verification email arrives (Brevo) → sign in → upload a fictional resume → readiness,
matches, skills & gaps, AI search, both assistants · a second account cannot see the first account's data.

### 7.6 Ollama / Gemma 3 options
| Option | Cost | Privacy | Reliability | When |
|---|---|---|---|---|
| Dedicated machine (CPU, or GPU for speed) running Ollama, reachable only by the backend | VM cost; GPU is expensive | Best - data stays on your server | CPU 15-60 s per answer | If AI must stay private |
| Hosted API (Groq) | Per request; free tier exists | Excerpts leave your server (consent + notice built in) | Fast; external dependency | Simplest |
| **Hybrid (recommended)**: AI off by default, enable Groq or an Ollama VM later | Lowest | Good | App never depends on AI | HR demo |

### 7.7 Backups and maintenance
- Database: enable the provider's automated backups; before each migration take a manual dump (`pg_dump`).
- Uploads: on the free plan files are not kept (no disk); on a paid plan add a disk and use its snapshots.
- Updates: push to `main` (or your release branch) → Render "Manual Deploy" (auto-deploy is off) → Vercel redeploys
  automatically from Git.

### 7.8 Continuing without this Claude session
Everything needed is in the repository: `README.md`, this guide, `.env.example`, `render.yaml`,
`frontend/vercel.json`, `FINAL_DATABASE_MIGRATION_CHECKLIST.md`, `MANUAL_ACCEPTANCE_CHECKLIST.md`. Local development:
section 1; tests: section 9. No step depends on Claude or on another person's account.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| New features missing after updating code | Restart the backend (no auto-reload); check `alembic current` is the head |
| Sign-in fails after updating code | Migrations not applied: `alembic upgrade head` (after a backup) |
| "Too many failed sign-in attempts" (429) | Wait 15 minutes (5 failures per email per 15 min) |
| Assistant says "Too many assistant requests" (429) | Limit is 10 messages per minute / 300 per day; wait and retry |
| Invitation email "failed" | `python -m backend.manage email-check`; fix SMTP settings; *Resend invitation* |
| Emails not arriving in outbox mode | Expected: look in the outbox folder (`uploads/email_outbox/` by default) |
| "Semantic search is temporarily unavailable" | Admin: `python -m backend.manage rebuild-index --apply` and `index-status`; download the embedding model if missing. Keyword search keeps working |
| AI answers slow or missing | `ollama list`, raise `OLLAMA_TIMEOUT_SECONDS`, or set `LLM_PROVIDER=none` |
| Resume parsed poorly (old extraction) | Restart the backend with the latest code, then *Re-parse* (asks before replacing corrections) or *Edit details*. Scanned (image-only) PDFs have no text (no OCR) |
| Frontend tests time out on a slow PC | Run `npx vitest run --maxWorkers=2` |

## 9. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q        # uses the *_test database only (refuses other names)
```
```powershell
cd "<project-root>\frontend"; npx vitest run --maxWorkers=2; npm run build
```
