# CareerNova AI — HR Assignment Test Report

Every result below was actually run. Automated tests used only `career_companion_test`, isolated temporary upload and
outbox folders, a fake LLM and blocked network. Live demos used the test database through an isolated backend (port
8001) and frontend (port 5174).

## Release preparation (2026-11-26)

### Fixes in this phase
| Issue | Root cause | Fix | Verification |
|---|---|---|---|
| Semantic internship search showed students internal messages (admin commands, model file names) on a 503 | `detail=str(exc)` | Plain student message; details logged for operators | `test_search_without_index_returns_503` now also asserts no internals |
| Guide counted Interview-assistant chats by loading every conversation | Python-side filter | One SQL `count` with the JSON filter | `test_app_guide.py` |
| Guide said "matching hasn't been run" when a run found no internships | Zero-result runs store nothing | Wording states only what the data proves ("no match results for this resume yet …") | `test_app_guide.py`; live G1 |
| Compare page: Compare button overflowed at 1280 px | `1fr` grid columns cannot shrink below long option text | `minmax(0,1fr)` columns, `min-w-0` children | Browser sweep 1280/768/375 px |
| Not-found and no-access pages had no heading | `EmptyState` title was a paragraph | Optional heading level; `h1` on both pages | `App.test.jsx` asserts the h1 |
| Generated artefacts and local config not ignored | Missing rules | `.gitignore`: `backend/data/faiss_index_*/`, evaluation console output, `.claude/launch.json` | `git check-ignore` |
| Managed PostgreSQL needs TLS | No SSL option | Optional `DB_SSLMODE` (unset locally = unchanged) | URL built with/without `sslmode`; full regression |
| No deployment configuration | - | `render.yaml` (backend), `frontend/vercel.json` (frontend), production steps in `DEPLOYMENT_AND_HANDOVER_GUIDE.md` §7 | Reviewed; not deployed yet |

### Environment finding (not an application defect)
In one full run (2026-11-26 18:40) the 12 tests of `test_answer_evaluation_real_model.py` errored at setup: Windows
Smart App Control blocked a SciPy DLL (`_biasedurn`) while the embedding model loaded (Code Integrity events
3077/3033 at 18:45:13). Smart App Control was **not** bypassed; the file passed 12/12 when rerun.

### Fresh results (this phase)
| Suite | Result |
|---|---|
| `test_app_guide.py` + `test_internships_api.py` (after the wording fix) | **59 passed** |
| Backend full suite (`career_companion_test`) | **1333 passed, 0 failed, 0 errors, 0 skipped (25 min 35 s)** |
| Frontend `vitest run --maxWorkers=2` | **414 passed, 0 failed (21 files, 136 s)** |
| Production build | **OK, 0 warnings (main bundle 364.28 kB / 116.33 kB gzip)** |
| Live scenarios A-J (test stack) | **30/30 checks passed (fresh test users; the curated internships were re-seeded into the test database because the full pytest run empties it)** |
| Browser sweep, 15 pages × 1280/768/375 px | **no horizontal overflow, an h1 on every page, no error alerts, no server errors** |

| Deep link | full page load of `/resumes/1` restored the session (refresh token) and rendered "Scored version: V1 · …" and 3 grouped projects |
| Session refresh | `/auth/refresh` returns a new (rotated) refresh token; the old one is rejected (401); the new access token works |
| CORS | allowed origin gets `Access-Control-Allow-Origin`; a foreign origin gets none (400) |
| `DB_SSLMODE` | `disable`/`prefer` connect to the local server; `require` is refused because the local server has no TLS - the setting reaches the driver as intended |
| Deployment configs | `frontend/vercel.json` and `render.yaml` parse as valid; **not deployed** - Vercel rewrites and Render settings are verified only at the first deployment |

## Final audit and stabilisation (2026-11-25/26)

All work below used `career_companion_test` (automated tests and live checks) and read-only checks on dev. Nothing was
committed, pushed or deployed.

