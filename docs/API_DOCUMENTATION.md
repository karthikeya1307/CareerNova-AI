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

## 6D. Resume and Cover Letter Customization APIs

All endpoints require login; documents, resumes and versions of other users return `404`. Inactive or past-deadline internships return `404`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/documents/llm-status` | Whether AI-assisted writing is configured, plus the privacy disclosure to show |
| GET | `/documents/resumes/{resume_id}/internships/{internship_id}/ats-report` | ATS keyword and format report (read-only) |
| POST | `/documents/resume` | Create an internship-specific resume (`201`) |
| POST | `/documents/cover-letter` | Create a cover letter (`201`) |
| GET | `/documents` | List your documents (`type`, `resume_id`, `internship_id`) |
| GET | `/documents/{id}` | Current content, fact-check results, ATS report |
| PATCH | `/documents/{id}` | Save edited content as a new version |
| GET | `/documents/{id}/versions` | Version history |
| POST | `/documents/{id}/versions/{version}/restore` | Restore a version (creates a new version) |
| GET | `/documents/{id}/download?format=docx\|txt` | Download (rendered on request, not stored) |
| DELETE | `/documents/{id}` | Permanently delete a document and its versions; the UI must ask for confirmation |

### 6D.1 Factual consistency

Documents are built only from a **fact base** with stable ids:
- `sum-1`: the summary
- `prof-1`: the profile degree
- `edu-N`, `exp-N`, `int-N`, `proj-N`: education, experience, internship and project entries
- `cert-N`, `ach-N`, `lang-N`: certifications, achievements and languages

The facts come from the resume's latest successful extraction and the profile. Contact details (name, e-mail, phone, links, location) are kept separately: they appear only in the document header, which is filled in locally.

The fact checker flags:
- technical skills the candidate does not have, unless the cited fact itself names the skill
- numbers that are not in the cited facts
- capitalised names or terms that are not in the cited facts, the internship record or the skills
- unknown fact ids

### 6D.2 Create a resume

```json
{
  "resume_id": 3,
  "internship_id": 12,
  "use_llm": false,
  "llm_consent": false,
  "options": { "max_skills": 15, "max_projects": 3, "max_experience": 4, "max_bullets": 4 }
}
```

Deterministic generation (the default) orders matched required skills first, then matched preferred skills, then the rest. It ranks experience and projects by how many of the internship's skills they mention, trims the summary to two sentences and tidies line formatting. **Nothing is added.**

The response includes an `ats_report`:
- required and preferred keyword coverage, with where each keyword was found
- missing keywords, each with "add only if true" guidance; they are **never inserted**
- format and contact checks

### 6D.3 Create a cover letter

```json
{ "resume_id": 3, "internship_id": 12, "tone": "formal", "emphasize_skills": ["FastAPI"], "use_llm": false, "llm_consent": false }
```

The letter has these paragraphs: greeting, opening (role and company from the internship record), fit (matched skills plus 1–2 cited experiences or projects), an optional learning paragraph, motivation (formal tone only) and closing.

The letter never claims a missing skill. The learning paragraph ("I am currently learning …") appears only for internship skills the student has marked `in_progress` in their Phase 4 skill-gap plan. `emphasize_skills` must be skills on the resume; otherwise the request returns `422`.

### 6D.4 AI-assisted writing (optional, off by default)

- Available only when the server sets `LLM_PROVIDER=groq` and `GROQ_API_KEY`. Otherwise `GET /documents/llm-status` returns `available: false`, and `use_llm: true` returns `503`.
- Each request must set `use_llm: true` **and** `llm_consent: true`, after the client has shown the `disclosure` text. Without consent the request returns `422`.
- Only the content facts needed for the document and the internship details are sent. **Name, e-mail, phone, links and location are never sent.** Every payload is checked before sending; if contact details are detected, nothing is sent and deterministic content is used.
- *(Hardened in Phase 6, applies to every AI request.)* After that check, a copy of every candidate string is scrubbed of:
  - each part of the name
  - the parsed postal address and its parts
  - street-number patterns
  - six-digit PIN codes
  - any e-mail, phone number or link

  The copy is checked again, and if anything remains nothing is sent (`privacy_guard`; the warning names the kind of data, never the value). The internship record and canonical skill lists are not altered. AI statements that repeat a removed detail (`[removed]`) are rejected (`privacy_placeholder`). Stored resumes, facts and documents are unchanged.
- Every generated statement must cite fact ids and pass the fact checker. Unsupported statements are replaced by deterministic content and listed in `fact_check.rejected_statements`.
- If the provider fails or times out, deterministic content is used and an `llm_unavailable` warning is recorded.
- API keys and resume content are never logged.

### 6D.5 Editing and versions

`PATCH /documents/{id}` accepts `{ "title"?: str, "content": <structured content> }`. The content type must match the document (`resume` or `cover_letter`). Limits: 12 sections or paragraphs, 50 items per section, 20 lines per item, 500 characters per line.

Edits are saved as written. The same fact checks run and are returned as `fact_check.warnings`; for example, an edit mentioning a skill that is not on the resume is flagged. If the source resume has been deleted, a `source_unavailable` warning is returned instead.

### 6D.6 Downloads

- `format=docx`: an ATS-friendly single-column DOCX with standard headings and plain bullets, and no tables, images or text boxes. The project's own resume parser reads it back with the same skills, education and contact e-mail.
- `format=txt`: plain text.
- PDF is not supported in this phase.

## 6E. Interview Preparation APIs

All endpoints require login. Sessions, questions and answers of other users return `404`. Inactive or past-deadline internships return `404`; a resume without a successful extraction returns `422`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/interviews/question-bank/version` | Bank versions and coverage |
| GET | `/interviews/questions/preview?resume_id=&internship_id=&technical=&project=&behavioral=&internship=&difficulty=` | Preview a question set (not saved) |
| POST | `/interviews/sessions` | Start a practice or mock interview (`201`) |
| GET | `/interviews/sessions` | History (`status`, `internship_id`, `resume_id`) |
| GET | `/interviews/sessions/{id}` | Session with questions |
| POST | `/interviews/sessions/{id}/questions/{qid}/reveal` | Reveal the suggested answer |
| POST | `/interviews/sessions/{id}/questions/{qid}/answers` | Submit an answer (`201`); retries allowed |
| GET | `/interviews/sessions/{id}/questions/{qid}/answers` | All attempts |
| POST | `/interviews/sessions/{id}/complete` | Finish and get the summary |
| DELETE | `/interviews/sessions/{id}` | Permanently delete (the UI must confirm) |
| GET | `/interviews/progress` | Progress across sessions |

