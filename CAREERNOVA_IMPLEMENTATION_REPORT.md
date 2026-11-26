# CareerNova AI — Implementation Report (Master Implementation Prompt)

Date: 2026-11-25 · Branch: `careernova/dashboard-redesign` · Backup stash `CareerNova pre-dashboard backup` untouched ·
**Nothing committed or pushed.** **No migration applied to `career_companion_dev`.** The accidental dev account
(user 5, `priya.test@example.com`) was not touched and no email was sent to it.

All automated tests and live demos used `career_companion_test`, an isolated backend on port 8001 (checked via
`/health` before every script), the frontend on port 5174, a file outbox (no real email) and isolated upload folders.

Status legend: **Verified** = implemented and checked by tests and a live demo · **Implemented** = implemented and
covered by automated tests, not shown in a live demo · **Not implemented**.

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

## 1. Audit checklist

| Area | Requirement | Status | Evidence |
|---|---|---|---|
| Two assistants | Separate Application Assistant and Interview Preparation Assistant (identity, intents, conversations, UI entry points, switching) | **Verified** | `test_two_assistants_keep_separate_scopes`, 2 frontend separation tests, Demo 1 |
| | Application Assistant stays on CareerNova help + the user's data; declines general chat | **Verified** | Demo 1 (off-topic question declined) |
| | Prep questions in the Application Assistant redirect to the Interview assistant (and vice versa) | **Verified** | redirect tests, Demo 1 |
| Interview prep | Roles from the resume, with matching internships per role | **Verified** | Phase 6 tests, Demo 2 |
| | Technical + HR questions, guidance, preparation priorities | **Verified** | Demo 2 |
| | Problem-solving HR question theme (11 questions) | **Implemented** | `hr-problem-solving` in `hr_question_guide.json`, test |
| | Roadmap with practice questions and resources | **Verified** | Demo 2 |
| | Mock interview questions only about the target role; scores labelled as practice | **Verified** | `test_role_mock…`, Demo 2 (starts with SQL) |
| Study documents | PDF/DOCX RAG, follow-ups, honest "not found", injection-safe | **Verified** | 24 tests, Demo 3 |
| | Several documents in one chat (max 5), cross-document citations with file names | **Verified** | multi-document tests, Demo 3 |
| RAG quality | Configurable chunking with metadata | **Implemented** | `STUDY_CHUNK_CHARS` / `STUDY_CHUNK_OVERLAP`, chunking test |
| | Hybrid retrieval, reranking, deduplication, metadata filters (document, page) | **Implemented** | retrieval tests + evaluation |
| | Repeatable evaluation dataset; standard vs agentic comparison | **Verified** | `evaluation/study_rag_eval.py` → `docs/assignment/evaluation/STUDY_RAG_EVAL.md` |
| | Agentic RAG only where it measurably helps | **Implemented** | "auto" mode: agentic for multi-part questions only (see §5) |
| Profile | Profile picture: upload, replace, remove, initials fallback, validation, private access | **Verified** | 13 tests in `test_profile_and_versions.py`, Demo 4 |
| | Picture shown in profile, header, dashboard and assistant messages | **Verified** | Demo 4 |
| | Editable bio (600 characters) | **Verified** | tests, Demo 4 |
| Resume versions | Several versions, never overwritten, names, version numbers, one preferred | **Verified** | tests, Demo 5 |
| | Preferred version used by the assistants and prep agent | **Verified** | Demo 2 used preferred V2 |
| Resume comparison | Contact, technical/soft skills, every section, keywords, readiness/role/ATS metrics; added/removed/modified/unchanged | **Verified** | tests, Demo 5 |
| | Verdict only from measured differences (≥ 5 points), recommendations, role suitability, nothing invented | **Verified** | Demo 5 |
| Security | Owner-only access to every new resource; 401 without a token | **Verified** | tests, Demo 6 |
| Frontend | Responsive (375 px), accessible labels, every new control works | **Verified** | frontend tests, mobile check |
| Database | Additive migrations, validated on the test DB only; dev procedure with backup and rollback | **Verified** (dev: applied 2026-11-25 after a verified backup) | 15 migration tests, `FINAL_DATABASE_MIGRATION_CHECKLIST.md` |