### Issues found and fixed

| # | Issue | Root cause | Fix | Verification |
|---|---|---|---|---|
| 1 | A real resume with **3 projects showed 7** | `extract_project_entries` treated any line containing words such as "assistant", "system", "prediction", "application" as a new project title; the en-dash bullet "–" was not recognised, so bullets were not seen as descriptions; the right-aligned technology list was glued to the title (e.g. "…ApplicationPython — Flask") | Project grouping rewritten: description lines (any bullet marker, action-verb sentences, wrapped continuation lines, Word list paragraphs without a marker) can never start a project; titles need title-like shape; technologies split into a "Technologies:" line; wrapped lines re-joined | The owner's own resume (in memory, no DB write): **7 → 3 projects** with correct titles, technologies and all 8 bullets; 32 extraction tests (2/3/5/7 projects, PDF + DOCX, several bullet styles, two-column PDF); live scenario C |
| 2 | A second resume file on the same account: 3 → 2 entries after the fix | The old third "project" was one bullet ("Improved classification performance through model optimization.") split off by the keyword "optimization" | Same fix | Checked against what the Resumes page displayed for that file (owner present); its content was not opened again because it is another person's resume. **PARTIAL**: no ground-truth file in the test fixtures |
| 3 | Dated project headings: a date at the end of a technology list became a "technology" | No date handling in the title/technology split | Dates stay with the title ("Chat Application (Jan 2024)") | Test `test_dates_on_project_headings_stay_with_the_title…` |
| 4 | Identical project printed twice was stored twice | No de-duplication | Exact duplicates are kept once; similar-but-different projects are kept | Test `test_an_identical_repeated_project_is_kept_once…` |
| 5 | Titles ending with ":" kept the colon ("Churn Analysis:") | Not stripped | Trailing colon removed | Tests tightened to require the clean title; live E3 |
| 6 | **Re-parse silently replaced the student's corrections** | No warning in the UI | Re-parse on a corrected resume now asks first ("Re-parse and replace your corrections?"); Cancel keeps them; the original file is never changed | Frontend test + live browser check |
| 7 | Product guide said to fix extraction mistakes by re-uploading | Outdated text | Guide now explains Edit details, what Re-parse does and which version is used | Product-guide tests (68) |
| 8 | Readiness "always 69" | Not a bug in the calculation: dev contains only 3 distinct resume files and two of them score 69 (68.8 and 69.0) | The response and UI now name the scored version, flag versions with identical content and say profile details are not an input | 5 readiness tests; dashboard/resume UI tests; live D1/D2/D3 |
| 9 | Application Assistant lacked step-by-step workflow guidance | Only product-guide snippets | `app_guide` answers workflow questions with numbered steps, real pages and links, progress from the student's own records, follow-ups ("step 4", "what next?"); interview questions still redirect; off-topic still declined | 29 tests; live F1–F5, G1; browser check of links |
| 10 | Short off-topic question after a product question ("who is ronaldo") was answered from the product guide | ≤ 4-word messages were always treated as follow-ups | `is_unrelated_topic()` | 6 test cases; live F4 |
| 11 | Application Assistant chip "Help me prepare for an interview" sent a message only to be redirected | Chip was a send button | Chip links to the Interview Preparation Assistant | Frontend test |

### Decisions (not defects)
- "How do I upload my resume?" stays a product-guide answer (file types, size, what is extracted); the new guide covers the workflow questions.
- Re-parsing existing dev resumes was **not** done: the fixed parser applies to new uploads, and to existing resumes only when the owner presses Re-parse (the dev backend must be restarted first to load the new code).

### Final results (2026-11-26)

