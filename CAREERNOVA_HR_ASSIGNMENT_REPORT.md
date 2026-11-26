# CareerNova AI — HR Assignment Report: AI-Powered Interview Preparation Agent Chatbot

Date: 2026-11-24, updated 2026-11-25 · Branch: `careernova/dashboard-redesign` (backup stash `CareerNova pre-dashboard backup` untouched) ·
Nothing committed or pushed. All new features were built **inside** the existing CareerNova AI app (no new project).

> **Incident to note first.** During the live demo setup, a script meant for my isolated test server was sent to
> `http://127.0.0.1:8000`. That port was in use by the owner's dev backend, connected to **`career_companion_dev`**. As a result:
>
> 1. One unverified student account was created in the dev database: user 5, "Priya Sharma",
>    `priya.test@example.com`, created 17:15 IST.
> 2. The dev server's SMTP accepted one verification email to `priya.test@example.com` at 17:15. `example.com` is a
>    reserved domain, so the mail cannot be delivered; a bounce notice may arrive in the sender's mailbox.
>
> Nothing else in dev changed: the follow-up verify, login and upload calls all failed. The account was **not**
> deleted, because deleting dev data needs owner approval.
>
> Since then every live check has run on a separate backend (port 8001) and frontend (port 5174) against
> `career_companion_test`. Each script first checks `/health` reports the test database.

## Release preparation (2026-11-26) - summary

- Fresh results: backend **1333 passed, 0 failed, 0 errors**; frontend **414 passed**; build OK (0 warnings); live
  scenarios A-J **30/30**; browser sweep 15 pages × 1280/768/375 px clean; session refresh, CORS and deep links verified.
- Fixes: student-facing search errors no longer show internals; compare page overflow; page headings on not-found /
  no-access pages; guide wording and query; optional `DB_SSLMODE` for managed PostgreSQL.
- Deployment prepared (not deployed): `frontend/vercel.json`, `render.yaml`, `DEPLOYMENT_AND_HANDOVER_GUIDE.md` §7.
  HR has approved GitHub publication and deployment; the owner approves each step.
- Manual acceptance by the owner: `MANUAL_ACCEPTANCE_CHECKLIST.md` (not yet run).

## Final audit (2026-11-26) - summary

- Resume extraction: a 3-project resume shown as 7 projects is fixed (root cause in project grouping); dates, duplicates,
  wrapped lines, Word bullets and technology lists handled; corrections are protected by a Re-parse confirmation.
- Application Assistant: step-by-step workflow guidance with real pages, links and the student's verified progress;
  CareerNova-only scope kept; interview preparation stays in the Interview Preparation Assistant.
- Readiness score: shows which version was scored and explains identical scores (the repeated 69 was real data).
- Results: backend **1333 passed, 0 failed (plus 78/78 re-run after the fixture rename)**; frontend **414 passed** (2 workers); build OK; live scenarios A-J 30/30.
- Details: `CAREERNOVA_IMPLEMENTATION_REPORT.md` and `CAREERNOVA_TEST_REPORT.md` ("Final audit" sections).

## 0. Additional HR feedback (2026-11-25) — status

Full details: `CAREERNOVA_IMPLEMENTATION_REPORT.md`. "Verified" = automated tests + live demo on the test database.

| Feedback item | Status |
|---|---|
| Two separate assistants (Application Assistant restricted to CareerNova + own data; Interview Prep Assistant), separate chats, easy switching, cross-redirects | Verified (Demo 1, 2) |
| Interview prep: internships per role, preparation priorities, problem-solving HR question, roadmap with practice questions and resources, role-only mock questions | Verified (Demo 2); problem-solving set covered by tests |
| Several PDF/DOCX study documents in one chat with cross-document citations | Verified (Demo 3) |
| RAG: configurable chunking, hybrid retrieval, reranking, dedupe, filters, evaluation dataset, standard vs agentic comparison | Verified by `evaluation/study_rag_eval.py`; "auto" mode chosen from the measurements |
| Profile picture (upload/replace/remove, initials, validation, private) and editable bio | Verified (Demo 4) |
| Multiple resume versions (names, preferred) and evidence-based comparison | Verified (Demo 5) |
| Privacy of all new data | Verified (Demo 6: 404 / 401) |
| Dev database migrations `f2b4d6a8c0e1`, `a7c9e1b3d5f6` | **Applied 2026-11-25** with owner approval, after a verified backup |

