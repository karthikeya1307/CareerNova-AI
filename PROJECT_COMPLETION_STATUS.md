# CareerNova AI — Project Completion Status

*Your Skills. Your Potential. Your Career.*

Last updated: 2026-11-19 · Branch `phase-9/frontend` (uncommitted work present; nothing committed or pushed).

Legend: ✅ done **and tested** · 🟡 partial / implemented but not fully verified · ⬜ not started · ⛔ blocked (needs owner action or external service)

## Current state (verified 2026-11-19)

| Item | State |
|---|---|
| Dev database `career_companion_dev` | revision `b2e8c4a7d1f5`; 2 users, 11 resumes, 180 internships, 135 match results, 3 conversations |
| Pending migrations | `c6d2a8f4b1e3`, `d8e4b2c6a9f1`, `e1f3a5c7b9d2` — full chain rehearsed on a restored copy (data and password hashes unchanged), **not applied** (owner approval) |
| Backup `career_companion_dev_20261119_100709.dump` | test-restored into `careernova_restore_test_20261119_101233`: identical schema and row counts |
| Backend / frontend services | not running at inspection time |
| Local AI | Ollama provider added and verified with `gemma3:latest` (first answer ~96 s on CPU) |
| Windows Smart App Control | **blocks PyTorch since 2026-11-24** → semantic features fall back; 63 real-model tests cannot run here |
| Vector index | NumPy `.npz` format; the old FAISS dev index is rejected; rebuild needed (owner approval: writes `knowledge_documents` status) |
| Python env | project `.venv` works (FAISS no longer imported); `venv-demo` exists only inside the Claude app's virtualised folder |

## P0 — Database safety and account security

- ✅ Backup test-restored into a separate database and compared (schema + row counts).
- ✅ Migration `c6d2a8f4b1e3` rehearsed on the restored copy: up, down, up; data unchanged; no drift.
- ✅ Roles student / admin / super_admin; single super admin enforced by the database.
- ✅ `create-superadmin` CLI (hidden password, idempotent, audited) — 13 tests.
- ✅ Admin: list/search users, create pending accounts, deactivate/reactivate; super admin only for roles and admins — 25 tests.
- ✅ Deactivated users rejected on every authenticated API, including old tokens; sessions revoked.
- ✅ Login throttling (atomic, concurrent-safe) — 10 tests.
- ✅ Audit log without secrets (API + Admin → Audit log page).
- ✅ Frontend: role-aware navigation/routes, users page, audit page — admin + auth frontend tests.
- ⛔ Apply `c6d2a8f4b1e3` to `career_companion_dev` — **owner approval**.
- ⛔ Create the real super admin — **owner runs the CLI** (see `SUPER_ADMIN_SETUP.md`).

## P1 — Email, invitations, activation, password reset

- ✅ Mail module: `outbox` (default, sends nothing) / `smtp` / `disabled`; STARTTLS and SSL; config validation; timeouts; classified failures; masked logs; delivery log — 24 tests.
- ✅ Branded HTML + plain-text templates (verification, invitation, reset, activated, test); links open the frontend.
- ✅ Invitation → activation with the person's own password; single use, 72 h expiry, resend revokes the old link, revoke; cooldown + daily limit — 12 tests.
- ✅ Password-reset emails limited to one per account per minute; deactivated accounts get none.
- ✅ Admin visibility: invitation + email status per pending user, Resend invitation; `/admin/email/status`, `/admin/email/deliveries`.
- ✅ Frontend: `/accept-invitation` page, users page invitation status/resend — auth + admin frontend tests.
- ✅ `python -m backend.manage email-check [--send-test]` (no secrets printed).
- ⛔ Real email sending — `.env` `MAIL_FROM` is a placeholder; owner must fix it and authorise `EMAIL_MODE=smtp`.

## P2 — Resume parsing, ATS readiness, job matching (see `P2_IMPLEMENTATION_REPORT.md`)