| Suite | Result |
|---|---|
| Backend `pytest tests` (test database) | **1333 passed, 0 failed, 0 errors, 0 skipped (33 min 00 s; started 01:04, after the title-colon fix). Fixtures renamed to fictional projects at 01:07 were re-run afterwards: extraction, resume-quality, versions and readiness files 78 passed** |
| Backend run before the last small fix (title colon) | 1333 passed, 0 failed, 0 errors, 0 skipped (28 min 31 s) |
| Frontend `vitest run --maxWorkers=2` | **414 passed, 0 failed** (21 files, 153 s) |
| Production build | **OK, 0 warnings** (main bundle 116.3 kB gzip) |
| Live scenarios A-J (test backend :8001, test database, outbox email) | **30/30 checks passed** (fresh test users; one assistant 429 rate-limit response retried as designed) |
| Browser check (test frontend :5174) | dashboard tile "70/100 Good · V3 Five projects"; Resumes page: 3 grouped projects with Technologies lines, "Scored version: V1 · …"; Re-parse confirmation on a corrected resume (cancelled - corrections kept); Application Assistant guide with working links (/profile, /resumes, /matches, /skill-gaps, /interview-assistant); no horizontal overflow at 375 px on dashboard, resumes, assistant |

New backend tests in this audit: `test_project_extraction.py` 32, `test_app_guide.py` 29, `test_readiness_versions.py` 5
(1267 → 1333). One existing comparison test was updated because it asserted the old merging limitation (V2's two
projects merged into one); the new behaviour (two separate projects) was verified independently. Frontend 411 → 414.

Live scenario detail (all PASS): A new user, guide before/after profile · B PDF upload parsed · C 3 projects → 3 entries,
titles, technologies, bullets, original file unchanged · D readiness names V1, identical upload flagged with the same score,
correction raises the score 68 → 72, re-parse returns the parser's version · E DOCX 5 projects → 5, named + preferred,
comparison reports 2 added projects and a measured verdict · F numbered 10-step guide with real status, links, step
follow-up, off-topic declined, interview questions redirected · G internship guidance with real match status · H roles
from the preferred resume, Data Analyst technical questions with SQL, separate conversation lists · I PDF + DOCX study
documents, one answer citing both, honest not-found · J second user 404 on 7 resources, no token 401.

## 1. Summary (2026-11-25; final figures after the post-migration fixes are in section 1b)

| Suite | Baseline (2026-11-24) | Now |
|---|---|---|
| **Backend, full suite** (`pytest tests`) | 1238 passed | **1267 passed, 0 failed, 0 errors, 0 skipped** (final; 1261 before the post-migration fixes) |
| **Frontend** (`vitest run`) | 402 passed (20 files) | **411 passed, 0 failed** (21 files, `--maxWorkers=2`; 410 before the chip fix) — see "Frontend timing" below |
| **Frontend production build** (`vite build`) | OK | **OK**, no warnings (main bundle 364 kB / 116 kB gzip; AssistantPage 11.7 kB gzip) |
| Live demos 1–6 (test database, port 8001/5174) | — | **Passed** (see `CAREERNOVA_DEMO_GUIDE.md`) |
| RAG evaluation (`python -m evaluation.study_rag_eval`, idle machine) | — | completed; `docs/assignment/evaluation/STUDY_RAG_EVAL.md` + `study_rag_eval_console.txt` (results in `CAREERNOVA_IMPLEMENTATION_REPORT.md` §5) |

**Why the counts changed (no test was removed or weakened):**
- Backend +29 in total: +23 listed here, +6 from the post-migration fixes (section 1b):
  - `test_profile_and_versions.py` (new) +13;
  - `test_study_documents.py` 19 → 24 (+5: several documents, agentic retrieval, chunking settings);
  - `test_prep_agent.py` 14 → 18 (+4: separate assistant scopes, every interview-prep wording redirected, internships/priorities, problem-solving + practice
    questions, role-only mock questions);
  - `test_migrations.py` 14 → 15 (+1: profile/resume-version migration).
- Frontend +9 in total: +8 here and +1 from the chip fix (section 1b). The +8: `versions.test.jsx` (new) +6 and `prepAgent.test.jsx` +2 (assistant separation). Some existing
  expectations in `assistant.test.jsx` / `dashboard.test.jsx` were updated for the new names and routes (same checks).

