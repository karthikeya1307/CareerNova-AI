# P3 Implementation Report — Skill Roadmaps, Career Tracks, Ollama, Job Sources

Date: 2026-11-24 · CareerNova AI · New migration `e1f3a5c7b9d2` (rehearsed, **not applied** to `career_companion_dev`).

State before P3 (verified in code): skill-gap recommendations had statuses pending / in_progress /
completed / dismissed per resume, no per-skill progress, no per-job roadmap; no career tracks; only a
Groq LLM provider; internships had `source` (dataset/admin/manual) but no source URL, posting or
verification date, or de-duplication.

## 1. Per-job skill-gap roadmap with persisted progress

* New table `skill_progress` (one row per student and skill): **Not Started → Learning → Practiced → Completed**.
  Progress applies to every job needing the skill and is mirrored into the student's current
  recommendations (not_started→pending, learning/practiced→in_progress, completed→completed).
* `GET /skill-gaps/progress`, `PUT /skill-gaps/progress {skill, status}` (skill names normalised;
  unknown skills 404; names like "CI/CD" work because the name is in the body).
* `GET /skill-gaps/resumes/{rid}/internships/{iid}/roadmap`: the job's missing and partial skills in
  prerequisite order, each with importance, why the job needs it (quoting the posting sentence that
  names the skill), current resume evidence, learning topics/hours/level (learning_plans.json), an
  official documentation link when curated, up to 3 interview questions from the question bank, a
  practice project and the saved status; plus skill match and progress counts.
* Frontend: "Your learning roadmap" on the per-job skill-gap page with a progress selector per skill
  (reverts and explains on failure).

## 2. Career tracks for 11 roles

Software Developer, AI Engineer, Machine Learning Engineer, Data Scientist, Data Analyst, Web
Developer, Java Developer, Python Developer, Cybersecurity Analyst, Cloud Engineer, DevOps Engineer
(`backend/data/career_tracks.json`, `tracks-v1`; the loader checks all 11 are present and complete).

Each: summary, core and advanced skills (with resume coverage and the student's progress), staged
roadmap, exercises, projects, resume advice, interview questions **taken from the existing question
bank** (a test asserts every question is from the bank), learning topics from the curated plans, and
official documentation links (27 curated official sites; a test asserts no other link can appear).
Relevant jobs: open listings ranked by how many track skills they ask for (+1 for a matching domain).

API: `GET /career-tracks`, `GET /career-tracks/{slug}?resume_id=`, `GET /career-tracks/{slug}/jobs`.
Frontend: **Career tracks** in the sidebar, list and detail pages.

## 3. Optional Ollama provider (local Gemma 3), Groq preserved

* `LLM_PROVIDER=ollama` with `OLLAMA_URL` (default `http://127.0.0.1:11434`), `OLLAMA_MODEL` (default
  `gemma3`), `OLLAMA_TIMEOUT_SECONDS` (default 120). `LLM_PROVIDER=groq` works exactly as before.
* Uses Ollama's `/api/chat` with JSON output. Unreachable server, missing model (HTTP 404 → "run:
  ollama pull …"), bad JSON or errors raise `LLMError`, so every AI feature falls back to its standard
  answer; an invalid URL turns AI off rather than failing. Status reports `location: local|external`.
* **Live check on this machine (synthetic prompt, no personal data):** `gemma3:latest` returned valid
  JSON grounded in the given facts in **96 s** on the first call (model load on CPU) — hence the
  120 s default. All AI use remains opt-in with consent and fact-checked as before.

## 4. Job-source tracking

* `internships` gains `source_url`, `posted_at`, `last_verified_at` (NULL = unknown, never guessed)
  and `dedup_key` (sha256 of normalised title|company|location, backfilled by the migration).
* Every listing response shows `source_label` (dataset rows: **"Sample listing (curated dataset)"**)
  and `freshness` (verified within 30 days / stale / unverified / expired).
* Admins: create/edit with source URL and posting date (URL validated), **duplicate listings
  rejected with 409** naming the existing listing, **Mark verified** (`POST /internships/{id}/verify`,
  audited).
* Filters: `source=` on `GET /internships/` and `GET /matches/explore`; Explore shows each duplicate
  once (`duplicates_hidden`). Insights carry source label/URL, posting/verification dates, freshness.
* **No live external job source was added**: none is configured with permitted access, and listings
  are never fabricated. The curated dataset stays clearly labelled as sample data.

## 5. Tests added

| File | Tests |
|---|---|
| `tests/test_ollama_provider.py` | 13 — config/defaults, custom URL/model/timeout, invalid URL, Groq unchanged, request shape, 7 failure modes, assistant fallback |
| `tests/test_p3_features.py` | 14 — progress states/validation/isolation/recommendation sync, roadmap content/order/ownership, 11 tracks, bank-only questions, curated-only links, coverage + jobs, sample labels, source details, duplicates (create/update), verification + audit, freshness, source filters, explore de-duplication |
| `tests/test_migrations.py` | +1 (P3 backfill and downgrade protection) and the round trip through all migrations |
| `tests/test_e2e_workflow.py` | 1 — the 10-step journey end to end |
| `frontend/src/features/careerTracks/careerTracks.test.jsx` | 5 — track list, detail (coverage, progress save, roadmap, questions, jobs), not-found, roadmap order/plan/progress, failed save reverts |

## 6. Limitations

* No live job feeds (needs a source with permitted API access); no automatic expiry check against the
  original site — admins use **Mark verified**.
* Local Gemma 3 on CPU is slow (first answer ~1.5 min); requests wait for it. A GPU or a smaller model helps.
* Learning resources are official documentation only; skills without a curated plan show a generic outline (labelled).
* Career-track job lists depend on the curated sample listings.
