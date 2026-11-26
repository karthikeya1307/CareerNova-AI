# CareerNova AI — Frontend

React + Vite single-page app for the CareerNova AI FastAPI backend.
*Your Skills. Your Potential. Your Career.*

**Status:** steps F0 (foundation), F1 (authentication screens), F2 (student dashboard), F3
(resume management and student profile), F4 (internship discovery and matching), F5 (skill gap
analysis), F6 (resume and cover letter customization), F7 (interview preparation), F8
(application tracking), F9 (career assistant), F10 (admin dashboard), F11 (integration, code
splitting and QA) and the CareerNova redesign. For a guided demonstration see **[DEMO_GUIDE.md](DEMO_GUIDE.md)**.

## Design system (CareerNova redesign)

All styling uses Tailwind; there is no UI component library.

| Where | What |
|---|---|
| `tailwind.config.js` | Tokens: `brand` (AI indigo, `brand-600` = #635BDB), `navy` (#101B36 hero/sidebar), `mint` (#EAF7F3 progress/success), re-tuned `slate` neutrals (page #F5F6FA, text #172033, secondary #697386), fonts (`sans` Inter, `display` Plus Jakarta Sans), shadows (`card`, `card-hover`, `elevated`, `glow`), animations (`fade-in-up`, `scale-in`, `slide-in-left`, `shimmer`, `float`, `grow-x`) |
| `src/index.css` | Base (body, headings in the display font, focus ring, selection), components (`cn-card`, `cn-card-interactive`, `cn-hero`, `cn-grid-pattern`, `cn-input`, `cn-gradient-text`, `cn-skeleton`) and a global `prefers-reduced-motion` rule |
| `src/config/brand.js` | `APP_NAME`, `APP_TAGLINE`, `APP_DESCRIPTION`, `pageTitle()` |
| `src/components/ui/*` | Button (`primary`, `secondary`, `danger`, `ghost`, `inverse`), Badge (`neutral`, `info`, `success`, `warning`, `danger`, `ai`), Card, Input, Select, Checkbox, Modal, EmptyState (with icon), ErrorAlert, Spinner, Pagination |
| `src/components/brand/BrandMark.jsx` | Nova-star logo + wordmark (`inverted` for navy surfaces); `public/favicon.svg` |
| `src/layouts/AppLayout.jsx` | Navy sidebar grouped by Overview / Your profile / Opportunities / Grow your skills / AI assistant (+ Admin for administrators only), active indicator, mobile drawer (focus trap, Escape, slide-in), sticky header with "Ask the assistant" and the profile menu, per-section page fade-in |

Rules: colours only through tokens; every number shown comes from a backend response (no placeholder
statistics); animations are decorative and disabled under `prefers-reduced-motion`.

## Code splitting and integration (F11)

* Every feature page is loaded on demand with `React.lazy` (`src/routes/AppRoutes.jsx`). Sign-in pages,
  the layouts and the dashboard stay in the main bundle. `src/routes/PageBoundary.jsx` wraps the routed
  page in `AppLayout`: a "Loading page" state while a chunk downloads, and an error state with a reload
  button if a chunk fails to download or a page crashes. Route guards (`ProtectedRoute`, `RoleRoute`)
  run before any lazy page loads, so students never download admin code.
* Bundle: one 602 kB chunk (173 kB gzip) before → main chunk 343 kB (111 kB gzip) plus one chunk per
  page (5–30 kB) after. Vite's 500 kB warning no longer appears; the limit was not changed.
* External links from stored data (application links, interview meeting links) are shown as links only
  when they are http(s); anything else is shown as plain text.

## Admin dashboard (F10)

All admin pages sit behind `RoleRoute` (students see a 403 page, signed-out visitors go to sign in) and
the backend checks the admin role on every call; a backend 403 is shown as such, without a retry.

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/admin` | Overview computed from live data: user counts (from the complete user list), internship totals (active vs. all), active internships per domain, index status | `GET /admin/users` (paged), `GET /internships/?include_inactive=true&limit=1`, `GET /internships/filters`, `GET /internships/?domain=&limit=1`, `GET /admin/index/status` |
| `/admin/users` | Users in id order (50 per page, Previous/Next), filter of the loaded page, change role student ⇄ admin (confirmed; not for yourself) | `GET /admin/users?skip=&limit=`, `PATCH /admin/users/{id}/role {role}` |
| `/admin/internships` | Catalogue including deactivated ones, search / domain filters and paging, deactivate (soft delete) and reactivate (confirmed) | `GET /internships/?include_inactive=true&q=&domain=`, `DELETE /internships/{id}`, `PATCH /internships/{id} {is_active}` |
| `/admin/internships/new`, `/admin/internships/:id/edit` | Create; edit sending only changed fields (cleared fields as `null`) | `POST /internships/`, `GET`/`PATCH /internships/{id}` |
| `/admin/index` | FAISS index status (read-only) and rebuild after typing REBUILD; the result, 409 (already running) and 503 (embeddings unavailable) are shown | `GET /admin/index/status`, `POST /admin/index/rebuild` |

* **Not offered because the backend has no endpoint:** user search, user details or profiles, account
  activation/deactivation, skill management, audit logs, a statistics endpoint and rebuild progress.
* Phone numbers and UUIDs returned by `/admin/users` are not displayed. Resume files are not accessible.

## Career assistant (F9)

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/assistant` | Empty state with suggested questions; the first message creates a conversation | `GET /assistant/capabilities`, `POST /assistant/conversations`, `POST /assistant/conversations/{id}/messages` |
| `/assistant/:conversationId` | Saved conversation: messages oldest first, "Load earlier messages", refresh, rename, delete (confirmed); conversation list with paging | `GET /assistant/conversations?skip=&limit=`, `GET /assistant/conversations/{id}`, `GET …/{id}/messages?before_id=&limit=`, `PATCH`/`DELETE /assistant/conversations/{id}` |
| `/` (dashboard) | Recent conversations link to `/assistant/:id`; "Ask the assistant" starts a new one | `GET /assistant/conversations?limit=3` |

* Message request `{message (1–2000, not blank), use_llm, llm_consent}`; response `{conversation_id,
  user_message, assistant_message}` with `content`, `sources[{type, id, label, available}]`,
  `result_set`, `suggested_actions`, `generation_method`, `warnings`, `created_at`. No streaming.
* **Grounding:** sources and result items are shown as returned. Each links to the matching page only
  when the type and id map to an existing route (`/resumes/:id`, `/internships/:id`, `/documents/:id`,
  `/interview-prep/sessions/:id`, `/applications/:id`, `/matches`, `/skill-gaps`…); unavailable or
  unmappable sources are shown without a link. Answers without sources say so.
* **Suggested actions** are backend API calls the assistant never performs; they are shown as links to
  the existing page where the student can do it themselves (e.g. `/documents?type=resume&internship=`).
  Unknown endpoints are not shown.
* **AI is off by default.** The option appears only when `capabilities.llm.available`; it shows the
  backend's assistant disclosure and needs a separate consent box before `use_llm`/`llm_consent` are sent.
* Failed sends keep the typed text and offer Try again (in the same conversation); 429 shows the
  backend's wait time; 409 (conversation full) offers a new conversation.

## Application tracking (F8)

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/applications` | Overview (totals, counts by status, rates with the backend's formulas, upcoming interviews, reminder counts, recent activity); list with status filters, search, sort and paging done by the backend (filters in the URL); add an application from outside the catalogue | `GET /applications/dashboard`, `GET /applications?status=&q=&sort=&order=&skip=&limit=`, `POST /applications` |
| `/applications?tab=saved` | Saved internships: open, mark as applied, remove (confirmed) | `GET /applications/bookmarks`, `DELETE /applications/bookmarks/{iid}`, `POST /applications` `{internship_id, status}` |
| `/applications?tab=reminders` | Stored reminders (pending / done / all): mark done, delete (confirmed) | `GET /applications/reminders?status=`, `PATCH`/`DELETE /applications/reminders/{id}` |
| `/applications?tab=trash` | Restore, or delete permanently (type DELETE) | `GET /applications/trash`, `POST /applications/{id}/restore`, `DELETE /applications/{id}/permanent?confirm=true` |
| `/applications/:id` | Details and edit, status change and undo, history and activity, company interview rounds, reminders, related match / documents / practice sessions, move to trash (confirmed) | `GET`/`PATCH /applications/{id}`, `PATCH /applications/{id}/status`, `GET /applications/{id}/history`, `GET`/`POST /applications/{id}/interviews`, `PATCH`/`DELETE /applications/interviews/{iid}`, `POST /applications/{id}/reminders`, `DELETE /applications/{id}?confirm=true` |

* **Statuses and transitions** are the backend's (`SAVED`, `APPLIED`, `SHORTLISTED`, `INTERVIEW_SCHEDULED`,
  `SELECTED`, `REJECTED`, `WITHDRAWN`). Only allowed transitions are offered; every change sends
  `expected_status`, so a stale page gets a 409 instead of overwriting. Decisions (Selected, Rejected,
  Withdrawn) and corrections are confirmed. "Undo last change" sends `correction: true`.
* Adding a company interview round can move the status to Interview scheduled, and cancelling or
  deleting the last round can move it back; the backend reports this and the page shows it.
  Company interviews are separate from F7 practice sessions.
* **Reminders are stored only.** The backend never sends them (`delivery: "not_sent"`); the UI says so.

## Interview preparation (F7)

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/interview-prep` | Start a session (resume, optional internship, practice/mock mode, difficulty, question mix, mock time limit, optional AI-tailored questions); session history with status filter (`?show=`); question-bank statistics | `POST /interviews/sessions`, `GET /interviews/sessions?status=`, `GET /interviews/question-bank/version`, `GET /documents/llm-status`, `GET /resumes/`, `GET /internships/`, `GET /internships/{id}` |
| `/interview-prep/sessions/:id` | Questions one at a time with a navigator (`?q=`), answered/unanswered markers, drafts kept while navigating and on errors, answer evaluation, retries, mock-mode reveal, all attempts, finish (confirmed) with the backend's results, delete (confirmed) | `GET /interviews/sessions/{id}`, `POST …/questions/{qid}/answers`, `GET …/questions/{qid}/answers`, `POST …/questions/{qid}/reveal`, `POST /interviews/sessions/{id}/complete`, `DELETE /interviews/sessions/{id}` |
| `/` (dashboard), internship detail | Latest session (status, score), links to start and to the history; "Practise interview questions" (`?internship=ID`). `/interviews` redirects to `/interview-prep` | `GET /interviews/progress`, `GET /interviews/sessions` |

* Request fields: session `{resume_id, internship_id, mode practice|mock, mix{technical 0–10, project 0–5,
  behavioral 0–5, internship 0–5; total 1–15}, difficulty mixed|easy|medium|hard, time_limit_seconds
  (30–900, mock only), use_llm, llm_consent}`; answer `{answer_text (1–5000, not blank),
  time_taken_seconds, use_llm_feedback, llm_consent}`.
* **Scoring is the backend's rubric.** Scores, labels, covered/missed key points, STAR checks, tips and
  the session summary are shown as returned. The overall score is the backend's (unanswered questions
  count as 0); the frontend computes no scores.
