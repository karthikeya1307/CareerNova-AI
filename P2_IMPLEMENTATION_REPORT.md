# P2 Implementation Report — Resume Parsing, Resume Readiness, Job Matching

Date: 2026-11-19 · CareerNova AI · No database migration needed for P2 · `career_companion_dev` untouched.

## 1. Resume parsing

| Improvement | How | Where |
|---|---|---|
| Multi-column PDFs | Text positions are read from each page; a two-column layout (a clear vertical gap with substantial text on both sides at overlapping heights) is read column by column. Used only when it recognises at least as many section headings as plain extraction, so single-column resumes are unaffected. | `resume_parser.page_text`, `split_columns` |
| Contact details | **Bug fixed:** the phone number could swallow the first digits of the next line (e.g. `+91 90000 00002\n12` from the address). Phone numbers no longer span line breaks. | `extract_contact_information` |
| Dates and durations | Ranges (`Jan 2024 - Jun 2024`, `06/2022 to 08/2022`, `Sept 2023 – Present`) with inclusive month counts; bare years stay years (no invented month); ranges that end before they start are flagged. | `resume_insights.parse_dates` |
| Extraction confidence | Per field/section (contact shape checks, entry text length, skill count) and an overall confidence. | `resume_insights.analyze` |
| Missing information | Core fields (name, email, phone, skills, education) and recommended sections (summary, experience/internships, projects, profile link, certifications, achievements); warnings for undated roles, invalid ranges, merged lines. | `resume_insights.analyze` |
| Duplicate uploads | Same file bytes (`identical_file`) or the same extracted content (`same_content`) among the student's own resumes. Reported in the upload response (`duplicate_of`, `duplicate_kind`) and as a warning in the UI — **not blocked**, so existing clients keep working. | `routes/resumes.find_duplicates` |
| Review and correct | `PUT /resumes/{id}/extracted-data` saves the student's version as a new extraction (`user_corrected`); the parser's version is kept, skills are re-synced, and matching/documents/assistant use the correction automatically (they read the newest extraction). Re-parse returns to the parser's version. Size-validated (5,000 chars, 100 items). | `routes/resumes.correct_extracted_data` |

New read endpoints: `GET /resumes/{id}/analysis`, `GET /resumes/{id}/readiness` (owner only; 404 for others).
Additive response fields: upload `duplicate_of`, `duplicate_kind`; detail `parser_type`, `corrected`.

## 2. General Resume Readiness (0–100, `readiness-v1`)

Independent of any job. Documented in `backend/services/resume_readiness.py`:

| Category | Max | Points for |
|---|---|---|
| Contact and profile | 10 | name 3, email 3, phone 2, LinkedIn/GitHub 2 |
| Structure and completeness | 15 | summary, skills, education, experience/internships, projects — 3 each |
| Skills and evidence | 20 | skill count (up to 8) + share of skills shown in experience/projects (12) |
| Experience and internships | 15 | entry 5 + dated share 4 + action-verb share 3 + quantified-result share 3 |
| Projects | 15 | project 5 + second project 2 + described share 4 + share naming a technology 4 |
| Education | 10 | entry 4 + recognised degree 3 + year 3 |
| Certifications and achievements | 5 | certification 3 + achievement 2 |
| Formatting and readability | 10 | parsing confidence (5), no warnings (2), summary length (1), focused skills list (1), clean contact line (1) |

Every point has a reason (earned or missed); missed points carry a specific recommendation. Empty
content earns nothing (an empty resume scores 0). Labels: 85+ Excellent, 70+ Good, 50+ Fair, else
Needs work. A disclaimer states it is not a prediction of any employer's ATS. It is recalculated on
every read, so corrections and re-parses apply immediately.

## 3. Job matching — two modes (`insights-v1`, `backend/services/job_insights.py`)

**For My Resume** — the existing ranked matching (`POST/GET /matches/resumes/{id}`, single-job scoring)
now returns an additive `insights` block per result.

**Explore Any Job** — `GET /matches/explore?resume_id=&q=&domain=&location=&work_mode=&category=&skip=&limit=`
lists every open opportunity (not only the best matches; closed/past-deadline jobs hidden). With a
resume, every job gets insights (scored without semantic similarity, stated in the response); without
one, it is a plain browse. Nothing is saved.

Insights per job:
* **Skill Match** = 100 × (0.8 × required share + 0.2 × preferred share); matched = 1, partial
  (closely related skill on the resume) = 0.5. `None` when the posting lists no skills.
* **Eligibility**: eligible / open (no requirement) / check / unknown / not eligible / closed — from the
  education component and the deadline.
* **Application Readiness** = 0.6 × Skill Match + 0.25 × resume readiness + 0.15 × eligibility value.
* **Category**: Apply Now (≥70, no fully missing required skill, eligible/open) · Long-Term Target (not
  eligible, closed, or <40 with 3+ missing required) · otherwise Apply After Improvement.
* Matched / partial (with the related skill) / missing skills, reasons, improvement steps (from the
  learning plans), application URL, source and dates. No guarantee of selection is implied.

## 4. Frontend

* Resumes: **Resume readiness** panel (score, label, 8 expandable categories with point-by-point reasons,
  strengths, weaknesses, recommendations, parsing confidence/missing fields/warnings, disclaimer);
  **Edit details** form (all fields; entries as blocks; skills comma-separated) with "Corrected by you";
  duplicate-upload warning.
* Matches: **For my resume / Explore any job** tabs; category badge per result; insights panel (Skill Match,
  Eligibility, Application Readiness, matched/partial/missing skills, reasons, improvements, application
  link, source); Explore search (role/company/domain, location, work mode), category filter with counts,
  paging.
* Backups of every edited page: `frontend/.backups/p2/` (git-ignored).

## 5. Tests

| Suite | Result |
|---|---|
| `tests/test_resume_quality.py` (new) | 28 passed — two-column PDF, right-aligned dates not split, PDF = DOCX sections, incomplete resume, phone fix, 5 date cases, confidence/warnings, readiness per category, empty = 0, evidence, duplicates (file and content, per user), owner-only endpoints, corrections (new extraction, skills synced, readiness changes, re-parse reverts), validation |
| `tests/test_job_matching_modes.py` (new) | 13 passed — formula, partial/missing, categories, eligibility states, no-skills case, For My Resume insights, Explore with/without resume, category counts and filter, search/paging, closed jobs hidden, other student's resume 404, auth required |
| Frontend (resumes + matches) | 39 passed, incl. 8 new P2 tests |
| Full frontend suite | **384 passed**; production build OK |
| Full backend suite | **1170 passed, 0 failed, 0 skipped, 0 errors** (23 min, `career_companion_test`) |

`tests/resume_factory.py` builds real PDF (single/two-column, any content order) and DOCX resumes with pypdf/python-docx — no new dependency.

## 6. Limitations

* Scanned (image-only) PDFs still have no text to extract (no OCR).
* Column detection handles two columns; three or more columns, tables drawn as text boxes, or
  sidebars spanning only part of a page may still be read in mixed order (plain extraction is kept
  whenever the column order is not better).
* Duplicate detection compares against the student's last 50 resumes.
* Explore mode skips semantic similarity (fast, deterministic); the ranked "For my resume" run uses it
  when the vector index is available — on the dev machine the index still needs a rebuild (owner approval).
* Listings are the curated sample dataset (labelled "sample data" in the UI); no live job sources yet (P3).
* Not verified live in the browser against the dev database: the new backend needs the pending
  migrations applied first (owner approval).