## 1. Audit — what existed and what was missing (verified by running it)

| HR requirement | Existing implementation (verified) | Missing work | Action taken |
|---|---|---|---|
| Resume data integration | Parser + `fact_base.build_fact_base` (education, skills, projects, experience, internships, certifications, achievements), skill locations, owner-scoped resumes | A single "resume context" for an agent | `services/prep/context.py` (`load_context`, `skill_evidence`, `profile`) reuses `build_fact_base` — no new parser |
| AI preparation chatbot | Career assistant (intents, tools, sources, memory, rate limits, optional Groq/Ollama rewording with verification) | Prep-agent intents | `services/assistant/prep_agent.py` routed first in `assistant/service.py`; conversation memory in `conversation.context` (`target_role`, numbered question lists) |
| Role recommendations | 11 career tracks with skills/roadmaps; per-job matching | Resume → role ranking, role fit, strengths/weaknesses | `services/prep/roles.py` (`roles-v1`: 75% core + 25% advanced coverage, evidence from projects/experience, readiness labels). Added Frontend, Backend and Full Stack tracks (now 14 roles) |
| Interview questions | 207 curated technical questions (69 skills × easy/medium/hard) with key points, explanations and misconceptions; 12 behavioural questions | Role-specific, levelled lists; HR set; project questions | `services/prep/questions.py`: beginner/intermediate/advanced per role (resume skills first, one slot for a missing core skill), personalised project questions, `hr_question_guide.json` (10 curated HR questions) |
| Answer guidance | Bank key points + explanations | Expectations, structure, sample answer, mistakes, verified resume material | `services/prep/guidance.py`: samples labelled as samples; "Tell me about yourself" draft built **only** from resume facts with placeholders |
| Preparation roadmap | Career-track roadmaps, learning plans, per-job roadmap | Personalised role roadmap | `services/prep/roadmap.py`: priorities (missing core = high), sequence, hours, exercises, project improvements, practice plan |
| Interactive interview practice | Sessions, one-question view, rubric evaluation, missing points, model answers (reveal), summary, history | Target **role** | `target_role` on `POST /interviews/sessions` (stored in the session summary, no migration); role picker + `?role=&mode=mock` links |
| PDF/DOCX upload | Resume validation (extension + magic bytes + ZIP limits), column-aware PDF reader, DOCX reader | Study documents with ownership | `services/study_documents.py` reuses `validate_resume_file` and `resume_parser.page_text`; 2 new tables (migration `f2b4d6a8c0e1`) |
| Document Q&A | — | Retrieval, grounded answers, references, follow-ups, injection safety | `services/study_qa.py` (BM25 + local embeddings, summary/concepts/questions/notes/answers with page or section references; optional grounded AI answer), `services/assistant/doc_agent.py` (chat integration) |
| Testing & integration | 1204 backend + 395 frontend tests | Tests for all new paths | 33 new backend tests, 1 new migration test, 7 new frontend tests; live demos A/B/C (see `CAREERNOVA_TEST_REPORT.md`) |

## 2. Features

**Already present before:**
- resume upload and parsing, readiness, ATS checks and matching;
- skill gaps and career tracks;
- the career assistant with sources, memory and AI rewording;
- interview practice with rubric feedback and summaries;
- application tracking and authentication.

**Newly implemented:**
1. Resume-grounded **role recommendations**, role fit ("Am I suitable for a Java Developer role?"), strongest skills, weaknesses / skills to improve, and resume analysis — in chat and REST.
2. **Role selection** with memory, so follow-ups like "Generate technical questions" use it.
3. **Technical questions** by level, **HR questions**, and **project questions** naming the student's own projects.
4. **Answer guidance** for every listed question: what the interviewer expects, points to mention, structure, a sample answer or a resume-only draft, common mistakes, and verified resume material.
5. **Personalised preparation roadmap.**
6. **Role-based mock interviews**: role picker, deep link from chat, and role-focused technical questions.
7. **PDF/DOCX study documents**:
   - checks: real file content, size, empty, corrupted, scanned (no OCR), duplicates and password-protected files;
   - ownership, page/section references, delete.