* **AI is off by default** for both question generation and feedback. It is offered only when
  `GET /documents/llm-status` reports a provider; the disclosure is shown and a separate consent box
  must be ticked before `use_llm`/`use_llm_feedback` and `llm_consent` are sent as `true`.
* Not used: `GET /interviews/questions/preview`. The backend has no endpoint to restart or abandon a
  session, so "Practise again" starts a new one.

## Resume and cover letter customization (F6)

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/documents` | Create a tailored resume or cover letter from a parsed resume (latest by default) and a chosen internship; history with All / Resumes / Cover letters filter (`?show=`) | `GET /documents/llm-status`, `POST /documents/resume`, `POST /documents/cover-letter`, `GET /documents?type=`, `GET /resumes/`, `GET /resumes/{id}/skills`, `GET /internships`, `GET /internships/{id}` |
| `/documents/:id` | Review: preview, provenance ("Built from your original resume"), fact-check results, ATS summary (resumes), edit wording as a new version, version history and restore, DOCX/TXT download, delete (confirmed) | `GET /documents/{id}`, `PATCH /documents/{id}`, `GET /documents/{id}/versions`, `POST /documents/{id}/versions/{v}/restore`, `GET /documents/{id}/download?format=docx\|txt`, `DELETE /documents/{id}` |
| Links | `?type=resume\|cover_letter`, `?internship=ID`, `?resume=ID` pre-fill the form; used by the internship detail page, the resumes page and the dashboard match card | — |

* Request fields: resume `{resume_id, internship_id, options{max_skills 5–30, max_projects 0–6,
  max_experience 0–8, max_bullets 1–6}, use_llm, llm_consent}`; cover letter `{resume_id, internship_id,
  tone formal|concise, emphasize_skills (≤10, skills on the resume), use_llm, llm_consent}`.
* **AI is off by default.** Documents are generated deterministically from facts on the resume
  (`use_llm: false, llm_consent: false`). The AI option appears only when `llm-status` reports a
  configured provider; turning it on shows the backend's disclosure and requires a separate consent
  checkbox before `use_llm: true, llm_consent: true` is sent. Turning AI off clears consent.
* Fact-check results come from the backend (`fact_check`): checked statements, warnings, rejected
  statements with reasons, AI accepted/rejected counts. Items backed by resume facts are marked
  "From your resume". The frontend never generates or alters document text itself; edits are saved
  by the backend as a new, re-checked version.

## Skill gap analysis (F5)

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/skill-gaps` | Skills on the latest parsed resume; learning plan (recommendations in backend priority order) with status filters in the URL; per-skill learning plan; progress updates | `GET /resumes/{id}/skills`, `GET /skill-gaps?resume_id=`, `PATCH /skill-gaps/{id}` |
| | "Analyse my top matches" (top 3/5/10/20 of the latest match run) | `POST /skill-gaps/resumes/{rid}` `{top_k}` |
| `/skill-gaps/internships/:id` | Required/preferred coverage from the backend summary, missing / partly / matched skills, learning order and plans, compact match breakdown, "Use for my learning plan" (confirmed) | `GET /skill-gaps/resumes/{rid}/internships/{id}`, `GET /matches/resumes/{rid}/internships/{id}`, `POST /skill-gaps/resumes/{rid}` `{internship_ids}` |
| `/` (dashboard) | Next recommendation to learn, required and preferred missing counts for the best match, links | existing dashboard calls |

