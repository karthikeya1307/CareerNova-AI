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
│   ├── routes/
│   │   ├── admin.py
│   │   ├── auth.py
│   │   ├── profiles.py
│   │   └── resumes.py
│   ├── schemas/
│   │   ├── user_schema.py
│   │   ├── profile_schema.py
│   │   └── resume_schema.py
│   ├── services/
│   │   ├── email_service.py
│   │   └── resume_parser.py
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
| 2 | Module 3: Internship knowledge base, FAISS index rebuilt from PostgreSQL | Planned |
| 3 | Module 4: Internship matching | Planned |
| 4 | Module 5: Skill gap analysis | Planned |
| 5 | Module 8: Application tracking | Planned |
| 6 | Provider-independent LLM service (Groq first) | Planned |
| 7 | Module 6: Resume and cover letter generation | Planned |
| 8 | Module 7: Interview preparation | Planned |
| 9 | Module 9: Conversational career assistant | Planned |
| 10 | React + Vite frontend, final documentation | Planned |

Frontend requirement recorded for Phase 10: resume deletion is permanent, so the UI must ask for explicit confirmation before calling `DELETE /resumes/{resume_id}`.

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

## Security Considerations

- Role-based authorization (`student`, `admin`) protects administrative endpoints.
- CORS only admits the origins listed in `CORS_ORIGINS`.
- Verification-link resends are throttled and do not reveal whether an account exists.

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
