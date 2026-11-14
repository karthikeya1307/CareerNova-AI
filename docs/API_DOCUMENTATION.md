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

Includes user ID, UUID, name, phone number, email, role, and creation timestamp. Password information is not returned.

### 3.2 Verify Email

**Endpoint:** `GET /auth/verify-email`

Verifies the user's email address using the verification token sent by email.

Query parameter:

```text
token=<verification_token>
```

**Success:** `200 OK`

The verification token is single-use and has a limited validity period.

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

The endpoint returns the resume metadata and `extracted_data`.

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

## 7. System APIs

### 7.1 Home

**Endpoint:** `GET /`

Returns the application's home response.

**Success:** `200 OK`

### 7.2 Health Check

**Endpoint:** `GET /health`

Checks whether the application is responding.

**Success:** `200 OK`

## 8. HTTP Status Codes

The OpenAPI specification documents the following success and validation responses:

| Status Code | Meaning |
|---|---|
| 200 | Request completed successfully |
| 201 | Resource created successfully |
| 204 | Request completed without a response body |
| 422 | Request validation error |

Other runtime errors may be returned by individual route handlers for authentication, authorization, missing resources, invalid files, and business-rule violations.

## 9. Validation and Security

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
- Environment secrets must remain in `.env` and must not be committed to Git.

## 10. API Testing

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

## 11. Related Documentation

- `README.md` – Project overview and setup.
- `DFD.md` – Data Flow Diagram.
- `SCHEMA_DESIGN.md` – Database schema design.