**Regressions found by the first full run and fixed (code fixed, tests unchanged):**
1. `test_assistant_answers::test_learning_plan_and_missing_skill_clarification` — the Application Assistant redirected
   "give me a learning plan" to the Interview assistant instead of asking which skill. Generic learning-plan, skill-gap
   and question-bank requests are answered by the Application Assistant again, as before the split (final rule below).
2. `test_assistant_privacy_cascades::test_context_stores_pointers_only` — new Application Assistant chats stored an
   `assistant` marker in the conversation context. They now keep the original empty context; only interview chats are
   marked.

Run history (all on `career_companion_test`):
1. First full run: **2 failed, 1258 passed** (27 min) — the two regressions above.
2. After the fix: `test_assistant*.py`, `test_prep_agent.py`, `test_study_documents.py` → **272 passed**.
3. Second full run: **stopped at 58% with no failures** — Windows began a power-off at 01:34:11 and the PC slept until
   11:06 (System log: User32 1074, Kernel-Power 42/107). Not a test result.
4. Third full run (machine kept awake): **1260 passed, 0 failed**.

**Third issue, found by a manual routing check after run 4 (not by a test):** the fix for regression 1 was too
broad. "Give me HR interview questions", "Start a mock interview" and "Create my preparation roadmap" stayed in the
Application Assistant because the old intent classifier maps them to shared tools. Fixed with `stays_in_application()`
(only generic learning-plan / skill-gap wording without interview/prep/roadmap/mock/HR words stays), and a new test
`test_application_assistant_redirects_every_interview_prep_wording` now guards it. Because the code changed, the full
backend suite was run once more:
5. Full run after the routing fix: **1261 passed, 0 failed** (32 min 30 s).
6. **Final full run after the post-migration fixes: 1267 passed, 0 failed, 0 errors, 0 skipped** (60 min 48 s).

**Frontend timing.** With vitest's default parallelism (12 logical cores) the full suite twice reported timeouts
(16 failures while the backend suite was also running; 7 on the otherwise idle machine) in `auth`, `admin`,
`prepAgent` and `dashboard` tests: "Test timed out in 15000ms" / element not found within the wait. The four files pass
alone (118/118, 33 s) and the whole suite passes with `--maxWorkers=2` (410/410). No test or timeout was changed.
This is a test-runner load sensitivity on this laptop, not a functional failure; CI should limit workers.

**Two assistants stay separate** (checked in the final runs): `test_two_assistants_keep_separate_scopes`, the redirect
tests, `test_context_stores_pointers_only` and the 2 frontend separation tests all pass.

## 1b. Post-migration fixes and final regression (2026-11-25, afternoon)

Found during the signed-in check on dev; reproduced and fixed **on `career_companion_test` only**.

| Finding | Root cause | Fix | Tests |
|---|---|---|---|
| "who is ronaldo" right after a product question was answered with product-guide text | any message of ≤ 4 words counted as a follow-up and was merged with the previous product question | `product_help.is_unrelated_topic()`: a short message that doesn't refer back (it/that/this…) and shares no word with the guide is not a follow-up; real follow-ups ("how big can it be?") keep the memory | reproduced first (4 new tests failed), then: `test_short_unrelated_question_after_a_product_answer_is_declined` (DB flow) + 3 real-model tests (5 cases) |
| Application Assistant chip "Help me prepare for an interview." sent a message that was only redirected | the chip was a send button | the chip is a link to `/interview-assistant`; the backend redirect and both scopes are unchanged | new frontend test (navigates, 0 messages, 0 conversations); count test now checks 5 buttons + 1 link |
| V2–V4 of one dev account have the same name; extracted contact differs from the account | diagnosis only (read-only): the same PDF was uploaded three times (identical SHA-256, 18:19 / 18:45 / 19:00 on 2026-11-24) - allowed by design and reported as a duplicate; the file is another person's resume, and the parser reads the file, never the account | no code change, no data change | — |

