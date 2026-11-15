# AI Career Companion

A backend application that combines user management and resume parsing to support an AI-powered career assistance platform.

## Project Overview

AI Career Companion provides two core modules:

1. **User Management APIs** – Registration, authentication, email verification, password management, user profiles, and session management.
2. **Resume Parsing APIs** – PDF and DOCX resume uploads, structured information extraction, file storage, and retrieval of parsed resume data.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Database Migrations | Alembic |
| Validation | Pydantic |
| Authentication | JWT |
| Password Hashing | Argon2 |
| Email Service | Gmail SMTP |
| PDF Processing | pypdf |
| Embeddings | Sentence Transformers (`all-MiniLM-L6-v2`, local, CPU) |
| Vector Search | FAISS (`faiss-cpu`), rebuilt from PostgreSQL |
| DOCX Processing | python-docx |
| API Documentation | Swagger / OpenAPI |

## Project Structure

```text
AI_CAREER_COMPANION/
│
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── init_db.py
│   ├── manage.py
│   ├── data/
│   │   ├── behavioral_questions.json      (12 HR/behavioral questions)
│   │   ├── interview_misconceptions.json  (curated common wrong statements)
│   │   ├── interview_question_bank.json   (207 technical questions, 69 skills)
│   │   ├── internships.json      (180 fictional postings)
│   │   ├── learning_plans.json   (curated, versioned learning plans)
│   │   └── faiss_index/          (generated, gitignored)
│   ├── routes/
│   │   ├── admin.py
│   │   ├── auth.py
│   │   ├── documents.py
│   │   ├── internships.py
│   │   ├── interviews.py
│   │   ├── matches.py
│   │   ├── profiles.py
│   │   ├── skill_gaps.py
│   │   └── resumes.py
│   ├── schemas/
│   │   ├── document_schema.py
│   │   ├── internship_schema.py
│   │   ├── interview_schema.py
│   │   ├── match_schema.py
│   │   ├── skill_gap_schema.py
│   │   ├── user_schema.py
│   │   ├── profile_schema.py
│   │   └── resume_schema.py
│   ├── services/
│   │   ├── answer_evaluator.py
│   │   ├── ats.py
│   │   ├── candidate_profile.py
│   │   ├── compatibility.py
│   │   ├── cover_letter.py
│   │   ├── document_common.py
│   │   ├── document_renderer.py
│   │   ├── documents_service.py
│   │   ├── email_service.py
│   │   ├── embeddings.py
│   │   ├── fact_base.py
│   │   ├── fact_check.py
│   │   ├── llm/                  (base.py, groq_provider.py)
│   │   ├── internship_seed.py
│   │   ├── internship_text.py
│   │   ├── interview_generator.py
│   │   ├── interview_service.py
│   │   ├── learning_plans.py
│   │   ├── llm_privacy.py
│   │   ├── matching_agent.py
│   │   ├── question_bank.py
│   │   ├── resume_customizer.py
│   │   ├── resume_parser.py
│   │   ├── resume_skills.py
│   │   ├── skill_gap.py
│   │   ├── skill_normalizer.py
│   │   ├── skill_relations.py
│   │   └── vector_index.py
│   └── utils/
│       ├── security.py
│       ├── dependencies.py
│       ├── roles.py
│       └── tokens.py
│
├── docs/
│   ├── API_DOCUMENTATION.md
│   ├── DFD.md
│   └── SCHEMA_DESIGN.md
│
├── tests/
│   ├── conftest.py
│   └── test_*.py
│
├── migrations/
│   └── versions/
│
├── uploads/
│   └── resumes/
│
├── .models/                      (local embedding model, gitignored)
├── .env.example
├── .gitignore
├── alembic.ini
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Implementation Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Project hygiene: Git, CORS, resend verification, role-based authorization, test suite | ✅ Done |
| 1 | Module 2 completion: skill normalization, re-parse, delete, download | ✅ Implemented, 162/162 tests pass. Pending: apply migration `a1c4e2b7d9f0` and run `backfill-skills --apply` on the development database |
| 2 | Module 3: Internship knowledge base, FAISS index rebuilt from PostgreSQL | ✅ Implemented, 235/235 tests pass (incl. all 162 earlier tests). Pending on the development database: migration `b7e3d1f4a2c8` (after `a1c4e2b7d9f0`), `seed-internships --apply`, `rebuild-index --apply` |
| 3 | Module 4: Internship matching and compatibility scoring | ✅ Implemented and reviewed, 361/361 tests pass (incl. all 235 earlier tests). Pending on the development database: migration `c4f8a9e2b6d1` (after the Phase 1 and 2 migrations) |
| A | RAG internship-matching assignment: validation, 10-profile evaluation, documentation (`docs/assignment/`) | ✅ Evaluated: 9/9 system checks, 50/50 results grounded, 373/373 tests pass |
| 4 | Module 5: Skill gap analysis and recommendation | ✅ Implemented, 417/417 tests pass (incl. all 373 earlier tests). Pending on the development database: migration `d5a1c7e3f9b2` (after the Phase 1–3 migrations) |
| 5 | Module 6: Resume and cover letter customization (includes the provider-independent LLM service, Groq first) | ✅ Implemented, 489/489 tests pass (incl. all 417 earlier tests); LLM writing off by default. Pending on the development database: migration `e7b2d4f6a8c1` (after the Phase 1–4 migrations) |
| 6 | Module 7: Interview preparation | ✅ Implemented — see the Phase 6 report. Pending on the development database: migration `f3c9e1a5b7d2` (after the Phase 1–5 migrations) |
| 7 | Module 8: Application tracking | Planned |
| 8 | Module 9: Conversational career assistant | Planned |
| 9 | React + Vite frontend, full integration, final documentation | Planned |

Frontend requirement recorded for Phase 9: resume deletion is permanent, so the UI must ask for explicit confirmation before calling `DELETE /resumes/{resume_id}`.

## Features

### 1. User Management

- User registration with first name, last name, phone number, and email.
- Unique UUID assigned to each user.
- Role-based user identification.
- Secure password hashing using Argon2.
- Email verification.
- JWT access and refresh token authentication.
- Refresh token rotation and session management.
- Login and logout.
- Forgot password and password reset through email.
- Change password.
- Protected user profile operations.
- User account deletion.

### 2. Resume Parsing

- Upload PDF and DOCX resumes.
- File type and size validation.
- Extract text from PDF and DOCX documents.
- Extract personal information such as name, email, phone number, and address.
- Extract LinkedIn and GitHub information when available.
- Extract professional summary and skills.
- Identify technical skills and soft skills.
- Extract education, work experience, and internships.
- Extract projects, certifications, languages, and achievements.
- Store uploaded resumes and extracted information.
- Retrieve user-specific resume records.

## API Modules

### Authentication APIs

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register a user |
| GET | `/auth/verify-email` | Verify email |
| POST | `/auth/resend-verification` | Resend verification link |
| POST | `/auth/login` | Authenticate user |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/logout` | Revoke session |
| GET | `/auth/me` | Get current user |
| DELETE | `/auth/account` | Delete user account |
| POST | `/auth/forgot-password` | Request password reset |
| POST | `/auth/reset-password` | Reset password |
| POST | `/auth/change-password` | Change password |