Nothing in the prompt is "Not implemented". OCR for scanned PDFs and live Groq testing were out of scope / not
possible (see §9).

## 2. Architecture and data flow

```
Browser (React)
  /assistant/:id?            → AssistantPage kind="application"
  /interview-assistant/:id?  → AssistantPage kind="interview" (+ PrepActions, StudyDocumentPanel)
  /profile                   → ProfilePhoto, BioEditor           /resumes, /resumes/compare
        │ JWT
FastAPI
  /assistant/conversations   conversation.context.assistant ∈ {application, interview}
        └─ service.post_message
             interview:   doc_agent → prep_agent → (application-only topic? redirect) → interview data intents → out of scope
             application: (prep topic? redirect) → product help → application data tools → out of scope
  /study-documents           study_documents (chunking) → study_qa (hybrid retrieval, rerank, dedupe, agentic)
  /profiles/me/avatar        services/avatars (magic bytes, size, dimensions, per-user folder)
  /resumes (PATCH, compare)  services/resume_compare (readiness-v1, roles-v1, ATS report)
        │
PostgreSQL (SQLAlchemy/Alembic)   uploads/avatars/<user>/<uuid>.<ext>
```

The existing resume parser is reused unchanged; the comparison reads its stored extraction.

## 3. APIs added or changed

| Method | Path | Notes |
|---|---|---|
| POST | `/assistant/conversations` | body `assistant: application \| interview` (default application) |
| GET | `/assistant/conversations?assistant=` | list one assistant's chats |
| PUT | `/assistant/conversations/{id}/study-document` | `document_ids` (≤ 5) or `document_id`; interview chats only (409 otherwise) |
| POST | `/study-documents/{id}/ask` | `mode`: standard / agentic / auto |
| POST | `/study-documents/ask` | question across 1–5 owned documents; rate limited |
| POST / GET / DELETE | `/profiles/me/avatar` | PNG/JPEG/WebP, ≤ 2 MB, 32–4096 px; served with `nosniff`, `no-store` |
| PUT | `/profiles/me` | `bio` (≤ 600 characters, cleaned) |
| GET | `/resumes` | adds `version`, `label`, `is_preferred` |
| PATCH | `/resumes/{id}` | `label`, `is_preferred` (parsed resumes only; un-prefers the others) |
| GET | `/resumes/compare?a&b&role&internship_id` | both resumes must belong to the caller (404 otherwise) |
| GET | `/prep/roles` | each role includes matching `internships` |

## 4. Database changes (additive)

| Migration | Adds |
|---|---|
| `f2b4d6a8c0e1` (earlier phase) | `study_documents`, `study_document_chunks` |
| `a7c9e1b3d5f6` (this phase) | `student_profiles.bio`, `avatar_path`, `avatar_content_type`, `avatar_updated_at`; `resumes.label`, `resumes.is_preferred` (default false); partial unique index "one preferred resume per student" |

Both downgrades refuse while new data exists (explicit `-x …_allow_data_loss=true` needed). Both were
**applied to `career_companion_dev` on 2026-11-25** with the owner's approval, after a fresh backup that was
restored and verified in `career_companion_restorecheck`. Row counts and content fingerprints were unchanged; details
and records in `FINAL_DATABASE_MIGRATION_CHECKLIST.md`.

## 5. AI / RAG

**Pipeline:** chunking (sentence-aligned overlap, page/section metadata) → BM25 + local MiniLM cosine (0.5/0.5) →
rerank (query-term coverage, heading match) → dedupe (≥ 80% overlap) → only passages ≥ 60% of the best score are
quoted → extractive answer with page/section citations (file name added when several documents are searched).
Optional AI rewording (local Ollama or Groq) sends excerpts as JSON data, needs citations and ≥ 60% word support,
otherwise the quoted answer is shown.