### 6E.1 Questions

Create body:

```json
{ "resume_id": 3, "internship_id": 12, "mode": "mock",
  "mix": { "technical": 3, "project": 2, "behavioral": 2, "internship": 1 },
  "difficulty": "mixed", "time_limit_seconds": 120, "use_llm": false, "llm_consent": false }
```

Rules: the mix totals 1–15 questions, `difficulty` is `mixed`/`easy`/`medium`/`hard`, and `time_limit_seconds` is 30–900 (applies in mock mode only). Without an internship, the internship-specific quota becomes behavioral questions.

| Category | Source | Grounding |
|---|---|---|
| Technical | Curated bank (`backend/data/interview_question_bank.json`, v2026.11-v2): 207 questions, 3 per skill (easy/medium/hard) for all 69 dataset skills, each with 3 key points | Ordered: the internship's required skills you have, then required skills you lack (labelled `required_missing`), then preferred skills you have, then your other skills |
| Project / experience | Templates | Use only the cited fact's title and the skills that fact names; `source_fact_ids` is returned |
| Behavioral / HR | Curated bank (12 questions, STAR guidance) | Questions from your 3 most recent sessions are avoided |
| Internship | Templates (motivation, missing required skill, fit, domain) | Use only the internship record |

Selection is deterministic for a given user, resume, internship and session number.

**Notices.** If the session has fewer (or different) questions than requested, `notices` explains why, for example:

```json
[{ "code": "fewer_questions", "category": "project", "requested": 5, "generated": 2,
   "detail": "Your resume has 2 project or experience entries to ask about. Add projects to your resume for more questions." },
 { "code": "internship_questions_replaced", "category": "internship", "requested": 1, "generated": 0,
   "detail": "No internship was selected, so internship-specific questions were replaced with behavioral questions." }]
```

`notices` is also stored in `summary.notices`, together with `summary.requested_questions`. The preview endpoint returns only the question list.

**Mock mode:** `key_points`, `explanation` and `suggested_answer` are `null` until the question is answered or revealed. **Practice mode:** they are always visible.

### 6E.2 Answer evaluation (deterministic by default)

