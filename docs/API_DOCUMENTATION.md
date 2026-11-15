# AI Career Companion – API Documentation

## 1. Overview

AI Career Companion provides REST APIs for user management, authentication, profile management, and resume parsing.

**Base URL:** `http://127.0.0.1:8000`

**API format:** JSON, except resume uploads, which use multipart form data.

**Interactive documentation:** `/docs`

## 2. Authentication

Protected endpoints use JWT Bearer authentication.

Add the access token to the request header:

```http
Authorization: Bearer <access_token>
```

The application uses:
- Access tokens with a 15-minute validity period.
- Refresh tokens with a 30-day validity period.
- Refresh token rotation.
- Database-backed session validation and revocation.

Use the latest access token after refreshing the session.

### Roles

Every user has a `role`. New users are `student`. Endpoints under `/admin` require the `admin` role and return `403 Forbidden` for other users. Tokens belonging to unverified accounts are rejected with `403`.

Bootstrap the first administrator from the command line:

```bash
python -m backend.manage set-role admin@example.com admin
```

### CORS

Browser origins allowed to call the API are configured with `CORS_ORIGINS` (comma-separated) in `.env`. The default allows the Vite dev server at `http://localhost:5173` and `http://127.0.0.1:5173`. Wildcard `*` is rejected at startup.

## 3. User Management APIs

### 3.1 Register User

**Endpoint:** `POST /auth/register`

Registers a new user and initiates email verification.