Final regression after these fixes (test database; frontend with 2 workers):

| Suite | Result |
|---|---|
| Backend `pytest tests` | **1267 passed, 0 failed, 0 errors, 0 skipped** (60 min 48 s; slower than the 32-min run because of other load on the PC) |
| Frontend `vitest run --maxWorkers=2` | **411 passed, 0 failed** (21 files, 129 s) |
| Production build | **OK**, 0 warnings (main bundle 116.3 kB gzip; AssistantPage 11.8 kB gzip) |

## 2. New and affected backend tests

| File | Tests | Covers |
|---|---|---|
| `tests/test_profile_and_versions.py` (new) | 13 | Avatar upload, replace, serve and remove; avatar validation (6 parametrised bad files); avatars private; bio create/update/clear/validate; versions kept, named, one preferred; comparison with measured evidence; comparison with an internship (ATS report); comparison validation and isolation |
| `tests/test_prep_agent.py` | 18 | As before plus: two assistants keep separate scopes and redirect; every interview-prep wording in the Application Assistant is redirected while a generic learning plan is not; internships and preparation priorities per role; problem-solving HR questions and roadmap practice questions; mock interview limited to the role's skills |
| `tests/test_study_documents.py` | 24 | As before plus: several documents in one chat with file-named citations (max 5, owner check), multi-document ask API, agentic retrieval for multi-part questions, chunk-size/overlap settings |
| `tests/test_migrations.py` | 15 | Single head `a7c9e1b3d5f6`; profile/resume-version migration keeps existing rows unchanged, enforces one preferred resume, downgrade refuses while new data exists |

## 2b. Security results

- Demo 6 (live, port 8001): a second student got **404** on the first student's resume detail, download, readiness,
  comparison, rename, study document, document questions (single and multi), attaching that document, both kinds of
  chats, prep roles and interview session; **401** without a token for avatar, documents and comparison.
- Avatars: content checked by magic bytes and dimensions, stored in a per-user folder, never served by path.
- Study-document text is passed to the optional AI as data; instructions inside documents are ignored (tested).

## 2c. Earlier results (2026-11-24, kept for reference)

| Suite | Result |
|---|---|
| **Backend, full suite** (`pytest tests`, after all changes) | **1238 passed, 0 failed, 0 errors, 0 skipped** |
| **Frontend** (`vitest run`) | **402 passed** (20 files) |
| **Frontend production build** (`vite build`) | **OK** — main bundle 115 kB gzip; AssistantPage chunk 10.8 kB gzip |
| Live demo A (resume → roles → questions → guidance → roadmap) | **Passed** |
| Live demo B (PDF and DOCX upload → grounded Q&A, incl. local AI) | **Passed** |
| Live demo C (role-based mock interview → feedback → summary) | **Passed** |

- **Backend run duration:** 3 h 34 min wall clock. The PC was in standby/sleep from about 21:02 to 23:51 during the
  run (Windows Kernel-Power events 42/506/507/107), so the actual test time was about 45 minutes.
- **Real-model tests:** all 63 ran and passed. PyTorch loads again on this machine.
- **No linter or type checker** is configured in this project, so none was run.

### Earlier backend tests (2026-11-24; counts since extended as listed in section 2)