`POST .../answers` with `{ "answer_text": "...", "time_taken_seconds": 95, "use_llm_feedback": false, "llm_consent": false }`. Answers can be 1–5,000 characters. Answering a completed session returns `409`.

Scores are 0–100. Labels: Excellent ≥ 80, Good ≥ 65, Fair ≥ 45, Needs work otherwise.

| Category | Rubric |
|---|---|
| Technical | **Key-point coverage, not verified correctness.** 80% key-point coverage + 20% length. A key point is covered by its curated keywords, or by local semantic similarity ≥ **0.50** with the pinned MiniLM model (nothing leaves the server). The threshold was calibrated so that off-topic, generic and vague answers get no credit. |
| Behavioral | STAR structure 50%, answering the actual question 20%, first-person 15%, length 15%. Off-theme answers are capped at 50. |
| Project | Mentions the project 25%, its technologies 30%, own role 20%, outcome 15%, length 10% |
| Internship | Company or role (or a learning plan for a missing skill) 30%, real skills 30%, specificity 20%, length 20% |

Answers under 10 words are capped at 20, and empty answers score 0. If an answer mentions skills that are not on the resume, `advisories` notes are returned; they do not change the score.

**Safeguards against inflated scores:**

| Case | Rule | Field in `evaluation` |
|---|---|---|
| Common incorrect statement (technical) | 143 questions across 61 skills have curated wrong statements (`backend/data/interview_misconceptions.json`, v2026.11-v2), such as "lists are immutable" or "an image is the running instance". A match gives that key point no credit, even if its keywords appear, and caps the score at 55 (one mistake) or 35 (two or more). A wrong statement the student rejects ("it is a misconception that …") is not penalised. | `incorrect_statements` (with corrections), `caps_applied: ["incorrect_statements"]` |
| "I don't know" (technical) | Sentences that say the student does not know earn no credit. If they make up half the answer or more, the score is capped at 25. | `uncertain_sentences`, `caps_applied: ["mostly_uncertain"]` |
| Keyword list (all categories) | An answer of 10+ words with no real sentence (a run of words with almost no joining words) is capped at 30. | `caps_applied: ["keyword_list"]` |
| Thin STAR story (behavioral) | STAR parts count only in real sentences. Fewer than 3 real sentences, or every part in a single sentence, halves the STAR credit and caps the score at 40. | `real_sentences`, `caps_applied: ["thin_story"]` |

Technical evaluations include `"score_basis": "key_point_coverage"` and `"correctness_verified": false`. Their feedback starts with "Key-point coverage" and states that the score does not verify every statement.

Each attempt is stored (`attempt` 1, 2, …). The question shows the latest one.

**Optional AI feedback:** set `use_llm_feedback: true` **and** `llm_consent: true`.
- It is off by default. Without consent the request returns `422`; without a configured provider it returns `503`.
- Before sending, a copy of the answer is scrubbed of:
  - the full name and each part of it (first name or surname on its own)
  - e-mail, phone and links
  - the stored resume address, each part of it, and the profile location
  - street-number patterns ("12 MG Road", "Flat No. 4B") and six-digit PIN codes

  A final check runs on the scrubbed text. If anything personal remains, nothing is sent (`llm_warnings` code `privacy_guard`). The stored answer is never altered.
- The same shared scrubber and check (`backend/services/llm_privacy.py`, applied in `call_llm`) protect every AI request: Phase 5 resumes and cover letters, AI-tailored interview questions and answer feedback. AI-tailored questions that repeat a removed detail are rejected (`privacy_placeholder`).
- If the session's resume was deleted, AI feedback is skipped with `llm_warnings` code `resume_unavailable`.
- **Scores always come from the rubric.** If the provider fails, rubric feedback is returned with an `llm_warnings` entry (`llm_unavailable`).

**Optional AI-tailored questions** (`use_llm` at session creation): at most 2 extra questions. Each must cite fact ids and pass the Phase 5 fact checker; rejected questions are recorded in `summary.generation`.

### 6E.3 Completion and progress

`POST .../complete` returns `summary`:
- `overall_score`: unanswered questions count as 0
- `average_answered_score`
- `by_category`
- `strengths` and `improvements` (with missed key points)
- `related_skill_gaps`: matching Phase 4 recommendations, read-only

`GET /interviews/progress` returns:
- session and answer counts and the average score
- `by_category` and `by_skill`
- `retry_improvement`: the average change from first to last attempt
- the last 10 completed session scores