Request:

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "9999999999",
  "email": "student@example.com",
  "password": "StrongPass123"
}
```

Required fields:
- `first_name`: String, 1–100 characters.
- `last_name`: String, 1–100 characters.
- `phone_number`: String, 7–20 characters.
- `email`: Valid email address.
- `password`: String, 8–128 characters.

**Success:** `201 Created`

Response model: `UserResponse`

Includes user ID, UUID, name, phone number, email, role, verification status (`is_verified`), and creation timestamp. Password information is not returned.

If the verification email cannot be sent, the account is still created and the API returns `503`. The user can request a new link with `POST /auth/resend-verification`.

### 3.2 Verify Email

**Endpoint:** `GET /auth/verify-email`

Verifies the user's email address using the verification token sent by email.

Query parameter:

```text
token=<verification_token>
```

**Success:** `200 OK`

The verification token is single-use and valid for 24 hours.

### 3.2.1 Resend Verification Email

**Endpoint:** `POST /auth/resend-verification`

Sends a new verification link to an account that has not been verified yet.

Request:

```json
{
  "email": "student@example.com"
}
```

**Success:** `200 OK`

Behaviour:
- The response is identical for unknown, verified and unverified emails, so the endpoint cannot be used to discover accounts.
- Issuing a new link invalidates all earlier unused links for that account.
- Requests within 60 seconds of the previous link are accepted but no new email is sent.
- If email delivery fails, the new link is disabled immediately.

### 3.3 Login User

**Endpoint:** `POST /auth/login`

Authenticates a verified user.

Request:

```json
{
  "email": "student@example.com",
  "password": "StrongPass123"
}
```

**Success:** `200 OK`

Response model: `TokenResponse`

```json
{
  "access_token": "<access_token>",
  "refresh_token": "<refresh_token>",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_expires_in": 2592000
}
```

Token expiry values are expressed in seconds.

### 3.4 Refresh Access Token

**Endpoint:** `POST /auth/refresh`

Uses a refresh token to obtain a new access token and rotated refresh token.

Request:

```json
{
  "refresh_token": "<refresh_token>"
}
```

**Success:** `200 OK`

Response model: `TokenResponse`

### 3.5 Logout User

**Endpoint:** `POST /auth/logout`

Revokes the session associated with the supplied refresh token.

Request:

```json
{
  "refresh_token": "<refresh_token>"
}
```

**Success:** `200 OK`

The revoked session can no longer be used to authenticate.

### 3.6 Get Logged-In User

**Endpoint:** `GET /auth/me`

Returns the currently authenticated user's information.

Authentication: Required.

**Success:** `200 OK`

Response model: `UserResponse`

### 3.7 Delete User Account

**Endpoint:** `DELETE /auth/account`

Deletes the authenticated user's account after password confirmation.

Authentication: Required.

Request:

```json
{
  "current_password": "StrongPass123"
}
```

**Success:** `204 No Content`

### 3.8 Forgot Password

**Endpoint:** `POST /auth/forgot-password`

Requests a password reset email.

Request:

```json
{
  "email": "student@example.com"
}
```

**Success:** `200 OK`

The response is designed to avoid revealing whether an email address is registered.

### 3.9 Reset Password

**Endpoint:** `POST /auth/reset-password`

Resets the password using the reset token received through email.

Request:

```json
{
  "token": "<password_reset_token>",
  "new_password": "NewStrongPass123"
}
```

Validation:
- Token: 20–256 characters.
- New password: 8–128 characters.

**Success:** `200 OK`

Reset tokens are single-use and expire after 30 minutes.

### 3.10 Change Password

**Endpoint:** `POST /auth/change-password`

Changes the password of the authenticated user.

Authentication: Required.

Request:

```json
{
  "current_password": "StrongPass123",
  "new_password": "NewStrongPass123"
}
```

**Success:** `200 OK`

The current password must be valid. Other active sessions are revoked after a successful password change.

## 4. User Profile APIs

All profile endpoints require Bearer authentication.

### 4.1 Create Profile

**Endpoint:** `POST /profiles/`

Creates an educational and personal profile for the authenticated user.

Request:

```json
{
  "college": "Example Engineering College",
  "degree": "B.Tech Computer Science",
  "graduation_year": 2027,
  "location": "Vijayawada"
}
```

Fields are optional and nullable:
- `college`: String, maximum 200 characters.
- `degree`: String, maximum 150 characters.
- `graduation_year`: Integer, 1900–2100.
- `location`: String, maximum 150 characters.

**Success:** `201 Created`

Response model: `ProfileResponse`

### 4.2 Get Profile

**Endpoint:** `GET /profiles/me`

Retrieves the authenticated user's profile.

**Success:** `200 OK`

Response model: `ProfileResponse`

### 4.3 Update Profile

**Endpoint:** `PATCH /profiles/me`

Updates the authenticated user's profile.

Request:

```json
{
  "college": "Updated Engineering College",
  "degree": "B.Tech Data Science",
  "graduation_year": 2027,
  "location": "Vijayawada"
}
```

**Success:** `200 OK`

Response model: `ProfileResponse`

## 5. Resume Parsing APIs

All resume endpoints require Bearer authentication.

### 5.1 Upload and Parse Resume

**Endpoint:** `POST /resumes/upload`

Uploads and parses a resume document.

Content type: `multipart/form-data`

Form field:

```text
file: Select a PDF or DOCX resume
```

Supported file formats:
- PDF
- DOCX

Maximum file size: 5 MB.

**Success:** `201 Created`

Response model: `ResumeUploadResponse`

The response includes:
- Resume ID.
- Original filename.
- File type.
- Processing status.
- Upload timestamp.
- Extracted resume information.

### 5.2 Get User Resumes

**Endpoint:** `GET /resumes/`

Retrieves the resumes belonging to the authenticated user.

**Success:** `200 OK`

Response: Array of `ResumeListItem` objects.

Each item includes:
- `resume_id`
- `filename`
- `file_type`
- `status`
- `uploaded_at`

### 5.3 Get Resume Details

**Endpoint:** `GET /resumes/{resume_id}`

Retrieves a specific resume and its extracted information.

Path parameter:
- `resume_id`: Integer resume identifier.

**Success:** `200 OK`

Response model: `ResumeDetailResponse`

The endpoint returns the resume metadata, `extracted_data` from the latest **successful** extraction, and `normalized_skills`.

### 5.4 Normalized Skills

Upload and detail responses include an additional field, `normalized_skills` (all earlier fields are unchanged):

```json
"normalized_skills": [
  { "skill_id": 3, "name": "React", "category": "framework", "source": "technical_skills" },
  { "skill_id": 9, "name": "Antigravity", "category": "other", "source": "technical_skills" }
]
```

Normalization rules:
- Known skills and aliases map to one canonical name (`React.js` → `React`, `sklearn` → `Scikit-learn`).
- Matching ignores case, spaces and separators, which repairs PDF spacing such as `A WS` → `AWS`.
- Proficiency words and labels (`Basic`, `Skills`) are dropped.
- Unknown skills are kept with category `other`.
- `source` is the parser section the skill came from.

**Endpoint:** `GET /resumes/{resume_id}/skills`

Returns `{ "resume_id": 1, "skills": [ ...NormalizedSkillItem ] }`.

### 5.5 Re-parse Resume

**Endpoint:** `POST /resumes/{resume_id}/reparse`

Parses the stored file again and re-links its skills.

**Success:** `200 OK`. Response: `ResumeDetailResponse`.

- Every attempt adds a new row to `resume_extractions`; earlier extractions are never modified or deleted.
- A failed attempt is stored with `status = "failed"` and an error message, returns `422`, and the last successful data stays in use.
- `404` if the stored file is missing.

### 5.6 Download Resume

**Endpoint:** `GET /resumes/{resume_id}/download`

Returns the original file as an attachment with its original filename (`Content-Type` is `application/pdf` or the DOCX type).

The server rebuilds the file location from the owner's ID and the server-generated filename only, so a stored path can never point outside the upload directory.

### 5.7 Delete Resume

**Endpoint:** `DELETE /resumes/{resume_id}`

**Success:** `204 No Content`.

Deletion is **permanent**. It removes the resume, all its extractions, its skill links and match results, then the stored file. Shared skill records are never deleted. Generated documents that referenced the resume are kept with the reference cleared.

Clients must ask the user for explicit confirmation before calling this endpoint.

All resume endpoints return `404` for resumes owned by another user.

## 6. Resume Extraction Response Structure

The `ResumeParsedData` model contains the following fields:

| Field | Type |
|---|---|
| full_name | String or null |
| email | String or null |
| phone | String or null |
| address | String or null |
| linkedin | String or null |
| github | String or null |
| professional_summary | String or null |
| skills | Array of strings |
| technical_skills | Array of strings |
| soft_skills | Array of strings |
| education | Array of objects |
| work_experience | Array of objects |
| projects | Array of objects |
| certifications | Array of strings |
| internships | Array of objects |
| languages | Array of strings |
| achievements | Array of strings |

Extraction results depend on the resume's content and formatting. Fields may be null or contain empty arrays when information is not found.

## 6A. Internship APIs

All internship endpoints require login. Deactivated internships are visible only to administrators.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/internships/` | User | List active internships |
| GET | `/internships/filters` | User | Distinct domains, work modes and locations |
| GET | `/internships/search?q=&k=` | User | Semantic search |
| GET | `/internships/{internship_id}` | User | Internship detail |
| POST | `/internships/` | Admin | Create an internship |
| PATCH | `/internships/{internship_id}` | Admin | Update an internship |
| DELETE | `/internships/{internship_id}` | Admin | Deactivate (soft delete) |