### Resume APIs

| Method | Endpoint | Description |
|---|---|---|
| POST | `/resumes/upload` | Upload and parse a resume |
| GET | `/resumes/` | List current user's resumes |
| GET | `/resumes/{resume_id}` | Retrieve a resume, extracted data and normalized skills |
| GET | `/resumes/{resume_id}/skills` | List the resume's normalized skills |
| POST | `/resumes/{resume_id}/reparse` | Parse the stored file again (history is kept) |
| GET | `/resumes/{resume_id}/download` | Download the original file |
| DELETE | `/resumes/{resume_id}` | Permanently delete a resume and its file |

Skills are normalized to canonical names (for example `React.js` → `React`, `A WS` → `AWS`). Unknown skills are kept with category `other`.

To link skills to resumes uploaded before Phase 1, preview first, then apply:

```bash
python -m backend.manage backfill-skills
python -m backend.manage backfill-skills --apply
```

### Internship APIs (login required)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/internships/` | List active internships (filters: `q`, `domain`, `work_mode`, `location`, `skill`) |
| GET | `/internships/filters` | Available filter values |
| GET | `/internships/search?q=` | Semantic search over the FAISS index |
| GET | `/internships/{internship_id}` | Internship detail |
| POST / PATCH / DELETE | `/internships/...` | Admin only; DELETE deactivates (soft delete) |
| GET | `/admin/index/status` | Admin: search index status |
| POST | `/admin/index/rebuild` | Admin: rebuild index from PostgreSQL |