8. **Document Q&A** in the chat:
   - grounded answers with references;
   - an honest "not in the document";
   - summary, key concepts, interview questions with answers, revision notes, follow-ups;
   - optional grounded AI answers (local Ollama) with citation and support checks;
   - document text treated as untrusted.

**Improved:**
- chat message formatting (headings, bullets, bold);
- the AI privacy notice now covers document questions;
- the interview form has a target role;
- 3 new career tracks;
- the career-tracks wording no longer hard-codes "11 roles".

## 3. Files

**Backend (new)**
- `backend/services/prep/__init__.py`, `context.py`, `roles.py`, `questions.py`, `guidance.py`, `roadmap.py`
- `backend/services/assistant/prep_agent.py`, `backend/services/assistant/doc_agent.py`
- `backend/services/study_documents.py`, `backend/services/study_qa.py`
- `backend/routes/prep.py`, `backend/routes/study_documents.py`
- `backend/data/hr_question_guide.json`
- `migrations/versions/f2b4d6a8c0e1_study_documents.py`

**Backend (changed)**
- `backend/main.py` (2 routers)
- `backend/models.py` (`StudyDocument`, `StudyDocumentChunk`)
- `backend/services/assistant/service.py` (routing, document answers, attach, source availability, rendering)
- `backend/services/assistant/facts.py` (source types `career_track`, `study_document`)
- `backend/routes/assistant.py` (`PUT /conversations/{id}/study-document`, conversation fields, disclosure)
- `backend/schemas/assistant_schema.py`
- `backend/routes/interviews.py`, `backend/schemas/interview_schema.py`, `backend/services/interview_generator.py`, `backend/services/interview_service.py` (target role)
- `backend/data/career_tracks.json` (+3 tracks, `tracks-v2`), `backend/services/career_tracks.py`, `backend/routes/career_tracks.py`

**Frontend (new)**
- `src/api/studyDocuments.js`, `src/api/prep.js`
- `src/features/assistant/components/PrepActions.jsx`, `StudyDocumentPanel.jsx`, `RichText.jsx`
- `src/features/assistant/prepAgent.test.jsx`

**Frontend (changed)**
- `src/features/assistant/AssistantPage.jsx`, `components/MessageBubble.jsx`, `assistantFormat.js`
- `src/features/interviews/components/StartSessionForm.jsx`, `InterviewPrepPage.jsx`
- `src/api/interviews.js`, `src/api/careerTracks.js`
- `src/features/careerTracks/CareerTracksPage.jsx`
- `src/test/handlers.js`

**Tests:**
- `tests/test_prep_agent.py` (new, 14)
- `tests/test_study_documents.py` (new, 19)
- `tests/test_migrations.py` (new head + 1 test)
- `tests/test_p3_features.py` (14 tracks)

**Tooling:** `.claude/launch.json` gained `frontend-test-demo` (port 5174, proxies to the test backend on 8001).

## 4. APIs

| Method & path | Purpose |
|---|---|
| `GET /prep/profile` | What the agent read from my resume + strengths with evidence |
| `GET /prep/roles?limit=` | Ranked role recommendations (`roles-v1`) |
| `GET /prep/roles/{slug}` | Role fit for one role |
| `GET /prep/roles/{slug}/technical-questions?level=` | Beginner / intermediate / advanced + project questions |
| `GET /prep/roles/{slug}/hr-questions` | Personalised HR questions |
| `GET /prep/guidance/{question_id}?role=` | Answer guidance |
| `GET /prep/roles/{slug}/roadmap` | Personalised roadmap |
| `POST /study-documents` | Upload PDF/DOCX (multipart `file`) |
| `GET /study-documents`, `GET/DELETE /study-documents/{id}` | My documents |
| `POST /study-documents/{id}/ask` | One question without a chat (`use_llm` + `llm_consent` optional) |
| `PUT /assistant/conversations/{id}/study-document` | Attach / detach (`{document_id: int \| null}`) |
| `POST /interviews/sessions` | New optional `target_role` |
| `GET /assistant/conversations/{id}` | Now includes `study_document_id`, `target_role` |