### 6A.1 List Internships

Query parameters (all optional): `q` (text in title, company or description), `domain`, `work_mode` (`Onsite`, `Hybrid`, `Remote`; case-insensitive), `location` (partial match), `skill` (canonical skill name, case-insensitive), `include_inactive` (admins only), `skip` (default 0), `limit` (default 20, max 100).

Response:

```json
{
  "total": 180,
  "skip": 0,
  "limit": 20,
  "items": [
    {
      "internship_id": 1,
      "title": "Application Security Intern",
      "company": "Basecrest Ventures Inc",
      "domain": "Cybersecurity",
      "work_mode": "Onsite",
      "location": "Pune, India",
      "duration_weeks": 10,
      "stipend_per_month": 8000,
      "stipend_currency": "INR",
      "min_education": "Pursuing M.Tech/M.E.",
      "required_skills": ["Linux", "Networking", "Problem Solving", "SQL"],
      "preferred_skills": ["AWS", "Docker"],
      "skills": [{ "skill_id": 1, "name": "Linux", "category": "cloud_devops", "importance": "required" }],
      "source": "dataset",
      "is_active": true
    }
  ]
}
```

### 6A.2 Semantic Search

**Endpoint:** `GET /internships/search?q=python backend developer&k=10`

- `q`: 2–500 characters. `k`: 1–50 (default 10).
- Returns `results` ordered by `similarity` (cosine similarity, higher is closer) and `index_built_at`.
- Results are always re-checked against PostgreSQL: inactive or deleted internships are never returned, even if the index is outdated.
- `503` if the index has not been built, was built with a different embedding model, fails its integrity check, or the embedding model has not been downloaded.

### 6A.3 Admin: Create, Update, Deactivate

Create body:

```json
{
  "title": "Backend Engineering Intern",
  "company": "Example Labs",
  "description": "Build REST APIs with FastAPI and PostgreSQL.",
  "location": "Bengaluru, India",
  "application_url": "https://example.com/apply",
  "domain": "Software Development",
  "work_mode": "Hybrid",
  "duration_weeks": 12,
  "stipend_per_month": 15000,
  "stipend_currency": "INR",
  "min_education": "Pursuing B.Tech/B.E.",
  "required_skills": ["Python", "FastAPI"],
  "preferred_skills": ["Docker"]
}
```

- Skills are normalized with the same rules as resumes; unknown skills are kept with category `other`.
- Validation: `work_mode` must be `Onsite`, `Hybrid` or `Remote`; `duration_weeks` 1–104; `stipend_per_month` 0–1,000,000; `stipend_currency` three capital letters; `application_url` must be http(s).
- `PATCH` updates only the supplied fields; skill lists, when supplied, replace the existing ones.
- `DELETE` sets `is_active = false` (`204`). The record is kept because applications and matches may refer to it.
- Create, update and deactivate mark the index as stale; run a rebuild to refresh search.

## 6B. Internship Matching APIs

All endpoints require login and only work on the caller's own resumes (other resumes return `404`).

| Method | Endpoint | Description |
|---|---|---|
| POST | `/matches/resumes/{resume_id}?k=10&work_mode=&location=` | Run matching, save the run, return ranked results (`201`) |
| GET | `/matches/resumes/{resume_id}` | Latest run (`404` if none yet) |
| GET | `/matches/resumes/{resume_id}/history` | All runs, newest first |
| GET | `/matches/runs/{run_id}` | One run |
| GET | `/matches/resumes/{resume_id}/internships/{internship_id}` | Score one active internship on demand (not saved) |

Parameters: `k` 1–50 (default 10); `work_mode` `Onsite` / `Hybrid` / `Remote`; `location` (2–150 characters) overrides the profile location for this request. `422` if the resume has no recognised skills; `409` if the resume is deleted while matching runs. The single-internship endpoint returns `404` for inactive or past-deadline internships.

Each run is saved in one transaction, so a run is either stored completely or not at all; concurrent requests create separate runs. Stored runs are history: they keep showing internships that were later deactivated (with `is_active: false`).

### 6B.1 How candidates are chosen

FAISS nearest neighbours of the resume (at least 50) **plus** every active internship that shares a skill with the resume. Each candidate is re-checked in PostgreSQL: inactive internships and internships whose deadline has passed are excluded.

### 6B.2 Score (algorithm v1)

`score = 100 × (0.50·skills + 0.20·semantic + 0.15·education + 0.15·location)`, rounded to one decimal and always within 0–100.

| Component | Rule |
|---|---|
| Skills | 0.8 × required coverage + 0.2 × preferred coverage; required only → required coverage; preferred only → 0.8 × preferred coverage (max 0.8); no skills listed → 0.5 (`not_stated`) |
| Semantic | `clamp((cosine − 0.40) / 0.35, 0, 1)`; calibrated on the 180 postings (median unrelated pair → 0.08, median related pair → 0.63) |
| Education | Degree **family and level** must fit: exact fit 1.0; non-CS branch where CS is preferred 0.85; any-bachelor: master 0.8 / diploma 0.2; higher level 0.7; related computing degree 0.6; right degree, other subject 0.5; lower level 0.3; unrelated field 0.1 |
| Location | Remote 1.0; same city 1.0 (aliases such as Bangalore = Bengaluru); hybrid elsewhere 0.3; onsite elsewhere 0.0 |

Missing information: student data unknown → 0.3 (`unknown`); posting does not state it → 0.5 (`not_stated`); semantic index/model unavailable, or the internship not yet indexed → 0.3 (`unavailable`, with the reason in `detail`). Weights are **not** redistributed when a component is missing: each keeps its weight with the conservative value, so missing data never inflates a score.

`score_before_caps` is the sum of the components' `weighted` values; `score` equals it rounded to one decimal, unless a cap applied.

Caps: no required skill matched → score ≤ 50; posting lists no skills → label ≤ Fair; any component not assessed → label ≤ Strong.

Labels: Excellent ≥ 80, Strong ≥ 65, Fair ≥ 45, Weak < 45. Ties are broken by required-skill coverage, then internship ID.

### 6B.3 Result item