| File | Tests | Covers |
|---|---|---|
| `tests/test_prep_agent.py` (new) | 14 | Role ranking with reasons and evidence; role fit for an uncovered role; technical questions by level (resume skills first + a missing core skill); HR questions personalised from the resume; guidance separating samples from verified resume facts; "Tell me about yourself" draft with placeholders only; roadmap priorities; 401 / 409 `resume_required` / 404 for another student's resume or an unknown role; chat flow resume → roles → select role → technical → guidance → HR → guidance → roadmap; strengths, weaknesses, role fit and "learn to become"; choosing a role by ordinal ("the second one"); student without a resume; other assistant intents still routed correctly; role detection; **role-based mock interview: session, answer, feedback, completion summary, unknown role 422** |
| `tests/test_study_documents.py` (new) | 19 | Valid PDF (page references) and DOCX (sections and tables); empty, wrong type (415), fake PDF, corrupted PDF, corrupted DOCX, scanned PDF (no OCR); >10 MB (413); duplicate (409); partly scanned PDF warning; answer with page reference; question not in the document; summary, concepts, interview questions, revision notes; AI answer grounded and cited, document instructions ignored, unsupported or uncited AI answers rejected; consent required; chat attach, follow-up, resume questions still routed to the agent, detach; deleted document → old sources unavailable; owner-only access (401/404, cannot attach or read another user's chat); no AI call without opt-in |
| `tests/test_migrations.py` (updated) | 14 | New single head `f2b4d6a8c0e1`; study-documents migration is additive, downgrade refuses while documents exist, cascade on user delete, no model/migration drift |
| `tests/test_p3_features.py` (updated) | — | 14 career tracks with complete content |

## 3. Frontend tests

New on 2026-11-25:
- `src/features/resumes/versions.test.jsx` (6): versions listed with names, set preferred and rename; the preferred
  parsed version is used for matching; comparison shows measured differences and the verdict; comparison needs two
  parsed versions; picture upload shown in the header + bio saved; picture files checked before upload.
- `prepAgent.test.jsx` +2: the two assistants keep separate conversation lists and tools and can be switched; a chat
  opens under the assistant it belongs to.

Earlier (`src/features/assistant/prepAgent.test.jsx`, 7):

1. Quick-action chips send normal chat messages, and the structured answer renders headings, bullets and bold text
   (no raw markdown).
2. The role picker sends "Prepare me for Data Analyst" and links the mock interview with `?role=data-analyst&mode=mock`.
3. PDF upload → attach to the chat → "Answering from your document" → "Stop using it" detaches.
4. Client-side file checks plus the backend's reason (scanned PDF, no OCR) shown to the student.
5. RichText parsing.
6. Safe source and action links (career track slug only; no link for an unsafe slug).
7. Study-file validation.

## 4. Requested scenarios → evidence

| Scenario | Automated | Live |
|---|---|---|
| Candidate with an extracted resume asks for suitable roles | `test_roles_are_ranked…`, `test_chat_resume_to_role…` | Demo A: Data Analyst 75/100, Data Scientist 75, ML Engineer 62, Python Developer 46 |
| Strongest skills | `test_chat_personal_questions` | ✔ |
| Selecting a role | `test_chat_resume_to_role…`, ordinal test | Demo A (role picker + typed) |
| Technical questions | REST + chat tests | Demo A (beginner list includes Statistics as a missing core skill) |
| HR questions | REST + chat tests | Demo A (10 questions; internship named) |
| Preparation roadmap | `test_roadmap_prioritises…`, chat | Demo A (Tableau/Statistics HIGH, 20 h / 40 h) |
| Missing resume data | `test_chat_without_a_resume…`, 409 API | — |
| Valid PDF / DOCX | ✔ / ✔ | Demo B: 2-page PDF (841 chars), 3-section DOCX |
| Empty / corrupted / unsupported / large | ✔ (6 parametrised + 413) | `.txt` → 415 live |
| Answer in the document / not in the document | ✔ / ✔ | "ACID…" [p. 2] / "couldn't find this in the document" |
| Follow-up questions | ✔ | ✔ (context kept) |
| Generate interview questions, submit answer, feedback, improved answer, complete session | `test_mock_interview_for_a_target_role…` + existing interview suites | Demo C: 100/100 and 6/100 with missing concepts, model answer, summary 13.2/100 overall |
| Unauthenticated access | ✔ (prep, documents) | — |
| Cross-user resume / document / chat access | ✔ (404 everywhere) | ✔ earlier: second student got 404 on another student's resume, matches and conversation |
| Invalid uploads | ✔ | ✔ |

## 5. Live AI check (local Ollama `gemma3`, test database)

- **"Summarize this document"** with AI opted in: the answer cited `p. 1, p. 2`, passed the citation and
  wording-support checks, and was labelled "AI-reworded (fact-checked)".
- **Preparation-agent answers** are deterministic by design; the chat says AI rewording is not applied to them.

## 6. Problems found during testing and fixed

| Problem | Fix |
|---|---|
| Word boundaries in two new regexes were lost by shell quoting (backspace characters), so "the second one" was not understood | Characters repaired; ordinal test passes |
| Technical lists never asked about missing core skills | One slot per level for a missing core skill (+ test) |
| Evidence titles too long / double full stops; date ranges cut | `short_title()` keeps date ranges, trims descriptions |
| "Tell me about yourself" draft listed skills alphabetically and repeated the full education line | Role core skills first; "I'm studying B.Tech Computer Science at Example Institute of Technology" |
| Misconception notes read as plain facts under "mistakes" | Phrased "Getting this wrong - remember: …" |
| Document concept extraction picked verbs ("lets", "hides") | Concepts taken from definitional sentences ("Encapsulation bundles…"), with a verb filter on the fallback |
| AI answers cited "[1]" instead of pages; "* " bullets not formatted | Converted to "[p. 1]"; RichText handles "* " |
| Chat message list squeezed by the action area on laptops; chips wrapping | Layout and `whitespace-nowrap` fixes |
| AI disclosure did not mention document questions | Disclosure extended |

## 7. Incident during testing (not a test failure)

A demo-setup script sent requests to `127.0.0.1:8000`, which was the owner's **dev** backend (`career_companion_dev`),
not a test server. As a result:

- **One unverified student account was created in dev:** user 5, `priya.test@example.com`.
- **One verification email was accepted by the real SMTP server** for that reserved, undeliverable address.

The follow-up verify, login and upload calls failed, so nothing else changed. The account was not deleted (that needs
owner approval). All later live checks used port 8001 and checked `/health` for the test database first.

## 8. Not tested / limitations

- **Groq:** not tested live (no API key).
- **OCR:** not available; scanned PDFs are rejected by design.
- **Upload in the browser pane:** the OS file picker can't be automated. The PDF was supplied to the real upload input
  by script; the DOCX was uploaded through the same API the panel calls, then attached in the UI.
- **Dev database:** migrated to head on 2026-11-25 with the owner's approval (see `FINAL_DATABASE_MIGRATION_CHECKLIST.md`). No automated test ever ran against it; only read-only checks and the owner's own sign-in.
- **After the live demos**, one retrieval refinement was made (quote only passages scoring ≥ 60% of the best). It is covered by the automated tests and the RAG evaluation, but the live demos were not repeated.

## 9. Focused fixes - verification (2026-11-26)

All checks used the test database `career_companion_test`, fictional users (email to a local outbox folder) and
synthetic resumes generated by the tests. The owner's servers on ports 8000/5173 and the development database were not
touched. Nothing was committed, pushed, staged or deployed.

### 9.1 Automated tests

| Suite | Result |
|---|---|
| Backend, full (`pytest`, test database) | **1381 passed, 0 failed, 0 errors** (33 min 7 s), after all Phase 5 fixes |
| Backend, first full run of this phase (before the Phase 5 fixes) | 1375 passed, 0 failed, 0 errors (24 min 37 s) |
| New: `test_job_search.py` | 10 passed |
| New: `test_resume_parsers.py` | 33 passed |
| New: `test_advanced_analysis.py` | 5 passed |
| Frontend (`vitest`, 2 workers) | 419 passed, 21 files (+3 role-analysis, +2 search, ODT wording) |
| Production build (`vite build`) | succeeded |

### 9.2 Live workflow (isolated backend 8001 + frontend 5174) - 34/34 passed

- **Search:** "Java internship" → 10 Java postings, the three "Java Developer Intern" first; "React frontend
  developer" → React postings; "Python internship in Hyderabad" → 8 results, all Hyderabad; "remote data science
  internship" → 8 results, all `work_mode` Remote; "AI/ML internship" → 10 results, all Data Science domain;
  "pizza delivery driver" and "senior plumber with 10 years experience" → 0 results with an explanation; browsing
  `/internships/` unchanged. Mode "hybrid" with a test-only index built from the test database.
- **Parsers through the API** (synthetic PDF, DOCX, ODT): regex returns name, email, phone (+91 kept), 6 technical
  skills (soft skill excluded), 2 education entries, 1 experience entry, 3 projects, 2 certifications on every format;
  hybrid without `consent=true` → 400; hybrid with consent and no AI provider → regex values labelled `sources: regex`
  with the "AI extraction not used" warning; LLM with no provider → 503 (never regex output under the LLM label);
  corrupt ODT → 400.
- **Workflow:** ODT upload → parsed (3 projects) → download returns the identical file with the ODT media type →
  match run (5 results) → insights contain evidence and the "not found ≠ lack" note → general analysis labelled, Java
  and Frontend roles give different gaps, each gap has why/learn/practice/resume tip, unknown role → 404 → stored
  resume preview leaves the stored extraction unchanged.

### 9.3 LLM and hybrid parsers with a real model (local Ollama `gemma3`, synthetic files only)

`LLM_PROVIDER` is not configured in `.env`; the check set `LLM_PROVIDER=ollama` for the CLI command only (the model
runs on this computer; nothing was sent to an external service).

- **First run found a defect:** the model answered `{}` and the LLM parser accepted it as an empty resume (hybrid
  silently fell back to regex values while naming the AI provider). Cause: Gemma 3 in JSON mode ignores long system
  prompts. Fixed (instructions in the user message; an answer with no schema field is an error), with tests.
- **After the fix**, on PDF, DOCX and ODT: LLM parser → skills Python, SQL, Java, React, Docker, Machine Learning,
  Power BI; 2 education entries (B.Tech, Example Institute of Technology, 2026; Senior Secondary, Example Junior
  College, 2022); 1 experience (Data Analyst Intern, Example Analytics, Jun-Aug 2025); 3 projects with technologies;
  2 certifications; name/email/phone `null` with the privacy warning. Hybrid → the same plus name, email and phone from
  regex, `sources` = "both" for every AI-checked field. Two certificate-name fragments the model returned as skills
  were ignored with a warning (fix + test added).
- Malformed answers, wrong shapes, `{}`, unavailable provider and no provider are covered by automated tests
  (fake provider), not by the real model.

### 9.4 Existing features - live regression A-J: 30/30 passed

Registration with outbox verification, sign-in, profile, PDF/DOCX upload and project extraction, readiness score and
correction, identical-upload detection, re-parse, versions and comparison, Application Assistant (workflow, links,
off-topic), internship guidance, Interview Prep Assistant (roles, questions, separate conversations), study-document
Q&A with citations, cross-user 404 and no-token 401.

### 9.5 Browser (test frontend 5174)

1280 / 768 / 375 px: Skills & Gaps (role analysis), Matches (insights with evidence), Internships (AI search), Resumes
- no horizontal overflow, no error alerts. At 375 px "remote React internship" showed "We understood: skills: React ·
work mode: Remote", 4 results with "Why:" lines. Frontend role analysis for Frontend Developer: JavaScript "Listed but
not demonstrated" (medium), CSS/HTML/Git/TypeScript "Not found in your resume" (high). Console: only the expected
`/profiles/me/avatar` 404 (test user without a picture) and the 401 before sign-in.

### 9.6 Not verified

- Groq (no API key). LLM extraction through the web API with a real model (verified through the CLI, which calls the
  same parser functions; the API was verified with no provider configured).
- OCR (not supported).
