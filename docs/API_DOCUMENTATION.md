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