## 6F. Application Tracking APIs (Phase 7)

All endpoints require login and only ever return the caller's own records: another student's id returns `404`. The student id always comes from the access token; request bodies reject unknown fields (`422`), so `user_id` cannot be supplied. Nothing in this module calls an AI provider.

**Timestamps.** Every incoming timestamp must include a UTC offset, e.g. `2026-11-20T10:30:00+05:30` (India Standard Time) or `2026-11-20T05:00:00Z`; values without one are rejected with `422`. Timestamps are stored in UTC and every Phase 7 response returns UTC ISO 8601 ending in `Z` (the frontend converts to local time). Date filters (`applied_from`, `due_to`, ...) also need an offset, so the frontend sends the student's local day boundaries.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/applications/dashboard` | Dashboard (6F.7) |
| POST | `/applications/bookmarks/{internship_id}` | Save: `201` created, `200` if already saved |
| GET | `/applications/bookmarks?skip=&limit=` | Saved internships (`{total, skip, limit, items}`) |
| GET | `/applications/bookmarks/{internship_id}` | `{saved: bool, bookmark}` (always `200`) |
| DELETE | `/applications/bookmarks/{internship_id}` | `204`, `404` if not saved |
| POST | `/applications` | Create (`201`) |
| GET | `/applications` | List with filters, search, sorting, paging |
| GET | `/applications/{id}` | Detail, including `related` links |
| PATCH | `/applications/{id}` | Edit details (not status) |
| DELETE | `/applications/{id}?confirm=true` | Move to the trash (`204`); `422` without `confirm=true` |
| GET | `/applications/trash` | Trashed applications |
| POST | `/applications/{id}/restore` | Restore (`409` if not trashed or an active duplicate exists) |
| DELETE | `/applications/{id}/permanent?confirm=true` | Permanently delete a trashed application with ALL its history, interview rounds, reminders and activity (`409` if not in the trash) |
| PATCH | `/applications/{id}/status` | Change status |
| GET | `/applications/{id}/history` | `{status_history, activity}` |
| POST / GET | `/applications/{id}/interviews` | Add (`201`) / list rounds |
| GET / PATCH / DELETE | `/applications/interviews/{interview_id}` | Round detail / edit / delete (`{deleted, status_change}`) |
| POST | `/applications/{id}/reminders` | Add a reminder (`201`) |
| GET | `/applications/reminders` | List reminders |
| PATCH / DELETE | `/applications/reminders/{reminder_id}` | Edit or complete / delete (`204`) |

### 6F.1 Bookmarks

Only active internships whose deadline has not passed can be saved (`404` otherwise). Each item includes an internship summary (`title`, `company`, `location`, `work_mode`, `domain`, `deadline`, `is_active`, `deadline_passed`) and `application_id` if the student has already applied. Full details stay at `GET /internships/{id}`. Bookmarks are separate from the `SAVED` status: saving does not create an application.

### 6F.2 Applications

Internal (from the knowledge base):

```json
{ "internship_id": 12, "status": "APPLIED", "applied_at": "2026-11-10T11:00:00+05:30",
  "notes": "Applied with the tailored resume", "resume_document_id": 7, "cover_letter_document_id": 8 }
```

Company, title, URL, domain, location and work mode are copied from the internship (sending them returns `422`). The internship must be active; a passed deadline is allowed (so late-recorded submissions can be logged) and shown as `deadline_passed: true` (computed from the deadline alone, also for inactive internships).

External (found elsewhere):

```json
{ "company_name": "Acme Robotics", "title": "Software Intern", "application_url": "https://jobs.acme.example/42",
  "external_reference": "REQ-1001", "location": "Pune", "work_mode": "Hybrid", "domain": "Robotics",
  "contact_name": "Hiring team", "contact_email": "careers@acme.example", "status": "SAVED" }
```

Filters: a start after its end (`applied_from`/`applied_to`, `created_from`/`created_to`, `due_from`/`due_to`) or a blank `q`/`company`/`domain` returns `422`. A write that fails because related data changed at the same moment returns `409` with a generic message; only real duplicates return the duplicate message.

Validation: `status` is `SAVED` or `APPLIED` at creation (default `SAVED`); `applied_at` only with `APPLIED`, between 2000-01-01 and now (defaults to now); URLs must be `http://` or `https://`; e-mail addresses are validated; text limits: company/title 200, location 150, domain 80, reference 100, contact name 120, notes 5,000. Linked documents must be the student's own Phase 5 resume / cover letter. Per-student caps: 1,000 applications, 1,000 bookmarks, 20 rounds and 100 reminders per application.

