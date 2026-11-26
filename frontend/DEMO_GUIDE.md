# AI Career Companion — HR Demonstration Guide

A guide for a controlled, local demonstration of the AI Career Companion web app (React frontend +
FastAPI backend). It contains no credentials or secrets: demo accounts and configuration values are
prepared separately by the project owner.

> Status: a working local prototype built for a technical assignment. It has not been deployed to
> production and has not been evaluated with real students or real job-market data.

## 1. What the application does

AI Career Companion helps a student go from a resume to internship applications:

1. Upload a resume (PDF/DOCX). The backend extracts skills, education, experience and projects.
2. Find internships by browsing, keyword filters or semantic search.
3. Get ranked internship matches with a transparent compatibility score and explanation.
4. See skill gaps against those internships, with a prioritised learning plan.
5. Generate a tailored resume and cover letter that only use facts from the student's resume, with a
   fact-check report.
6. Practise interview questions generated from the resume and internship, with rubric-based feedback.
7. Track applications, company interview rounds and reminders.
8. Ask a career assistant questions about all of the above; answers show their sources.

Administrators manage the internship catalogue, user roles and the search index.

### Architecture and technologies

```
Browser (React SPA, localhost:5173)
   │  /api/* via the Vite dev proxy (same origin, no CORS)
   ▼
FastAPI backend (127.0.0.1:8000) ── JWT access token (memory) + rotating refresh token
   ├── PostgreSQL ............ users, resumes, internships, matches, documents, sessions, applications, chats
   ├── uploads/ ............... uploaded resume files (private, per user)
   ├── FAISS index ............ internship vectors only (rebuilt from PostgreSQL)
   ├── all-MiniLM-L6-v2 ....... local sentence-embedding model (no external call)
   └── optional LLM provider .. Groq, only if configured and the user consents per request
```

| Layer | Technologies |
|---|---|
| Frontend | React 18, React Router 7, Vite 7, Tailwind CSS 3, Axios; tests with Vitest, React Testing Library and MSW (mocked API) |
| Backend | Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, PyJWT |
| Search and NLP | sentence-transformers (`all-MiniLM-L6-v2`, 384-dim), FAISS (CPU), pypdf and python-docx for resume parsing and DOCX export |
| Data | PostgreSQL (separate databases for development and tests) |

Each feature page of the frontend is downloaded on demand (route-level code splitting), so the first
screen loads a 344 kB bundle (111 kB compressed) instead of the whole app.

## 2. Features to show

**Student**

| Page | URL | What to point out |
|---|---|---|
| Dashboard | `/` | Latest resume, best match, ATS check, skills, interview practice, applications, assistant — each card loads and fails independently |
| Resumes | `/resumes` | Upload with progress, extracted information, re-parse, download, delete with typed confirmation |
| Internships | `/internships` | Browse with filters; semantic search ("machine learning with python"); internship detail with save, mark as applied, tailor resume, practise interview |
| Matches | `/matches` | Compatibility score (skills 50%, semantic 20%, education 15%, location 15%), matched/missing skills, caps and reasons |
| Skill gaps | `/skill-gaps` | Missing skills by priority, learning plans, progress status |
| Documents | `/documents` | Tailored resume / cover letter, "From your resume" markers, fact-check results, versions, DOCX/TXT download |
| Interview practice | `/interview-prep` | Practice and mock modes, answer evaluation (score, covered/missed key points, STAR check), session results |
| Applications | `/applications` | Status pipeline with allowed transitions only, history, company interview rounds, stored reminders, trash |
| Career assistant | `/assistant` | Suggested questions, answers with sources and result lists, suggested next steps that link to the right page |

**Administrator** (an account with the admin role; the menu shows an "Admin" section)

| Page | URL | What to point out |
|---|---|---|
| Admin overview | `/admin` | Counts computed from live data, index status |
| Users | `/admin/users` | Role changes with confirmation; you cannot remove your own admin role |
| Manage internships | `/admin/internships` | Add, edit, deactivate (soft) and reactivate internships |
| Search index | `/admin/index` | Index status. **Do not click "Rebuild" during a demo** unless you intend to rebuild the dev index; it can take minutes |

## 3. Recommended demo sequence (about 15 minutes)

