# CareerNova AI — Final QA Report

Date: 2026-11-24 · Scope: P0–P3 · All database tests on `career_companion_test` · `career_companion_dev`
verified untouched (revision `b2e8c4a7d1f5`, 2 users, 11 resumes, 180 internships; read-only check).

## 1. Test results (exact)

| Suite | Result |
|---|---|
| Backend, full (`pytest tests`) | **1140 passed, 0 failed, 0 skipped, 63 errors** (26 min) |
| — the 63 errors | all in the 5 real-model files (`test_answer_evaluation_real_model` 12, `test_assistant_intents_real_model` 14, `test_assistant_product_rag_real_model` 29, `test_embeddings_model` 3, `test_matching_real_model` 5). Cause: **Windows Smart App Control now blocks PyTorch's native DLL** (Code Integrity events 3077/3033 on 2026-11-24; 12 direct "Application Control policy has blocked this file" + 51 follow-on "torch can only be initialized once"). The same tests passed on 2026-11-19 (full run 1170 passed). Not bypassed. |
| Frontend, full (`vitest`) | **390 passed** (19 files) |
| Production build (`vite build`) | **OK** |
| End-to-end API journey (`tests/test_e2e_workflow.py`) | **passed** — invite → activate → sign in → upload → parse → correct → readiness → match + explore → skill progress → career track → assistant (+ provider failure fallback) → admin users/audit |
| Migration rehearsal (restored copy of the dev backup) | **passed** — full chain `b2e8c4a7d1f5 → c6d2a8f4b1e3 → d8e4b2c6a9f1 → e1f3a5c7b9d2`; counts and password hashes unchanged; no drift |

## 2. Live browser walkthrough (test database, local servers, outbox email)

Performed in the built-in browser against `career_companion_test` with throw-away test accounts
(passwords generated and kept in a scratch file; nothing sent by email):

| Step | Result |
|---|---|
| Super admin signs in; Admin → Users shows "Super admin · Protected · Active" | ✅ |
| Add user (Meera) → "Pending activation · Invitation sent · saved to the test outbox (not sent)" | ✅ |
| Outbox `.eml`: branded subject/sender, working `/accept-invitation?token=…` link | ✅ |
| Activation page: greets the user, removes the token from the URL, password rules, "Your account is active" | ✅ |
| Student signs in; dashboard prompts for a resume | ✅ |
| Two-column PDF resume uploaded (via the API — the pane cannot drive the OS file picker) → parsed correctly | ✅ |
| Resumes page: readiness **84/100 Good** with categories | ✅ no console errors |
| Matches → Explore: 180 sample listings, categories 3 / 38 / 139, sample-data label | ✅ |
| Career track (Data Analyst): coverage 6/8 (75%), official links, progress set to Learning **persisted after reload** | ✅ PUT 200 |
| Per-job roadmap shows the same Power BI "learning" status | ✅ all API calls 200 |
| Admin → Audit log lists bootstrap, user added, invitation, activation | ✅ (after fix 4 below) |
| Mobile width 375 px: no horizontal overflow | ✅ (after fix 5 below) |

Only console error seen: the expected `404` for "no matching run yet" (`GET /matches/resumes/{id}` before
the first run), which the app handles.

## 3. Bugs found and fixed (with regression tests)

| # | Bug | Root cause | Fix | Test |
|---|---|---|---|---|
| 1 | With the embedding model unavailable (torch blocked), product questions and semantic search could fail with raw `ImportError`/`OSError`, and torch was re-imported on every request | `get_embedder()` only raised `EmbeddingError` for its own checks | Any load failure → `EmbeddingError`, remembered until restart; product guide falls back to a keyword TF-IDF index with its own calibrated threshold (0.25: covered 0.28–0.59, uncovered ≤ 0.19, unrelated ≤ 0.18) | `tests/test_model_unavailable.py` (4) |
| 2 | Disabled-AI status gained a `location: null` key, breaking the existing response contract | P3 change added the key unconditionally | Key only present when a provider is configured; schema reverted | existing `test_llm_status_disabled_by_default` ×2 |
| 3 | Audit record for an internship edit listed the internal `dedup_key` as a changed field | the recomputed key was added to the change set | excluded from audit details | existing `test_admin_actions_are_audited_and_listed` |
| 4 | Audit log page showed raw codes (`user.activate`, `user.invite`) and could not filter them | label map predated P1/P3 actions | all 14 backend actions labelled and described | new "labels every backend audit action" |
| 5 | Mobile: job titles overlapped the category badge in Explore | flex row squeezed the title | title takes the full row below `sm` | verified live |
| 6 | (P3 build) Ollama first answer needs ~96 s on CPU; 30 s timeout failed | default timeout too short for local models | `OLLAMA_TIMEOUT_SECONDS` (default 120) | `test_ollama_provider.py` |

Earlier batches fixed: phone number merged with the next line, two-column PDFs read out of order,
empty resume scoring 3 instead of 0, inconsistent month counting, login page treating "deactivated"
as "unverified", "this application" routed to job-application data, pricing answered with an unrelated
overview, follow-up memory mixing topics.

## 4. Audit coverage

| Area | Evidence |
|---|---|
| Authentication, roles, throttling, deactivation | `test_auth`, `test_roles`, `test_admin_security` (25), `test_login_throttle` (10, incl. concurrency), `test_superadmin_cli` (13) |
| Invitations, password reset, activation, email | `test_invitations` (12), `test_mailer` (24), frontend activation tests (8) |
| Resume parsing, correction, readiness, duplicates | `test_resume_quality` (28), existing parser/lifecycle tests, frontend resume tests |
| Matching, Explore, application links, insights | `test_job_matching_modes` (13), existing matching tests, frontend matches tests |
| Skill-gap roadmap, career tracks, job sources | `test_p3_features` (14), frontend career-track/roadmap tests (5) |
| AI assistant, Groq, Ollama, fallbacks | assistant suites, `test_ollama_provider` (13), `test_model_unavailable` (4), live Gemma 3 call |
| Migrations | `test_migrations` (13) + rehearsal on restored data |
| Validation / errors / loading states | covered across API tests (422/404/409/429/410) and frontend tests (loading, empty, error, retry) |

## 5. Known limitations and unresolved items

1. **PyTorch is blocked by Windows Smart App Control on this machine** (since 2026-11-24). Effects: semantic
   search off, intent detection rule-based, product guide uses the keyword fallback, answer-evaluation
   uses its non-semantic path; 63 real-model tests cannot run here. Fix outside the code: allow the
   files through a policy the owner controls, or run on a machine/container where it is not blocked.
   Not bypassed.
2. The pending migrations are **not applied** to `career_companion_dev`; the new backend must not be
   started against it until they are (owner action).
3. Real email is not configured (`MAIL_FROM` placeholder); default mode only writes to the outbox.
4. No live job feeds; listings are the labelled sample dataset. No OCR for scanned PDFs.
5. Local Gemma 3 is slow on CPU (~1.5 min first answer).
6. Branding: the UI still shows "AI Career Companion" in titles and the sidebar (emails and new pages use
   "CareerNova AI"); a full rebrand/UI redesign (P4) was not done in this pass.

## 6. Owner actions required

1. Approve and run the migration (`FINAL_DATABASE_MIGRATION_CHECKLIST.md`), then `create-superadmin`.
2. Decide on Smart App Control for PyTorch (or run elsewhere); then `rebuild-index --apply` and restart.
3. Set a real `MAIL_FROM` and authorise `EMAIL_MODE=smtp` when ready.
4. Optionally drop the temporary database `careernova_restore_test_20261119_101233` (kept as instructed).