All are authenticated and scoped to the signed-in user. Other users' resumes, documents and conversations return 404;
unauthenticated requests return 401.

## 5. Database

- **New migration `f2b4d6a8c0e1` (study documents)** — additive only:
  - `study_documents` (owner, file name, type, size, sha256, page/section/char/chunk counts, warnings);
  - `study_document_chunks` (passage text, page, section).
  - The original file is **not** stored. Deleting a user deletes their documents (cascade).
  - The downgrade refuses while documents exist, unless `-x study_allow_data_loss=true`.
- Role selection, prep memory and mock-interview roles use the existing `conversations.context` and
  `interview_sessions.summary` JSON columns: **no other schema change**.
- Applied to `career_companion_test` only (tests + demo).
- **`career_companion_dev`:** migrated to head (`a7c9e1b3d5f6`) on 2026-11-25 with the owner's approval, after a
  verified backup (see `FINAL_DATABASE_MIGRATION_CHECKLIST.md`).

## 6. AI model / provider

- **Preparation agent:** deterministic and grounded (resume + curated guides), so it always works without an AI
  provider. AI rewording is not applied to these answers, and the chat says so.
- **Document Q&A:**
  - The extractive answer always works.
  - With the student's opt-in and consent, the configured provider writes the answer: **local Ollama `gemma3`**
    (verified live), or Groq if configured.
  - It must cite excerpts and pass a wording-support check; otherwise the extractive answer is shown with a warning.
- **Interview feedback:** rubric scoring, with optional AI coaching (unchanged).
- **Retrieval:** local `all-MiniLM-L6-v2` embeddings when available (loaded once, vectors cached per document), with
  BM25 keyword fallback.
- No paid or mandatory API is required.

## 7. Tests (actual results — details in `CAREERNOVA_TEST_REPORT.md`)

- **Final (2026-11-25, after the post-migration fixes):** backend **1267 passed, 0 failed**; frontend **411 passed** (21 files, 2 workers); build OK.
- Post-migration fixes: off-topic short questions are no longer answered from the product guide; the interview suggestion opens the Interview Prep Assistant directly (details in `CAREERNOVA_IMPLEMENTATION_REPORT.md` §7b).
- Earlier (2026-11-24): backend 1238 passed, frontend 402 passed. The later items below are that day's figures.
- Backend full suite after the 2026-11-24 changes: **1238 passed, 0 failed, 0 errors, 0 skipped** (including the 63 real-model tests).
- New and affected backend files: `test_prep_agent` 14 passed, `test_study_documents` 19 passed, `test_migrations`
  14 passed.
- Frontend: **402 passed** (20 files); production build OK.
- Live demos A, B and C passed on the test database (see `CAREERNOVA_DEMO_GUIDE.md`).

## 8. Known limitations

- **No OCR.** Scanned PDFs are rejected with an explanation; partly scanned PDFs warn which pages are unsearchable.
- **Extractive answers quote sentences.** Without AI, a follow-up like "explain that in more detail" returns the same
  passage. AI mode can rephrase, but only within the document.
- **Deterministic question generation from documents** relies on definitional sentences ("X is …"). Narrative
  documents fall back to frequent terms, which can be weaker; AI mode produces better questions.
- **AI answers on CPU are slow:** about 15–60 s with Gemma 3.
- **Role fit is skill coverage**, not a hiring prediction. It does not read job seniority or soft skills.
- **"Which skills am I missing for my best match?"** still uses stored skill-gap recommendations (existing tool).
- **Mock-interview scores** are rubric key-point coverage, labelled "automated guidance, not a hiring decision".

## 9. Remaining incomplete requirements

None of the HR requirements (original nine or the 2026-11-25 feedback) is unimplemented. The dev database is
migrated (2026-11-25). Still for the owner: decide about the accidental test account (user 5) in dev.

## 10. Start the application

```powershell
cd "<project-root>"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
```powershell
cd "<project-root>\frontend"
npm run dev
```

- To use the AI options, set `LLM_PROVIDER=ollama` in `.env` (Ollama running with `gemma3`).
- Dev is already migrated to head; the record is in `FINAL_DATABASE_MIGRATION_CHECKLIST.md`.

Demo steps: `CAREERNOVA_DEMO_GUIDE.md`.