1. **Sign in** as the prepared demo student → dashboard.
2. **Resumes**: show the parsed demo resume (skills, education, projects). Use a synthetic resume only.
3. **Internships**: run a semantic search, open an internship, point out required/preferred skills.
4. **Matches**: open the best match and walk through the score breakdown and missing skills.
5. **Skill gaps**: open "View skill gap and learning plan" for that internship; show the learning plan.
6. **Documents**: from the internship, "Tailor my resume"; generate with the standard (no AI) method;
   show the fact-check panel and the "From your resume" markers; download the DOCX.
7. **Interview practice**: start a short practice session for the same internship; answer one question
   and show the evaluation; finish the session for the summary.
8. **Applications**: mark the internship as applied; change status to Shortlisted; add an interview round
   and show the automatic "Interview scheduled" status; add a reminder and note that it is stored only.
9. **Career assistant**: ask "What skills am I missing?" and "Where do my applications stand?"; open the
   sources and a suggested next step.
10. Back to the **dashboard**: the cards now reflect the new data.
11. **Admin** (separate browser profile or after signing out): overview, users, manage internships,
    search index status. Read-only unless a change is part of the script.

## 4. Running it locally

> **Current blocker on the development laptop (17 Nov 2026):** Windows Application Control blocks the
> FAISS native library (`faiss/_swigfaiss`). The backend imports FAISS at startup, so **the backend server
> (and its test suite) cannot start on this machine until that is resolved**. The frontend alone runs, but
> needs the backend for real data. Do not try to bypass Windows security; resolve it through the normal
> environment setup.

**Prerequisites (one-time, done by the project owner on the development environment)**

1. FAISS loads in the virtual environment: `.venv/Scripts/python.exe -c "import faiss"` prints nothing.
2. PostgreSQL has the **development database** `career_companion_dev`, migrated to the latest Alembic
   revision (the root README lists the migrations per phase).
3. The synthetic internships are imported and a **development FAISS index** is built from that database.
   No index folder exists yet. Use a dedicated folder for the dev index, for example
   `backend/data/faiss_index_dev`, and set `FAISS_INDEX_DIR` to it for both the build and the server (the
   commands are in the root README, §6a: `seed-internships`, then `rebuild-index`, each as a dry run first).
4. The embedding model is downloaded once (`python -m backend.manage download-embedding-model`, stored in
   `.models/`).
5. Demo accounts exist and are **already email-verified**: one student with a parsed synthetic resume and a
   match run, and one account with the admin role. Registration sends a real verification email through the
   SMTP settings in `.env`, so don't register live during the demo.
6. Node.js and `npm install` in `frontend/`.

**Environment configuration.** The backend reads `.env` but never overrides variables already set in the
shell, so the development database and index are selected without editing `.env`:

| Variable | Default | For the demo |
|---|---|---|
| `DB_NAME` | `career_companion` | `career_companion_dev` |
| `FAISS_INDEX_DIR` | `backend/data/faiss_index` | the dev index folder from step 3 |
| `APP_BASE_URL` | `http://127.0.0.1:8000` | `http://localhost:5173` (used in links inside emails) |
| `LLM_PROVIDER` | `none` | leave `none` for a predictable, AI-free demo |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `JWT_SECRET_KEY`, `SMTP_*`, `MAIL_FROM` | from `.env` | unchanged — never print or share them |
| `BACKEND_URL` (frontend dev proxy) | `http://127.0.0.1:8000` | unchanged |

**Start the backend** (Git Bash, from the project root):

```bash
DB_NAME=career_companion_dev FAISS_INDEX_DIR=backend/data/faiss_index_dev APP_BASE_URL=http://localhost:5173 \
  .venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In PowerShell, set the variables first:

```powershell
$env:DB_NAME = "career_companion_dev"; $env:FAISS_INDEX_DIR = "backend/data/faiss_index_dev"; $env:APP_BASE_URL = "http://localhost:5173"
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Start the frontend** (from `frontend/`):

```bash
npm install   # first time only
npm run dev
```

**Demo URLs**

- App: http://localhost:5173
- Backend health (through the frontend proxy): http://localhost:5173/health
- API docs (backend directly): http://127.0.0.1:8000/docs

**Before the demo:** check `/health`, sign in once with each demo account, confirm the demo student has a
parsed resume and a match run, and close unrelated tabs. Use only synthetic data: never real student
resumes, names, emails or phone numbers.

## 5. Deterministic behaviour and optional AI