**Agentic mode:** splits multi-part / comparison questions into sub-queries, retrieves per part, retries once with
heading expansion and merges round-robin. **Auto** (the default) uses it only when the question has several parts.

**Evaluation** (`python -m evaluation.study_rag_eval`; final run 2026-11-25 on an idle machine; full table, methodology
and limitations in `docs/assignment/evaluation/STUDY_RAG_EVAL.md`, console output in `study_rag_eval_console.txt`).
30 questions (25 answerable incl. 5 multi-part/cross-document, 5 unanswerable) + 3 follow-ups on fictional PDF/DOCX
notes. The **hard set** adds two distractor documents, 220-character chunks and top-2 retrieval.

Hybrid retrieval (BM25 + MiniLM), hard set:

| Mode | recall@k | precision@k | multi-part recall | answer correctness | failure rate | citation precision (strict) / hit | no-answer / hallucination | latency mean / p95 |
|---|---|---|---|---|---|---|---|---|
| standard | 0.98 | 0.88 | 0.9 | 0.96 | 0.033 | 1.0 / 1.0 | 1.0 / 0.0 | 12.2 / 13.4 ms |
| agentic | 1.0 | 0.867 | 1.0 | 1.0 | 0.0 | 0.745 / 1.0 | 1.0 / 0.0 | 18.2 / 32.3 ms |
| **auto** (default) | 1.0 | 0.867 | 1.0 | 1.0 | 0.0 | 0.957 / 1.0 | 1.0 / 0.0 | 15.6 / 33.8 ms |

Keyword-only fallback (no embedding model), hard set: standard answers 0.92 / failure rate 0.067 / 1.6 ms;
agentic 1.0 / 0.0 / 1.7 ms; auto 1.0 / 0.0 / 1.5 ms. Standard set (1000-character chunks): same pattern
(hybrid standard 0.96 → auto 1.0).

- **What this supports:** on this dataset, agentic retrieval fixes the multi-part questions standard retrieval misses
  (the only standard failures are "foreign key + third normal form" and, keyword-only, "deadlock + round robin").
  Always-on agentic quotes more off-target passages (strict citation precision 0.745). **Auto** gets the agentic gain
  with citation precision 0.957 at ~1.3× standard latency, so it is the default.
- **What it does not support:** general accuracy claims. The dataset is small, fictional and hand-labelled; answer
  correctness is a key-word check; optional AI-reworded answers are not measured.
- Earlier runs made while the test suites were running showed 4–10× higher latency; only the idle-machine figures
  above are reported.
- Everything runs locally; no cloud service is required.

## 6. Frontend

New: `AssistantSwitch`, `Avatar`, `AvatarContext`, `ProfilePhoto`, `BioEditor`, `ResumeComparePage`.
Changed: `AssistantPage` (kind), `StudyDocumentPanel` (several documents), `ConversationList`, `MessageBubble`,
`ProfileMenu`, `DashboardPage`/`AssistantCard` (two assistants), `ResumesPage` (versions, rename, preferred, compare),
navigation ("AI assistants" group). Checked at 375 px: no horizontal overflow.

## 7. Tests (final, 2026-11-25)

| Suite | Baseline | Final |
|---|---|---|
| Backend `pytest tests` (test DB) | 1238 passed | **1267 passed, 0 failed, 0 errors, 0 skipped** (final run after the last code change) |
| Frontend `vitest run` | 402 passed | **411 passed, 21 files** with `--maxWorkers=2`. With default parallelism (12 cores) 7 tests timed out at 15 s; all 4 affected files pass alone (118/118). See the test report |
| Production build `vite build` | OK | **OK** (no warnings; main bundle 116 kB gzip) |