**Duplicate prevention.**

| Case | Rule |
|---|---|
| Internal | One active application per internship (`409` with the existing `application_id`) |
| External with URL | Same *normalised* URL is a duplicate (`409`): scheme, host case and `www.` ignored, fragment and trailing slash removed, tracking parameters (`utm_*`, `ref`, `source`, `gclid`, `fbclid`, `trk`, `referrer`, `src`) removed; path and other query parameters kept, so different openings stay distinct |
| External with reference | Same company (case and spacing ignored) + same `external_reference` is a duplicate (`409`) |
| Neither | Never blocked; the response lists `possible_duplicates` (same company and title) so the frontend can ask |

Trashed applications are ignored by all duplicate rules.

`PATCH /applications/{id}` edits details only (`status` returns `422`). For internal applications company, title, URL and reference come from the internship and cannot be edited. Only fields that really change are recorded in the activity feed, as field NAMES.

**List filters:** `status` (repeatable), `source` (`internal`/`external`), `company` (contains), `domain` (exact, case-insensitive), `q` (title or company contains; `%` and `_` are literal), `applied_from`/`applied_to`, `created_from`/`created_to`; `sort` = `created_at`, `updated_at` (default), `applied_at`, `company_name`, `title` or `status`; `order` = `asc`/`desc` (empty values last); `skip`, `limit` (1-100, default 20).

**Detail extras:** `interview_count`, `next_interview`, `pending_reminders`, `next_reminder`, `internship_active`, `deadline_passed` and `related`: the student's latest Phase 3 match score for this internship (read-only), the linked Phase 5 documents, up to five Phase 6 practice sessions for the same internship, and `prepare_with` (`POST /interviews/sessions` with the internship id).

**Deletion.** `DELETE ...?confirm=true` moves the application to the trash: it disappears from lists, the dashboard, reminders and every other endpoint, but its history, rounds and reminders are kept and `POST .../restore` brings everything back. `DELETE .../permanent?confirm=true` (trashed applications only) removes the application and all related records for good. There is no automatic purge: trashed items stay until deleted permanently or the account is deleted. Deleting the account deletes everything.

### 6F.3 Status rules

`PATCH /applications/{id}/status` with `{ "status": "SHORTLISTED", "correction": false, "expected_status": "APPLIED" }`.

| From | Allowed |
|---|---|
| `SAVED` | `APPLIED`, `WITHDRAWN` |
| `APPLIED` | `SHORTLISTED`, `INTERVIEW_SCHEDULED`, `SELECTED`, `REJECTED`, `WITHDRAWN` |
| `SHORTLISTED` | `INTERVIEW_SCHEDULED`, `SELECTED`, `REJECTED`, `WITHDRAWN` |
| `INTERVIEW_SCHEDULED` | `SHORTLISTED`, `SELECTED`, `REJECTED`, `WITHDRAWN` |
| `SELECTED` | `WITHDRAWN` (offer declined) |
| `REJECTED`, `WITHDRAWN` | none |

* Same status: `200` with `changed: false`; no history entry.
* Not allowed: `409` listing the allowed values. Unknown values: `422`.
* `correction: true` undoes the last change only (the new status must be the previous one); it can reopen a final status and is recorded as `correction`. Correcting back to `SAVED` clears `applied_at`.
* `applied_at` is set the first time the application moves past `SAVED` (except `SAVED -> WITHDRAWN`), unless the student entered a date.
* `expected_status` that no longer matches returns `409` (protects against stale browser tabs).
* Each change (application, history, activity) is one transaction; the application row is locked, so concurrent changes are applied one after the other.

Response: `{ "changed": true, "from_status": "APPLIED", "to_status": "SHORTLISTED", "application": {...}, "warnings": [] }`. `warnings` notes pending interview rounds left outside the interview stage (for example after a correction). History `change_type` values: `created`, `manual`, `correction`, `interview_added`, `interview_cancelled`, `migrated`.

### 6F.4 Interview rounds

```json
{ "interview_type": "technical", "mode": "online", "scheduled_at": "2026-12-01T10:00:00+05:30",
  "duration_minutes": 45, "meeting_url": "https://meet.example/abc", "preparation_notes": "Revise joins",
  "outcome": "pending", "interview_session_id": 31 }
```