* Progress statuses (`pending`, `in_progress`, `completed`, `dismissed`) are persisted by the backend; the
  card shows the returned record. "Detected on your resume" = `completed_via: "resume"`.
* Learning plans show only backend fields (level, estimated hours, prerequisites, topics). The backend
  provides **no learning resources or URLs**, so none are shown; non-curated plans are labelled
  "General outline" and have no time estimate.
* Generating recommendations replaces the *current* set (progress on skills still needed is kept), so
  basing the plan on one internship asks for confirmation first.

## Internship discovery and RAG-based matching (F4)

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/internships` | Browse: keyword (title/company/description), skill, domain, location and work-mode filters, sorting, pagination, clear all | `GET /internships/`, `GET /internships/filters` |
| `/internships?view=search` | AI search over the embedding (FAISS) index, example queries, similarity %; 503 = index unavailable | `GET /internships/search?q&k` |
| `/internships/:id` | Full details; Save for later; Mark as applied; Check my match (latest parsed resume) | `GET /internships/{id}`, `GET/POST/DELETE /applications/bookmarks/{id}`, `POST /applications`, `GET /matches/resumes/{rid}/internships/{id}` |
| `/matches` | Latest run in rank order with score breakdowns, run with top-k / work mode / location, run history | `GET/POST /matches/resumes/{rid}`, `GET /matches/resumes/{rid}/history`, `GET /matches/runs/{run_id}` |

* The list API has no sort parameter (fixed id order). Choosing a sort loads every matching internship
  (pages of 100) and sorts in the browser; the default order uses server pagination.
* Filter, sort, page and search state live in the URL. Semantic similarity is labelled as such and is
  never presented as a match score; match scores come only from the matching engine.
* "Mark as applied" sends `{internship_id, status: "APPLIED"}`; the backend copies the internship details
  and sets `applied_at`. A 409 (already tracked) links to Applications.

## Resume management and student profile (F3)

| Route | Feature | Backend endpoint(s) |
|---|---|---|
| `/resumes`, `/resumes/:id` | List all resumes (Latest / Used for matching), details of the selected one | `GET /resumes/`, `GET /resumes/{id}` (404 "Parsed resume information not found" = no successful extraction) |
| | Upload by drag-and-drop or browse, PDF/DOCX ≤ 5 MB, progress, one upload at a time | `POST /resumes/upload` (parses in the same request) |
| | Re-parse the stored file (earlier data stays in use if it fails) | `POST /resumes/{id}/reparse` |
| | Download the original file | `GET /resumes/{id}/download` |
| | Delete after typing DELETE (explains everything that is removed) | `DELETE /resumes/{id}` |
| `/profile` | Completeness from real data, read-only account details, academic profile form, extracted resume data shown separately | `GET/POST /profiles/…`, `PATCH /profiles/me`, `GET /resumes/`, `GET /resumes/{id}` |

* Resume statuses come only from the backend (`completed`, `failed`, `uploaded`); "Reading your resume…"
  is shown while the upload request is parsing, because the backend has no separate processing state.
* Extracted sections are shown exactly as parsed (`{details: "…"}` entries); empty core sections say
  "No … found in this resume". Only http(s) links are rendered as links.
* The profile form saves only changed fields (clearing a field sends `null`) and never copies resume
  data automatically; "Use resume address as location" only fills the form.
* Name, email and phone have no update endpoint and are shown read-only.
* The dashboard and matching use the latest *successfully parsed* resume.

## Student dashboard (F2)

`/` shows the signed-in student's dashboard inside the app shell (desktop sidebar, mobile/tablet
navigation drawer, profile menu with sign-out, skip link). Every section loads on its own with
loading, empty, error and "Try again" states; an expired session is handled by the shared API
client (refresh once, otherwise sign out and return to `/login?next=…`).

| Section | Backend endpoint(s) | Notes |
|---|---|---|
| Resume (upload + latest status) | `GET /resumes/`, `POST /resumes/upload` | PDF/DOCX ≤ 5 MB checked before upload; newest resume is used |
| Best internship match | `GET /matches/resumes/{id}` (404 = not run yet), `POST /matches/resumes/{id}` | Compatibility score 0–100 from the matching engine |
| ATS check | `GET /documents/resumes/{id}/internships/{iid}/ats-report` | Resume checks + keyword coverage for the best match. **The backend has no overall ATS score**, and the match score is never shown as one |
| Skills & gaps | `GET /resumes/{id}/skills`, `GET /skill-gaps/resumes/{id}/internships/{iid}`, `GET /skill-gaps?resume_id=` | Total skills, required-skill gap for the best match, learning-plan progress |
| Interview preparation | `GET /interviews/progress`, `GET /interviews/sessions` | Average practice score (0–100 rubric), sessions, strongest/weakest category, latest session status and score (F7) |
| Applications | `GET /applications/dashboard`, `GET /applications?sort=updated_at&order=desc&limit=5` | Totals, next interview, recent applications with status |
| Career assistant | `GET /assistant/conversations?limit=3` | Entry point to `/assistant` with recent conversations |

All of these endpoints scope data to the signed-in user on the server; the browser never sends a user id.

## Authentication screens (F1)

| Route | Screen | Backend endpoint(s) |
|---|---|---|
| `/login` | Sign in, "Remember me", password visibility, unverified-email resend | `POST /auth/login`, `GET /auth/me`, `POST /auth/resend-verification` |
| `/register` | Student registration (name, email, phone, password + confirmation) and pending-verification state | `POST /auth/register`, `POST /auth/resend-verification` |
| `/auth/verify-email?token=` | Verify email: success, expired, already used, invalid, server unavailable (retry) | `GET /auth/verify-email`, `POST /auth/resend-verification` |
| `/forgot-password` | Request a reset code (generic answer: never reveals whether an account exists) | `POST /auth/forgot-password` |
| `/reset-password[?token=]` | Reset with a pasted code (decision D3) or a `?token=` link | `POST /auth/reset-password` |

* `/auth/verify-email` matches the link the backend puts in the verification email
  (`{APP_BASE_URL}/auth/verify-email?token=…`); set `APP_BASE_URL` to the frontend URL in development.
* One-time tokens are read once and removed from the address bar. A verification token is sent to
  the backend exactly once per page load, even under React StrictMode.
* `/login`, `/register` and `/forgot-password` send a signed-in user on to `?next=` (validated) or the dashboard.
* After a password reset the backend revokes every session, so the browser's copy is cleared too.
* Phone number is required because the backend's `UserCreate` schema requires it.
* New passwords: 8–128 characters (backend rule) plus at least one letter and one number (client-side
  floor). Sign-in never applies the new-password rules.

## Stack

| Purpose | Package (exact version) |
|---|---|
| UI | React 18.3.1, React DOM 18.3.1 |
| Routing | React Router DOM 7.18.5 (declarative `<BrowserRouter>` mode) |
| HTTP | Axios 1.21.0 |
| Build / dev server | Vite 7.3.8, @vitejs/plugin-react 5.2.0 |
| Styling | Tailwind CSS 3.4.19, PostCSS 8.5.32, Autoprefixer 10.6.2 |
| Tests | Vitest 5.1.0, jsdom 25.0.1, React Testing Library 16.3.3 (+ @testing-library/dom 10.4.2, jest-dom 6.10.0, user-event 14.6.8), MSW 2.15.0 |

Versions are pinned exactly in `package.json`; `package-lock.json` is committed.

## Requirements

* Node.js 22.12 or newer (developed with Node 22.22.2) and npm 10. Vite 7 needs Node 20.19+/22.12+ and
  Vitest 5 needs Node 22.12+.
* The FastAPI backend running on `http://127.0.0.1:8000` for live use (tests do not need it).