+29 backend tests and +9 frontend tests were added; none removed or weakened. The first full backend run found 2
regressions in the assistant split, and a manual routing check found that the first fix was too broad; all were fixed in
code (details in `CAREERNOVA_TEST_REPORT.md`).

## 7b. Post-migration fixes (2026-11-25, afternoon; test database only)

- **Off-topic leak fixed:** "who is ronaldo" after a product question was merged with it as a short "follow-up" and answered
  from the product guide. `product_help.is_unrelated_topic()` now keeps such messages out of the follow-up path; real
  follow-ups that refer back still work. Reproduced by 4 failing tests before the fix; 6 new test cases.
- **Interview chip:** the Application Assistant's "Help me prepare for an interview" suggestion is now a link to the
  Interview Preparation Assistant (no message sent); scopes and backend redirects unchanged.
- **Identical resume names (diagnosis, no change):** the same PDF was uploaded three times (identical SHA-256); duplicate
  uploads are allowed and reported by design; the file belongs to a different person, so its contact details differ
  from the account.
- **Dev database:** both migrations applied with the owner's approval after a verified backup; signed-in UI check passed.

## 8. Live demos (test database, 2026-11-25)

1. **Application Assistant:** product answer from the guide; off-topic question declined; prep question redirected.
2. **Interview Prep Assistant:** roles with internships → technical/HR questions → guidance → roadmap with resources;
   used the preferred V2 resume; role mock interview started with SQL.
3. **Study documents:** PDF + DOCX in one chat; cross-document citations; follow-up; questions from the documents;
   honest "not found".
4. **Profile:** picture and bio persist after reload, picture in the header.
5. **Resume versions:** V2 uploaded and named "Data-analyst focused", set preferred; comparison: B stronger
   (contact 10 vs 8, Data Analyst fit 100 vs 75), skills added/removed, removed project, lost evidence listed.
6. **Security:** a second student got 404 on all of the first student's resumes, documents, chats, comparison and
   prep data; no token → 401.

After the demos, two changes were made and are covered by automated tests only (live demos not repeated):
the relative 60% score cut-off for quoted passages, and the fix that lets the Application Assistant keep answering
learning-plan / skill-gap / practice-question requests (and keep an empty context for its chats).

## 9. Known limitations

- No OCR: scanned PDFs are rejected with an explanation.
- Groq not tested live (no API key); Ollama tested earlier.
- Project extraction is rule-based: it relies on each project title being on its own line (or "Title - sentence").
  Projects written as one continuous paragraph, inside images, or in complex tables may still be grouped wrongly -
  "Edit details" lets the student correct them. (Plain-paragraph projects are now separated; the earlier merging
  limitation is fixed.) The second resume file whose count changed 3 → 2 was checked only against its earlier on-screen
  display, not a ground-truth fixture.
- Existing resumes in dev keep their stored (old) extraction until the owner presses Re-parse after restarting the dev
  backend; nothing was re-parsed automatically.
- DOCX study documents without Word heading styles are cited as "document" rather than by section.
- Local AI needs Ollama running with `gemma3` (CPU answers 15-60 s); it will not run on ordinary serverless hosting.
- The RAG evaluation uses a small synthetic, hand-labelled dataset; it compares retrieval modes and is not a measure of
  real-world accuracy.
- Comparison matches section entries by title; a renamed entry shows as removed + added.
- Readiness, role fit and mock-interview scores are practice guidance, not hiring predictions.
- Browser file pickers cannot be automated; uploads in demos used the real input via script or the same API.
- Frontend tests are timing-sensitive under heavy parallelism on this laptop (7 timeouts with default workers, 0 with
  2 workers). Not a functional failure, but CI should use limited workers or a faster runner.

## 10. Pending the owner's decision

1. Decide what to do with user 5 (`priya.test@example.com`) in dev (untouched).
2. Whether to keep or drop the scratch database `career_companion_restorecheck` and the backups.
3. Approve staging, the commit and the push to the owner's private `CareerNova-AI` repository (local config and
   generated files are now git-ignored).