Types: `technical`, `hr`, `behavioral`, `managerial`, `case_study`, `assignment`, `group`, `other`. Modes: `online`, `offline`, `phone`. Outcomes: `pending` (default), `passed`, `failed`, `cancelled`, `no_show`. Rounds are numbered automatically. `scheduled_at` must be within two years of today; `duration_minutes` 5-600; meeting URL `http(s)` only.

* Rounds can be added once the application is submitted (`APPLIED`, `SHORTLISTED`, `INTERVIEW_SCHEDULED`, `SELECTED`, `REJECTED`); `SAVED`/`WITHDRAWN` return `409`.
* **Status consistency:** adding a non-cancelled round (or un-cancelling one) moves `APPLIED`/`SHORTLISTED` to `INTERVIEW_SCHEDULED`; recording a round that is already cancelled never changes the status. When an existing round is cancelled or deleted and no remaining round is pending or took place (`passed`, `failed`, `no_show`), an `INTERVIEW_SCHEDULED` application returns to the last `APPLIED` or `SHORTLISTED` status before the interview stage (corrections and detours are skipped; `APPLIED` if none). `SELECTED`, `REJECTED` and `WITHDRAWN` are never changed automatically. Rescheduling never changes the status. Responses include `status_change` (`{from_status, to_status, reason}` or `null`).
* **Phase 6:** `interview_session_id` links an existing practice session the student owns; if both have an internship they must match (`422`). Practice sessions are not copied or rescored; deleting a session leaves the round with `interview_session_id: null`.

### 6F.5 Reminders (stored only)