## Install and run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Other scripts:

```bash
npm test             # run all tests once (Vitest + React Testing Library + MSW)
npm run test:watch   # re-run tests on change
npm run build        # production build into dist/
npm run preview      # serve the production build on http://localhost:4173
```

Open `http://localhost:5173/health` to check that the browser can reach the backend.

## How the frontend talks to FastAPI

```
Browser ──► http://localhost:5173/api/auth/login ──(Vite proxy)──► http://127.0.0.1:8000/auth/login
```

* All API calls use the base URL `/api` (`VITE_API_BASE_URL`, see `.env.example`).
* In development the Vite dev server forwards `/api/*` to FastAPI and strips the `/api` prefix
  (`vite.config.js`). The browser only talks to `localhost:5173`, so there is no CORS and
  headers such as `Content-Disposition` (download file names) and `Retry-After` are readable.
* Point the proxy at another backend with `BACKEND_URL=http://host:port npm run dev`.
* The dev server listens on `localhost` only.

### Running the backend for frontend development

The backend reads `.env` without overriding variables that are already set in the process, so
a development backend can be pointed at a separate database and index **without editing `.env`**
(decision D1/D2; the `career_companion_dev` database is set up in a later step):

```bash
DB_NAME=career_companion_dev FAISS_INDEX_DIR=<dev index folder> APP_BASE_URL=http://localhost:5173 \
  .venv/Scripts/python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## Authentication design

* **Access token:** kept in memory only (`src/api/client.js`) and sent as `Authorization: Bearer …`.
* **Refresh token:** `sessionStorage` by default; `localStorage` only when "Remember me" is ticked
  (`src/utils/storage.js`). Passwords are never stored.
* **Expired access token:** the Axios interceptor refreshes once and retries the request. Requests
  that fail at the same time share a single refresh call, because the backend rotates refresh
  tokens (a second parallel refresh would use a revoked token).
* **Failed refresh:** the session is cleared and protected pages redirect to `/login?next=…`.
  The `next` value is only honoured for same-app paths (`src/utils/redirect.js`).
* **Roles:** `ProtectedRoute` requires a signed-in user; `RoleRoute` shows a 403 page to
  non-admins. The backend enforces the same rules.

## Error handling

`src/api/errors.js` turns every failure into an `ApiError` with `status`, `message`,
`fieldErrors` (from FastAPI 422 validation lists), `detail` (for object details such as a 409
duplicate with the existing id) and `retryAfter` (429). Network failures get a friendly message;
technical details are never shown.

## Project structure

```
src/
  api/          client.js (Axios + interceptors), errors.js, auth.js, dashboard.js, resumes.js,
                profile.js, internships.js, matches.js, applications.js (bookmarks + F8 tracking), skillGaps.js, documents.js, interviews.js, assistant.js, admin.js,
                system.js
  context/      AuthContext, ToastContext, ConfirmContext (promise-based confirm dialog)
  routes/       AppRoutes (lazy pages), PageBoundary, ProtectedRoute, RoleRoute, GuestRoute, navigation.js
  layouts/      AppLayout (sidebar, mobile drawer, top bar), ProfileMenu, AuthLayout (brand panel + form card)
  hooks/        useApiResource (per-section loading / error / retry state)
  components/ui Button, Input, Select, Checkbox, Card, Badge, Icon, Spinner, Modal, ConfirmDialog,
                ErrorAlert, EmptyState, Pagination
  components/brand  BrandMark (logo)
  features/     system/ (Health, NotFound, Forbidden, ComingSoon)
                resumes/ ResumesPage, ResumeUploader, ResumeDetail, resumeData.js, resumeFile.js
                profile/ ProfilePage, profileForm.js
                internships/ InternshipsPage, BrowseInternships, SemanticSearch,
                             InternshipDetailPage, InternshipCard, internshipFormat.js
                matches/ MatchesPage, MatchBreakdown
                skillGaps/ SkillGapsPage, InternshipGapPage, RecommendationCard, LearningPlan,
                           gapFormat.js
                documents/ DocumentsPage, DocumentDetailPage, documentFormat.js, components/
                           (CreateDocumentForm, InternshipPicker, AiAssistChoice, DocumentPreview,
                            DocumentEditor, FactCheckPanel)
                interviews/ InterviewPrepPage, InterviewSessionPage, interviewFormat.js, components/
                            (StartSessionForm, QuestionCard, EvaluationView, SuggestedAnswer,
                             SessionSummary)
                applications/ ApplicationsPage, ApplicationDetailPage, applicationFormat.js, components/
                             (ApplicationSummary, ApplicationList, NewApplicationForm, SavedInternships,
                              RemindersPanel, ReminderItem, TrashPanel, StatusControl, InterviewRounds,
                              ApplicationReminders, DetailsEditor, HistoryTimeline)
                assistant/ AssistantPage, assistantFormat.js, components/ (MessageBubble, Composer,
                           ConversationList)
                admin/ AdminOverviewPage, AdminUsersPage, AdminInternshipsPage, AdminInternshipFormPage,
                       AdminIndexPage, adminShared.jsx
                dashboard/ DashboardPage, format.js, components/ (Resume, Match, Ats, Skills,
                           Interview, Applications, Assistant cards; DashboardCard; ScoreRing)
                auth/ Login, Register, VerifyEmail, ForgotPassword, ResetPassword pages,
                      useAuthForm, useTokenFromUrl, validation.js,
                      components/ (PasswordInput, PasswordRequirements, ResendVerification,
                                   StatusPanel, AuthHeader)
  utils/        storage.js, dates.js, redirect.js, saveBlob.js
  test/         setup.js, server.js, handlers.js (MSW)
```

## Testing

Tests run in jsdom with MSW intercepting every request; an unhandled request fails the test,
so no test can reach a real backend or database.

## Security notes

`npm audit` reports **0 vulnerabilities** (dependencies upgraded to Vite 7.3.8, Vitest 5.1.0 and
React Router 7.18.5). Defence in depth that stays in place:

* the dev and preview servers bind to `localhost` only;
* the Vitest UI and browser mode are not installed or used (`npm test` runs headless in Node);
* redirect targets (`?next=`) are validated before navigation (`src/utils/redirect.js`).

Nothing sensitive is configured in the frontend: anything in `VITE_*` variables is public.