- ✅ Resume upload and parsing (PDF/DOCX, sections, skills, education, projects, certifications) — existing tests.
- ✅ Two-column PDFs read column by column (only when better than plain extraction); phone-number line-merge bug fixed.
- ✅ Dates and durations, per-section confidence, missing core/recommended fields, parsing warnings (`GET /resumes/{id}/analysis`).
- ✅ Duplicate uploads reported (identical file / same content), not blocked.
- ✅ Review and correct extracted details (`PUT /resumes/{id}/extracted-data`, used everywhere; re-parse reverts).
- ✅ General Resume Readiness 0–100 (`readiness-v1`, 8 documented categories, reasons, recommendations) — `GET /resumes/{id}/readiness`.
- ✅ Job insights (`insights-v1`): Skill Match, Eligibility, Application Readiness, Apply Now / After Improvement / Long-Term, matched/partial/missing, reasons, improvements, application link.
- ✅ "For my resume" (ranked matching + insights) and "Explore any job" (`GET /matches/explore`) — backend and frontend.
- ✅ Job-specific ATS keyword report and cover letter tied to the selected internship (earlier work).
- ⬜ OCR for scanned PDFs; three-or-more-column layouts.

## P3 — Skill gaps, career tracks, AI providers, job sources (see `P3_IMPLEMENTATION_REPORT.md`)

- ✅ Skill-gap analysis with priorities, learning plans and status tracking (existing tests).
- ✅ Per-job learning roadmap with persisted Not Started / Learning / Practiced / Completed progress — backend + frontend tests, verified live.
- ✅ Career tracks for all 11 roles (skills, roadmap, exercises, projects, resume advice, bank-only interview questions, official docs links, relevant jobs) — verified live.
- ✅ Career assistant with product-guide RAG and memory; keyword fallback when the embedding model cannot load.
- ✅ Optional Ollama provider (local Gemma 3, verified live) alongside Groq; safe fallbacks.
- ✅ Job-source tracking: source URL, posted/verified dates, freshness, sample labels, duplicate rejection, source filters, explore de-duplication.
- ⬜ External live job feeds (needs a source with permitted access).

## P4 — CareerNova branding, UI polish, handover

- ⬜ Branding (name, tagline, favicon, titles, emails).
- ⬜ Dashboards for admin/super admin health and configuration.
- ✅ Docs: `DATABASE_MIGRATION_GUIDE.md`, `FINAL_DATABASE_MIGRATION_CHECKLIST.md`, `SUPER_ADMIN_SETUP.md`, `SMTP_SETUP.md`, `P2_/P3_IMPLEMENTATION_REPORT.md`, `FINAL_QA_REPORT.md`, `DEPLOYMENT_AND_HANDOVER_GUIDE.md`.
- ⬜ Full CareerNova rebrand of the UI (titles/sidebar still say AI Career Companion) and dashboard redesign.

## Known defects / risks

1. Starting the new backend before migrating the dev database breaks sign-in (`users.is_active` missing).
2. `.env` `MAIL_FROM` is a placeholder; `APP_BASE_URL` points at the backend, so email links are wrong.
3. No vector index in the format the code now reads → semantic search is off until a rebuild.
4. Fixed 15-minute throttle windows; `X-Forwarded-For` not trusted (fine locally, revisit behind a proxy).

## Implementation order

P0 (owner approvals pending) → P1 email/invitations → P2 resume quality + ATS readiness + matching modes →
P3 roadmaps, role assistants, Ollama provider, job sources → P4 branding, dashboards, handover docs.

## Test strategy

Backend: pytest on `career_companion_test` only (the test setup refuses other names); emails captured in
memory; no network. Frontend: Vitest + mocked API. Production build after each batch. Database changes:
rehearse on a restored copy first, then the owner applies them.

Latest full results (2026-11-24, after P3 + audit): backend **1140 passed, 0 failed, 0 skipped, 63 errors** (all 63 = PyTorch blocked by Windows Smart App Control; passed on 2026-11-19); frontend **390 passed**; production build OK; end-to-end API journey passed; live browser walkthrough passed on the test database.