`{ "title": "Follow up with HR", "description": "Ask about the timeline", "remind_at": "2026-11-25T09:00:00+05:30" }`. Title 1-150, description up to 2,000; `remind_at` from now (5 minutes' tolerance) up to two years ahead. `PATCH` edits fields or sets `is_completed` (completing sets `completed_at`; reopening clears it).

**Reminders are not delivered.** No e-mail, SMS, push or background scheduler exists; every reminder has `"delivery": "not_sent"`. Responses include `overdue` (pending and past due) and `due_within_24h`.

`GET /applications/reminders`: `status` = `pending` (default), `completed` or `all`; `application_id`; `due_from`/`due_to`; `overdue` = `true`/`false`; `skip`, `limit` (1-100, default 50); sorted by `remind_at`.

### 6F.6 History and activity

`GET /applications/{id}/history` returns `status_history` (every real status change) and `activity`: `application_created`, `details_updated`, `status_changed`, `interview_scheduled`, `interview_updated`, `interview_deleted`, `reminder_created`, `reminder_updated`, `reminder_completed`, `reminder_reopened`, `reminder_deleted`, `application_deleted`, `application_restored`. Activity `details` contain statuses, changed field names, round numbers and ids only, never notes, contact details, URLs or reminder text.

### 6F.7 Dashboard

Computed from the caller's non-trashed records only; an empty account returns zeros and `null` rates.

| Field | Definition |
|---|---|
| `saved_internships` | Bookmarks |
| `total_applications`, `by_status` | All seven statuses, zeros included |
| `submitted_applications` | Applications with `applied_at` (submitted at some point) |
| `selected`, `rejected` | Applications in that status |
| `interviews_scheduled` | Rounds not cancelled |
| `upcoming_interviews`, `next_interviews` | Pending rounds from now on (count and the next five) |
| `pending_reminders`, `overdue_reminders`, `completed_reminders` | Reminder counts |
| `success_rate` | SELECTED applications that were submitted / submitted_applications x 100 (never above 100%) |
| `decision_rate` | SELECTED / (SELECTED + REJECTED) x 100 |
| `interview_rate` | submitted applications with >= 1 non-cancelled round / submitted_applications x 100 |
| `recent_activity` | Last 10 events |

Rates are rounded to one decimal place and `null` when the denominator is 0; the formulas are also returned in `formulas`.

### 6F.8 Example workflow

1. `POST /applications/bookmarks/12` while browsing (Phase 2) or after a match run (Phase 3).
2. Tailor documents (Phase 5), then `POST /applications` with `internship_id: 12`, `status: "APPLIED"` and the document ids.
3. Shortlisted: `PATCH /applications/41/status` `{ "status": "SHORTLISTED" }`.
4. Interview invite: `POST /applications/41/interviews` (status becomes `INTERVIEW_SCHEDULED`); practise with `POST /interviews/sessions` (Phase 6) and link the session to the round.
5. `POST /applications/41/reminders` to follow up; `PATCH /applications/reminders/9` `{ "is_completed": true }` when done.
6. Offer: `PATCH /applications/41/status` `{ "status": "SELECTED" }`; the dashboard updates.

## 6G. Career Assistant APIs (Phase 8)

All endpoints require login; conversations belong to their creator and another student's id returns `404`. Request bodies reject unknown fields. Timestamps are UTC ISO 8601 ending in `Z`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/assistant/capabilities` | Example questions per intent, `llm` status with privacy disclosure, limits, notes |
| POST | `/assistant/conversations` | `{resume_id?, title?}` -> `201`. `resume_id` must be the student's own (`404`) |
| GET | `/assistant/conversations?skip=&limit=` | `{total, skip, limit, items}`, most recently updated first |
| GET | `/assistant/conversations/{id}` | Conversation with its 50 most recent messages |
| PATCH | `/assistant/conversations/{id}` | `{title?, resume_id?}` (switching resume clears the current focus) |
| DELETE | `/assistant/conversations/{id}?confirm=true` | Permanent delete with all messages (`422` without `confirm=true`) |
| GET | `/assistant/conversations/{id}/messages?before_id=&limit=` | History, oldest first, paged backwards |
| POST | `/assistant/conversations/{id}/messages` | `{message, use_llm=false, llm_consent=false}` -> `201` `{conversation_id, user_message, assistant_message}` |

### 6G.1 How a question is answered

1. **Understand** (no AI): ordered rules detect the intent and entities (ordinals such as "the second one", pronouns, `internship #12`, `application #5`, skills, statuses, work mode, search words). An optional second stage compares the question with example phrases using the local MiniLM model (threshold 0.55, margin 0.05; off-topic questions are never classified); it never leaves the server.
2. **Resolve** what the question refers to (6G.3).
3. **Gather facts** with read-only tools that call existing Phase 1-7 services for the logged-in student only. Nothing is recalculated or written: match explanations come from stored match runs, recommendations from stored skill-gap rows, statuses from the application tables.
4. **Answer** with a deterministic template made only of those facts, plus `suggested_actions` (`{label, method, endpoint, body, requires_confirmation}`) that the frontend may run after the student confirms. The assistant itself never changes data.
5. **Optional AI rewording** (6G.5).

| Intent | Example | Source types |
|---|---|---|
| `profile_summary` | "What skills are on my resume?" | `resume`, `resume_fact` |
| `internship_search` | "Find remote data internships in Pune" | `internship` (FAISS; only active internships with an open deadline, exactly as in the keyword fallback, which is used with a `semantic_search_unavailable` warning only when the index or embedding model is unavailable) |
| `internship_detail` | "Tell me more about the second one" | `internship`, `application`/`bookmark` |
| `top_matches`, `match_explain` | "Show my top matches", "Why is the first one a good match?" | `match_result`, `internship` (stored runs only; top matches list only internships that are still open and say how many closed ones were hidden - `closed_matches_hidden`; an explanation of a closed internship starts by saying it is no longer open - `internship_closed`) |
| `skill_gap` | "What skills am I missing for it?", "Show my skill gaps" | `internship`, `resume`, `skill_gap_recommendation`, `learning_plan` |
| `learning_plan` | "How do I learn Docker?" | `learning_plan` |
| `document_help` | "Cover letter for the first one" | `document`, `internship`, `resume` (ATS check) |
| `interview_prep` | "Practice questions on SQL", "My interview progress" | `question_bank`, `interview_progress`, `interview_session` |
| `application_status` | "Status of my Acme application", "Which were rejected?" | `application`, `application_interview`, `application_reminder` |
| `upcoming_interviews`, `reminders`, `dashboard` | "When is my next interview?" | `application_interview`, `application_reminder`, `dashboard` |
| `help`, `unknown` | "What can you do?" | none (not factual) |

### 6G.2 Messages and sources

```json
{ "message_id": 42, "sender": "assistant", "intent": "internship_detail",
  "content": "Details for Backend Intern at Nimbus Analytics:\n- Location: Pune; work mode: Hybrid.\n- ...",
  "sources": [{ "type": "internship", "id": "12", "label": "Backend Intern at Nimbus Analytics", "available": true }],
  "result_set": null,
  "suggested_actions": [{ "label": "Save this internship", "method": "POST",
                          "endpoint": "/applications/bookmarks/12", "body": {}, "requires_confirmation": true }],
  "generation_method": "deterministic", "warnings": [], "created_at": "2026-11-15T10:00:00Z" }
```

Every factual line comes from a fact with at least one source `{type, id, label}`, so the frontend can open exactly the resume, internship, match result, recommendation, document, session, application, interview round or reminder behind it. When reading history, `available` is `false` for records deleted, closed or trashed since. Answers that are questions or guidance (help, clarifications) have no sources. Contact details, notes and reminder descriptions are never included in answers.

### 6G.3 Follow-ups and context

* A list answer stores its ordered `result_set` (`{kind, items: [{type, id, label}]}`) on the assistant message. "The second one" / "the last one" / "number 3" resolves against the **most recent list shown in this conversation**; a newer (possibly reordered) list replaces it, while non-list answers do not.
* "It" / "that one" uses the current focus (the entity of the last detail answer), else the only item of the last list; with several candidates the assistant asks "Which one do you mean?" and lists them (that list becomes the new result set). Out-of-range ordinals are answered with the list again.
* Explicit references (`internship #12`, `application #5`) and company names are checked against the database and the student's own records; another student's application is "not found".
* The conversation `context` stores only pointers (`last_result_message_id`, `focus {type, id, message_id}`), never resume facts. If the message holding a list was deleted, the assistant says the earlier list is no longer available instead of guessing; deleted or closed records referenced by a follow-up are reported as unavailable.

### 6G.4 Privacy, deletion and limits

* Account deletion removes all conversations, messages and rate-limit counters.
* Every message pair whose answer used resume data records that `resume_id`; deleting the resume deletes those turns (`ON DELETE CASCADE`), so no deleted resume facts remain in chat history, and the conversation's pinned resume becomes `null` (the latest parsed resume is used afterwards). Turns that did not use resume data are kept.
* Rate limits per student: 10 messages per minute and 300 per day (`429` with `Retry-After`), plus 30 AI provider calls per hour. The AI limit is counted only when a provider call is actually made (not for answers without facts or requests refused by the privacy check); when it is reached the provider is not called and the standard answer is returned with an `ai_rate_limited` warning (with `retry_after`). Counters are incremented with one atomic `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` in their own transaction, so concurrent requests can never exceed a limit; rejected message attempts count.
* Size limits: messages 1-2,000 characters; 200 conversations per student; 500 messages per conversation (`409`).
* Errors: if the semantic index or embedding model is unavailable, search falls back to keywords; database errors return `503` "The assistant could not answer right now" with nothing saved and no internal details; other unexpected errors are not hidden by a fallback.
* Closed internships: anything that is deactivated or past its deadline is never presented as a current opportunity - search and top matches leave it out, and detail, explanation, skill-gap and document answers state "This internship is no longer open: ..." as a sourced fact. History sources show `available: false` for records deleted, closed or trashed since (including deleted bookmarks).

### 6G.5 Optional AI rewording

Off by default. Set `use_llm: true` **and** `llm_consent: true` (`422` without consent, `503` when not configured). Only answers with facts are reworded (otherwise `llm_not_applicable`).

* Sent: only the detected **topic** (for example "internship search results") and the answer's facts in an AI-safe form. **Never sent:** the text of the question, the chat history, names, account and resume contact details, addresses, PIN codes, notes, contact persons, reminder titles or descriptions, document titles, or the company and job titles typed for external applications (these facts are sent as, for example, "a reminder for an external application, due ..."). The request still goes through the shared `call_llm` privacy pipeline (6D/6E). `GET /assistant/capabilities` returns this as `llm.assistant_disclosure`.
* The AI must return `{"sentences": [{"text", "fact_ids"}]}`. Each sentence is verified against the facts it cites: numbers, skills and names must appear in those facts; a skill marked missing must not be described as present (and vice versa); status words must match; negated statuses and overclaiming ("guaranteed", "definitely", "best", ...) are treated as uncertain; `[removed]` placeholders are rejected.
* If any sentence fails or is uncertain, the whole AI answer is discarded and the deterministic answer is returned with an `llm_unverified` warning (`llm_unavailable` if the provider failed). The `result_set` always comes from the deterministic answer, so follow-ups stay exact.
* Accepted answers have `generation_method: "llm"` and only the sources of the cited facts.

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