### Matching APIs (login required, own resumes only)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/matches/resumes/{resume_id}` | Rank internships for a resume (`k`, `work_mode`, `location`) |
| GET | `/matches/resumes/{resume_id}` | Latest matching run |
| GET | `/matches/resumes/{resume_id}/history` | Past runs |
| GET | `/matches/runs/{run_id}` | One run |
| GET | `/matches/resumes/{resume_id}/internships/{internship_id}` | Compatibility with one internship |

Scores are 0–100: skills 50%, semantic similarity 20%, education 15%, location 15%, with explanations, matched/missing skills and a data-completeness indicator. See `docs/API_DOCUMENTATION.md` section 6B.

### Skill Gap APIs (login required, own data only)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/skill-gaps/resumes/{resume_id}/internships/{internship_id}` | Matched, partially matched and missing skills for one internship, with learning plans |
| POST | `/skill-gaps/resumes/{resume_id}` | Prioritised recommendations from the latest match run or selected internships |
| GET | `/skill-gaps` | Your recommendations (filters: `resume_id`, `status`, `current_only`) |
| PATCH | `/skill-gaps/{recommendation_id}` | Progress: `pending`, `in_progress`, `completed`, `dismissed` |

Skills that appear on a re-parsed resume complete their recommendations automatically. Learning plans are curated in `backend/data/learning_plans.json` and contain no external links. See `docs/API_DOCUMENTATION.md` section 6C.

### Resume and Cover Letter APIs (login required, own data only)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/documents/llm-status` | AI-writing availability and privacy disclosure |
| GET | `/documents/resumes/{resume_id}/internships/{internship_id}/ats-report` | ATS keyword coverage and checks |
| POST | `/documents/resume` | Internship-specific resume |
| POST | `/documents/cover-letter` | Cover letter |
| GET / PATCH / DELETE | `/documents/{id}` | View, edit (new version), delete |
| GET | `/documents/{id}/versions` | Version history; `POST .../versions/{v}/restore` restores |
| GET | `/documents/{id}/download?format=docx\|txt` | Download |

Generation is deterministic by default and uses only facts from the student's own resume and profile. Optional Groq-based writing is off unless configured and must be opted into per document. Name and contact details are never sent: every AI request is scrubbed of name parts, contact details, addresses and PIN codes, then checked again before anything is sent. Every generated statement is fact-checked. See `docs/API_DOCUMENTATION.md` section 6D.

### Interview Preparation APIs (login required, own data only)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/interviews/question-bank/version` | Question bank versions and coverage |
| GET | `/interviews/questions/preview` | Preview a question set |
| POST / GET | `/interviews/sessions` | Start a practice or mock interview / history |
| GET / DELETE | `/interviews/sessions/{id}` | Session detail / delete |
| POST | `/interviews/sessions/{id}/questions/{qid}/answers` | Answer (with retries) and get feedback |
| GET | `/interviews/sessions/{id}/questions/{qid}/answers` | All attempts for a question |
| POST | `/interviews/sessions/{id}/questions/{qid}/reveal` | Reveal the suggested answer (mock mode) |
| POST | `/interviews/sessions/{id}/complete` | Finish and get the summary |
| GET | `/interviews/progress` | Progress over time |

Questions come from a curated bank: 207 technical questions covering all 69 dataset skills, plus 12 behavioral. Project questions are grounded in the student's own resume facts and internship questions in the internship record. Answers are scored with deterministic rubrics and optional local semantic matching (calibrated against vague and off-topic answers). Technical scores measure **key-point coverage, not verified correctness**. Curated checks for common wrong statements (143 questions across 61 skills), "I don't know" detection, keyword-list detection and a STAR story check stop inflated scores. AI feedback is opt-in per answer: names, contact details, addresses and PIN codes are removed before anything is sent, and a final check blocks the request if any remain. See `docs/API_DOCUMENTATION.md` section 6E.

### Profile APIs

| Method | Endpoint | Description |
|---|---|---|
| POST | `/profiles/` | Create current user's profile |
| GET | `/profiles/me` | Get current user's profile |
| PATCH | `/profiles/me` | Update current user's profile |