```json
{
  "rank": 1,
  "score": 78.2,
  "label": "Strong",
  "algorithm_version": "v1",
  "score_before_caps": 78.2,
  "data_completeness": 1.0,
  "required_skill_coverage": 0.75,
  "components": [
    { "name": "skills", "score": 0.7, "weight": 0.5, "weighted": 35.0, "status": "assessed",
      "detail": "You have 3 of 4 required skills (Python, SQL, Git). Missing: Docker. ..." },
    { "name": "semantic", "score": 0.66, "weight": 0.2, "weighted": 13.2, "status": "assessed", "detail": "..." },
    { "name": "education", "score": 1.0, "weight": 0.15, "weighted": 15.0, "status": "assessed", "detail": "..." },
    { "name": "location", "score": 1.0, "weight": 0.15, "weighted": 15.0, "status": "assessed", "detail": "..." }
  ],
  "matched_required_skills": ["Python", "SQL", "Git"],
  "missing_required_skills": ["Docker"],
  "matched_preferred_skills": ["AWS"],
  "missing_preferred_skills": ["Linux"],
  "missing_information": [],
  "caps_applied": [],
  "explanation": ["..."],
  "internship": { "internship_id": 12, "title": "...", "company": "..." }
}
```

Every item always contains all four components in the same order. Explanations use skills, degree category and the posting's location only; no names, emails or phone numbers.

## 6C. Skill Gap Analysis APIs