| Area | Default (no AI) | Optional AI (only if a provider is configured and the user opts in) |
|---|---|---|
| Resume parsing, matching, skill gaps | Deterministic rules + local embeddings (`all-MiniLM-L6-v2`) | None |
| Tailored resume / cover letter | Fact-based assembly from resume facts | AI rewording, then every statement is fact-checked; unsupported ones are removed |
| Interview questions / feedback | Question bank + resume facts; rubric scoring | Up to 2 AI-tailored questions (fact-checked); AI coaching text added to the rubric score |
| Career assistant | Standard answers built from the student's data with sources | AI rewording of the answer's facts only; unverifiable sentences fall back to the standard answer |

AI is **off by default everywhere**. Each AI option shows the backend's privacy disclosure and needs an
explicit consent tick before anything is sent. Contact details are removed before sending. For a
predictable demo, keep AI off.

## 6. Explaining the RAG-based matching honestly

- **Retrieve:** the student's profile and all internships are embedded with `all-MiniLM-L6-v2`
  (384 dimensions). A FAISS index returns the nearest internships, combined with every internship that
  shares at least one skill with the student.
- **Ground:** each candidate is re-read from PostgreSQL, the single source of truth; the index stores
  only vectors.
- **Score and explain:** a transparent compatibility score — skills 50%, semantic similarity 20%,
  education 15%, location 15% — with matched/missing skills, a sentence per component and any caps
  (e.g. no required skill matched → at most 50). Missing data lowers, never inflates, the score.
- **No LLM in matching:** explanations are generated from the retrieved records, so companies,
  requirements and student facts are never invented.

## 7. Dataset and evaluation — what to say (and not say)

- The internship catalogue has **180 synthetic postings with invented companies**. It is not real
  job-market data.
- The matching system was evaluated with **10 synthetic candidate profiles** (fictional resumes parsed by
  the production parser): 9/9 system checks passed and 50/50 results were grounded in database records
  (`docs/assignment/EVALUATION_RESULTS.md`).
- This shows the system behaves correctly and transparently on synthetic data. It does **not** show
  real-world placement accuracy, and no claim of that should be made.
- Known findings from the evaluation: close scores can let location/education outrank a better role fit;
  skills mentioned only inside project text are not recognised; no GenAI/computer-vision postings;
  grades and awards are not scored; 10 postings have contradictory work mode and location.

## 8. Verification status (final integration, 17 Nov 2026)

| Check | Result |
|---|---|
| Frontend tests (Vitest + MSW, mocked API only), `npx vitest run --maxWorkers=4`, run twice | 356/356 and 356/356, no warnings |
| Same suite with default workers (11) on a battery-throttled laptop | 351/356 and 353/356: the failures are timeouts in sign-in/session-expiry redirect tests that pass alone and with 4 workers |
| Production build | Succeeds; main JS 344 kB (111 kB gzip) + 19 page chunks; no size warning |
| `npm audit` | 0 vulnerabilities |
| Browser journeys (scratch mock API, synthetic data) | Student: sign-in → dashboard → resume upload → discovery → semantic search → match → skill gap → documents → interview prep → track application → assistant → back to dashboard → sign out. Admin: overview, users, internships, edit form, index status, rebuild dialog opened and **cancelled**. Students blocked from admin pages and never download admin code |
| Responsive | 16 pages at 1440 / 768 / 375 px: no page-level horizontal overflow, no crashes |
| Backend test suite (`pytest`, isolated `career_companion_test` database) | **Not run**: Windows Application Control blocked the FAISS native library (`_swigfaiss`) when the test setup imported the app, so no backend test executed |
| Live run against the development database | **Not tested** (by decision): no account registration, real email, or dev-database writes were performed during frontend verification |

Run the frontend checks yourself (from `frontend/`): `npx vitest run --maxWorkers=4`, `npm run build`,
`npm audit`.

## 9. Known limitations (frontend and product)

- Reminders are **stored only**: no email, SMS or push notification is ever sent.
- Interview practice scores measure key-point coverage, not verified technical correctness.
- The assistant suggests next steps as links; it never performs actions itself.
- Admin: no user search, user details, account activation/deactivation, skill management, audit log or
  rebuild progress (the backend has no endpoints for them). The user list has no total, so it pages with
  Previous/Next.
- Not available in the UI although the backend supports them: change password, delete account, and the
  interview question preview.
- The app has only been run locally; it is not configured or hardened for public deployment.