### Administration APIs (admin role)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/admin/users` | List users |
| PATCH | `/admin/users/{user_id}/role` | Change a user's role |

Create the first administrator from the command line:

```bash
python -m backend.manage set-role admin@example.com admin
```

## Installation and Setup

### Prerequisites

- Python 3.13
- PostgreSQL 17
- Git

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd AI_CAREER_COMPANION
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example configuration:

```powershell
Copy-Item .env.example .env
```

Update `.env` with your own configuration:

- PostgreSQL credentials.
- A strong JWT secret key.
- Gmail SMTP username.
- Gmail App Password.
- Application base URL.
- Allowed frontend origins (`CORS_ORIGINS`).
- Test database name (`TEST_DB_NAME`, must end with `_test`).

Do not commit `.env` or expose credentials publicly.

### 5. Configure PostgreSQL

Create a PostgreSQL database named:

```text
career_companion
```

Update the database connection details in `.env`.

For a fresh database, initialize the tables using:

```bash
python -m backend.init_db
```

Then mark the current migration history as applied:

```bash
python -m alembic stamp head
```

For an existing database that already has the migration baseline and schema, apply pending migrations using:

```bash
python -m alembic upgrade head
```

Do not run both setup paths on the same database without checking its current migration state.

### 6. Start the application

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 6a. Internship knowledge base and search index

PostgreSQL is the single source of truth for internships. The FAISS index stores only vectors and is rebuilt from PostgreSQL.

```bash
# One-time download of the pinned embedding model (~92 MB, safetensors only)
python -m backend.manage download-embedding-model

# Validate the bundled dataset (180 fictional postings; no database access)
python -m backend.manage validate-internships

# Import internships: dry run first, then apply
python -m backend.manage seed-internships
python -m backend.manage seed-internships --apply

# Build the search index: dry run first, then apply
python -m backend.manage rebuild-index
python -m backend.manage rebuild-index --apply

python -m backend.manage index-status
```

After the one-time download the model is loaded from `.models/` only (no network access) and only when first needed, never at API startup. `backend/data/internships.json` comes from the Milestone 2 reference project (SHA-256 `402a37cd…6fc1317`); its supplied pickle/FAISS files are not used.

### 7. Run the tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Tests use a separate PostgreSQL database (`career_companion_test` by default), which is created automatically and rebuilt on every run. They never modify the development database, never send real email and never write to `uploads/`.

## API Documentation

Once the application is running, open:

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

Use Swagger UI to explore endpoints, provide request data, authenticate, and execute API requests.

## Documentation

Additional project documentation is available in the `docs/` directory:

- `API_DOCUMENTATION.md` – Endpoint reference.
- `DFD.md` – Data Flow Diagram.
- `SCHEMA_DESIGN.md` – Database schema design.
- `assignment/` – RAG internship-matching assignment: report, architecture, methodology, test cases and actual evaluation results (reproduce with `python -m evaluation.rag_evaluation`, which uses the test database only).

## Security Considerations

- Role-based authorization (`student`, `admin`) protects administrative endpoints.
- CORS only admits the origins listed in `CORS_ORIGINS`.
- Verification-link resends are throttled and do not reveal whether an account exists.
- Generated resumes and cover letters contain only facts from the student's own resume and profile; every AI-generated statement is fact-checked and unsupported ones are replaced.
- Optional AI writing never receives name, e-mail, phone, links or location, requires explicit per-document consent, and never logs API keys or resume content.
- Semantic search results are always re-checked against PostgreSQL; inactive or deleted internships are never returned.
- Index rebuilds run one at a time and are swapped in atomically; index files are verified by SHA-256 before loading.
- No pickle files are downloaded or loaded (model weights are safetensors; the index is native FAISS format).

- Passwords are stored as Argon2 hashes.
- JWT access tokens have limited validity.
- Refresh tokens are stored as hashes and rotated.
- Authentication sessions can be revoked.
- Email verification is required before login.
- Password reset tokens are stored as hashes and expire.
- Resume records are scoped to their owning users.
- Uploaded files are validated before processing.
- Environment variables and private uploads must not be committed to Git.

## Current Scope and Limitations

Resume parsing uses text extraction and rule-based parsing. Extraction accuracy can vary depending on document formatting and layout. Scanned documents requiring OCR are not currently supported.

## License

This project is developed as part of an academic and technical assignment.