All endpoints require login and only work on the caller's own resumes and recommendations (others return `404`). Administrators have no extra access to students' recommendations.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/skill-gaps/resumes/{resume_id}/internships/{internship_id}` | Analyse one internship (read-only) |
| POST | `/skill-gaps/resumes/{resume_id}` | Generate or refresh saved recommendations (`201`) |
| GET | `/skill-gaps` | List your recommendations |
| PATCH | `/skill-gaps/{recommendation_id}` | Update progress status |

### 6C.1 Skill classification

Every required and preferred skill of an internship is classified as:
- `matched`: the resume has it.
- `partial`: missing, but the resume has a closely related canonical skill, from a curated list (for example MySQL for PostgreSQL, PyTorch for TensorFlow, AWS for Azure). The reason is returned in `related_skills`.
- `missing`: neither.

Partial matches are reported here only. They do **not** change Phase 3 compatibility scores.

### 6C.2 Analyse one internship

`GET /skill-gaps/resumes/{resume_id}/internships/{internship_id}` returns:
- `summary` counts
- `matched`, `partial` and `missing` skills
- `learning_order`: gap skills with prerequisites first
- `learning_plans`: a curated plan for each gap skill

Returns `404` for an inactive or past-deadline internship. Nothing is saved.

### 6C.3 Generate recommendations

`POST /skill-gaps/resumes/{resume_id}` with an optional body:

```json
{ "internship_ids": [12, 40, 77] }
```
or
```json
{ "run_id": "<match run id>", "top_k": 5 }
```

With an empty body, the top 5 results of the resume's latest matching run are used. Rules:
- `internship_ids`: 1–20 unique IDs; it cannot be combined with `run_id`.
- `top_k`: 1–20.

Errors:
- `409`: no matching run yet, or none of the run's internships is still available.
- `404`: an unknown or unavailable internship, or a run that belongs to another resume.
- `422`: the resume has no recognised skills, or the request is invalid.

Priority (algorithm `gap-v1`):

```
priority = 100 × Σ(importance × relevance × partial) / Σ relevance
```

- `importance`: required 1.0, preferred 0.5
- `relevance`: the internship's compatibility score ÷ 100, read-only from Phase 3
- `partial`: 0.5 for a partially matched skill, 1.0 otherwise

A required, fully missing skill needed by every analysed internship scores 100. Ties are broken by required count, then demand, then name.

The response contains:
- the analysed internships with their `relevance`
- `skipped_internship_ids`: run results that are no longer available
- `newly_acquired_skills`
- `learning_order`
- `recommendations`, ordered by priority

Regenerating updates existing rows and keeps their progress status. Skills that are no longer gaps are kept with `is_current: false`.

### 6C.4 List and progress

`GET /skill-gaps?resume_id=&status=&current_only=true`. The `status` filter accepts `pending`, `in_progress`, `completed` or `dismissed`.

`PATCH /skill-gaps/{recommendation_id}` with body `{ "status": "in_progress" }`:

| New status | Effect |
|---|---|
| `in_progress` | Sets `started_at` |
| `completed` | Sets `completed_at` and `completed_via = "user"` |
| `pending` | Clears the timestamps |
| `dismissed` | Clears the completion fields |

**Automatic detection:** when a resume is re-parsed (`POST /resumes/{id}/reparse`) and a recommended skill now appears on it, the open recommendation is set to `completed` with `completed_via = "resume"`.

### 6C.5 Learning plans

Curated plans live in `backend/data/learning_plans.json` (version `2026.11-v1`) and cover all 69 dataset skills. Each plan has:
- a level and approximate study hours
- prerequisites, given as canonical skill names
- a topic outline

Plans contain no external links or named courses. A skill without a curated plan gets a generic outline marked `curated: false`.

## 7. Administration APIs

All endpoints require an access token for a user with the `admin` role.

### 7.1 List Users

**Endpoint:** `GET /admin/users`

Query parameters: `skip` (default 0), `limit` (default 50, max 200).

**Success:** `200 OK`. Response: array of `UserResponse`.

### 7.2 Change User Role

**Endpoint:** `PATCH /admin/users/{user_id}/role`

Request:

```json
{
  "role": "admin"
}
```

Allowed roles: `student`, `admin`.

**Success:** `200 OK`. Response: `UserResponse`.

Errors: `400` if an admin tries to remove their own admin role, `404` if the user does not exist, `422` for an unknown role.

### 7.3 Search Index Status

**Endpoint:** `GET /admin/index/status`

Returns `built`, `built_at`, `model_name`, `model_revision`, `dimension`, `indexed_vectors`, `configured_model`, `model_matches_configuration`, `active_internships`, `document_status_counts` and `stale`.

`stale` is `true` when no index exists, the model differs from the configuration, any document is `pending` or `failed`, or the index holds vectors for internships that are no longer active.

### 7.4 Rebuild Search Index

**Endpoint:** `POST /admin/index/rebuild`

Rebuilds the FAISS index from the active internships in PostgreSQL.

**Success:** `200 OK` with `indexed`, `deactivated_documents`, `built_at`, `model_name`, `dimension`.

- Only one rebuild runs at a time (PostgreSQL advisory lock); a concurrent request returns `409 Conflict`.
- The new index is written to a new file and swapped in atomically; searches keep using the previous index until the swap.
- `503` if the embedding model has not been downloaded.

## 8. System APIs

### 8.1 Home

**Endpoint:** `GET /`

Returns the application's home response.

**Success:** `200 OK`

### 8.2 Health Check

**Endpoint:** `GET /health`

Checks whether the application is responding.

**Success:** `200 OK`

## 9. HTTP Status Codes

| Status Code | Meaning |
|---|---|
| 200 | Request completed successfully |
| 201 | Resource created successfully |
| 204 | Request completed without a response body |
| 400 | Invalid request or business-rule violation |
| 401 | Missing, invalid, expired or revoked token |
| 403 | Authenticated but not allowed (wrong role or unverified email) |
| 404 | Resource not found or not owned by the user |
| 409 | Conflict, such as an already registered email |
| 413 / 415 | Uploaded file too large / unsupported type |
| 422 | Request validation error |
| 503 | Dependent service (database or email) unavailable |

Other runtime errors may be returned by individual route handlers for authentication, authorization, missing resources, invalid files, and business-rule violations.

## 10. Validation and Security

- Input validation is handled through Pydantic schemas.
- Passwords are hashed using Argon2.
- Access tokens are signed JWTs.
- Refresh tokens are securely generated and stored as hashes.
- Email verification is required before login.
- Password reset tokens are securely stored as hashes.
- Password reset tokens expire and cannot be reused.
- Database-backed sessions support token revocation.
- Resume operations are restricted to the authenticated owner.
- Uploaded files are validated before extraction.
- Role-based authorization protects administrative endpoints.
- CORS only admits explicitly listed origins.
- Environment secrets must remain in `.env` and must not be committed to Git.

## 11. API Testing

### Automated tests

The test suite runs against a separate database (`TEST_DB_NAME`, default `career_companion_test`, created automatically). It never touches the development database, never sends real email and never writes to `uploads/`.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

### Manual testing

Start the backend:

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

The OpenAPI specification is available at:

```text
http://127.0.0.1:8000/openapi.json
```

Use Swagger UI to inspect request schemas, authenticate, upload documents, and execute API operations.

## 12. Related Documentation

- `README.md` – Project overview and setup.
- `DFD.md` – Data Flow Diagram.
- `SCHEMA_DESIGN.md` – Database schema design.