4. Deployment (HR has approved; the owner approves each step): create the database, the Render service and the Vercel
   project in the owner's own accounts - steps in `DEPLOYMENT_AND_HANDOVER_GUIDE.md` §7. Render's recommended plan has a
   monthly cost.
5. Manual acceptance: `MANUAL_ACCEPTANCE_CHECKLIST.md`.

## 12. Deployment readiness (configuration prepared - nothing deployed yet)

| Area | Current state | What deployment needs |
|---|---|---|
| Frontend | React + Vite static build (`npm run build` → `frontend/dist`, ~116 kB gzip main bundle) | Any static host (or the backend's reverse proxy). Set the API base (`VITE_API_BASE_URL`, default `/api`) and route `/api` to the backend |
| Backend | FastAPI + Uvicorn, synchronous request handling; parsing, embeddings and matching run inside requests | A long-running Python service (VM or container), not serverless functions: requests can take seconds, the MiniLM model is loaded in memory, and files are written to disk |
| Database | PostgreSQL 17, Alembic head `a7c9e1b3d5f6` | Managed PostgreSQL; run `alembic upgrade head` on deploy; daily backups (`pg_dump`) as in `FINAL_DATABASE_MIGRATION_CHECKLIST.md` |
| File storage | Resumes, avatars and the email outbox are written under `uploads/` on local disk; study documents keep only extracted text in the database | A persistent volume (or move to object storage later); back up together with the database. Ephemeral container disks would lose uploads |
| Secrets / config | `.env` (git-ignored): `DB_*`, `JWT_SECRET_KEY`, `SMTP_*`, `MAIL_FROM*`, `FRONTEND_URL`, `APP_BASE_URL`, `CORS_ORIGINS`, `EMAIL_MODE`, `LLM_PROVIDER`, `GROQ_*`, `OLLAMA_*`, `EMBEDDING_*`, `FAISS_INDEX_DIR` (documented in `.env.example`) | Set in the host's secret store; a new random `JWT_SECRET_KEY`; never commit `.env` |
| Authentication | JWT access tokens (HS256) + refresh sessions in the database, login throttling, email verification, role-based admin | HTTPS is required (tokens in headers, refresh flow); `FRONTEND_URL`/`APP_BASE_URL` must be the public HTTPS URLs used in email links |
| CORS | Explicit allow-list from `CORS_ORIGINS` (`*` is refused at startup) | Set to the exact frontend origin(s) |
| Email | `EMAIL_MODE=outbox` writes `.eml` files (no sending); `smtp` sends | Real SMTP credentials only in production; keep `outbox` for staging |
| AI (optional) | Every feature works without AI. Optional rewording: Groq (cloud, needs `GROQ_API_KEY`, data leaves the server) or Ollama + Gemma 3 (local) | Ollama does **not** run on ordinary serverless or small app hosts: it needs its own machine with ~8 GB+ RAM (GPU recommended; CPU answers took 15-60 s here). Options: leave AI off (default), use Groq with a privacy notice, or run Ollama on a separate VM reachable only from the backend |
| Embeddings / RAG | `sentence-transformers/all-MiniLM-L6-v2` (CPU), downloaded once into `EMBEDDING_CACHE_DIR`; internship index under `FAISS_INDEX_DIR` (NumPy format); keyword fallback when the model is unavailable | ~1 GB RAM for PyTorch + model; pre-download the model in the image; persistent index directory (or rebuild via the admin "Search index" page) |
| Background work | None: no queue or workers; everything runs in the request | Fine for a demo/small cohort; for many users, move parsing/embedding to a worker queue |
| Limits | Resume 5 MB, study documents 10 MB, avatars 2 MB; assistant rate limits (10/min, 300/day); login throttling | Also set a reverse-proxy body-size limit and timeouts above the slowest request |

**Recommended architecture for an HR demo:** one small Linux VM (2 vCPU, 4 GB RAM) running the backend in a container behind Nginx/Caddy (HTTPS, static frontend, `/api` proxy), a managed PostgreSQL instance, a persistent volume for `uploads/`, `EMAIL_MODE=outbox` or a transactional SMTP account, and AI rewording off (or Groq). Add a separate GPU/large-RAM VM for Ollama only if local AI is required.

**Costs and privacy:** resumes and study documents contain personal data; keep the database and upload volume in one region, restrict database access to the backend, enable automated backups, and publish a privacy notice before using Groq (data leaves the server). Nothing here has been deployed yet. HR has approved deployment; the concrete steps for the owner's accounts are in `DEPLOYMENT_AND_HANDOVER_GUIDE.md` §7 (`render.yaml`, `frontend/vercel.json`).

## 11. Start commands

```powershell
cd "<project-root>"
$env:DB_NAME='career_companion_test'   # or career_companion_dev (migrated to head on 2026-11-25)
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```
```powershell
cd "<project-root>\frontend"
$env:BACKEND_URL='http://127.0.0.1:8001'   # the Vite proxy defaults to port 8000
npm run dev
```

## 13. Focused bug fixes and feature improvements (2026-11-26)

Three requested areas, built on the existing architecture (no rebuild, no removed features, no unrelated redesign).

### 13.1 AI job search (Issue 1)

**Root cause.** `/internships/search` returned the top-k postings by cosine similarity with no relevance floor, so
any query (even "pizza delivery driver") returned results; location and remote/hybrid/onsite words were ignored; skills
in the query were not required. Found during Phase 5: a search for "AI/ML" also matched postings whose *company name*
contains "AI", and a "Remote" search let through ten curated postings whose location says "Remote" but whose
`work_mode` is Onsite/Hybrid.

**Fix.** New `backend/services/job_search.py`: the query is interpreted (skills via the existing skill normaliser,
role phrases, location from the catalogue's cities, work mode, "jobs"/"fresher" wording); location and work mode are
hard filters (structured `work_mode` only); a requested skill must be in the posting's skills, title or domain; roles
match title/domain/skills (not the company); other words need a match or semantic similarity ≥ 0.50. Score =
0.6 × exact-match share + 0.4 × similarity; equal scores put postings whose title names the skill first. If the
model/index is unavailable or stale, search falls back to keyword rules (no more 503) and says so. Empty results and
"jobs" queries get an explanation (the catalogue lists internships only). The UI shows "We understood: …", the
backend message, a relevance badge and a "Why:" line per result. Browsing/filtering is unchanged.

### 13.2 Resume parsers (Issue 2)

`backend/services/resume_parsers/`: `regex_parser.py`, `llm_parser.py`, `hybrid_parser.py` and `common.py` (one
Pydantic schema: name, email, phone, technical skills, education, work experience, projects, certifications, plus
`metadata.parser`, `file_type`, `warnings`, `sources`, `llm_provider`, `llm_model`). Formats: PDF, DOCX, ODT
(ODT read with the standard library; format detected from file content, ZIP limits applied).

- **Regex:** reuses the existing extraction; adds structured education/experience/project entries and phone
  normalisation that keeps the country code.
- **LLM:** the existing provider integration (`LLM_PROVIDER` = `ollama` or `groq`); no keys in code. Contact details
  are removed before sending, so name/email/phone are always `null` (privacy rule). Every returned value must appear in
  the resume text; skills that appear only inside certification names are ignored; an answer without any schema field
  (e.g. `{}`) or with the wrong shape is an error, never an "empty resume". Found with the real local model in Phase 5:
  Gemma 3 in JSON mode answers `{}` when the instructions are in the system prompt, so the instructions are now sent in
  the user message.
- **Hybrid:** contact details from regex, the rest merged from both with evidence checks; conflicts reported;
  `metadata.sources` per field. If the AI is unavailable or its answer is unusable, the regex result is returned with
  the warning "AI extraction not used" - never labelled as AI output.
- **Integration:** ODT accepted by the normal upload (and download, versions, ATS, comparison), `POST
  /resumes/parse-preview` and `GET /resumes/{id}/parse-preview` (nothing stored; AI parsers need `consent=true`), CLI
  `python -m backend.manage parse-resume <file> --parser regex|llm|hybrid`. Stored extractions and manual corrections
  are never changed by a preview.

### 13.3 Matches and Skills & Gaps (Issue 3)

- **Matches** (`job_insights.py`, `routes/matches.py`): each match now lists where the resume shows each matched skill
  (project/experience titles), skills that are only in the skills list, and labels missing skills "Not found in your
  resume (this does not mean you lack the skill)"; improvement tips say to add a skill to a project if the student
  already uses it.
- **Skills & Gaps** (`skill_analysis.py`, `GET /skill-gaps/role-analysis?role=`): skills grouped into Programming
  languages / Frontend / Backend / Databases / AI/ML / Cloud & DevOps / Tools & frameworks (+ CS fundamentals, Other);
  each skill is *demonstrated* (a project/experience mentions it), *listed only*, or *not found*. For a chosen role (14
  curated career tracks) it shows the requirements with status, a fit score (75% core + 25% advanced coverage, with the
  basis shown), and gaps sorted by priority, each with why it matters, what to learn (roadmap stage), a practical task
  and how to add it to the resume. Without a role it is a clearly labelled general analysis. New frontend section
  `RoleAnalysis.jsx` on the existing page (role kept in the URL `?role=`), with loading, empty and error states.

### 13.4 Files

Created: `backend/services/job_search.py`, `backend/services/skill_analysis.py`,
`backend/services/resume_parsers/{__init__,common,regex_parser,llm_parser,hybrid_parser}.py`,
`frontend/src/features/skillGaps/components/RoleAnalysis.jsx`, `tests/test_job_search.py`,
`tests/test_resume_parsers.py`, `tests/test_advanced_analysis.py`.

Modified: `backend/routes/{internships,resumes,matches,skill_gaps}.py`, `backend/schemas/internship_schema.py`,
`backend/services/{resume_parser,job_insights}.py`, `backend/manage.py`, `tests/test_internships_api.py` (503 test
replaced by the keyword-fallback test), `frontend/src/api/{resumes,skillGaps}.js`,
`frontend/src/features/internships/{SemanticSearch.jsx,internships.test.jsx}`,
`frontend/src/features/matches/{JobInsights.jsx,matches.test.jsx}`,
`frontend/src/features/resumes/{resumeFile.js,ResumesPage.jsx,components/ResumeUploader.jsx,resumes.test.jsx}`,
`frontend/src/features/dashboard/{components/ResumeCard.jsx,dashboard.test.jsx}`,
`frontend/src/features/skillGaps/{SkillGapsPage.jsx,skillGaps.test.jsx}`, `README.md`, this report and
`CAREERNOVA_TEST_REPORT.md`.

### 13.5 Limitations

- No OCR: scanned/image-only resumes are rejected with a clear message.
- The LLM parser never returns name/email/phone (by design); use hybrid for a complete record. It needs
  `LLM_PROVIDER`; it is **not configured** in this environment's `.env`. It was verified with the local Ollama
  `gemma3` model by setting `LLM_PROVIDER=ollama` for the CLI command only. Groq was not tested (no key).
- Rule-based extraction expects common section headings; unusual layouts may need manual correction.
- The catalogue is 180 curated **internships**; "job" queries are answered from it and say so. Ten curated postings
  have location "Remote" but a non-remote work mode (data left unchanged; search follows `work_mode`).
- Search similarity needs the FAISS index for the same database; without it search runs in keyword mode and says so.
- Role analysis covers the 14 curated career tracks only.
