# Approach and Methodology

## 1. Resume data preparation

**Parsing.** PDF text is extracted with `pypdf`; DOCX documents are read paragraph by paragraph (including tables) with `python-docx`. The parser detects section headings (summary, skills, technical/soft skills, education, experience, internships, projects, certifications, languages, achievements) and returns a structured JSON object. Scanned PDFs (OCR) are not supported.

**Cleaning and structuring.**
- Skill lists are split on commas, semicolons, bullets and line breaks; labels such as `Programming Languages:` are removed.
- Every raw skill is normalized against a canonical catalog of 133 skills and ~110 aliases. Matching ignores case, spaces, dots, hyphens and slashes, which also repairs PDF spacing artefacts (`A WS` → `AWS`). Proficiency words (`Basic`, `Intermediate`) are discarded as noise. Unknown skills are kept with category `other` rather than dropped.
- Normalized skills are stored in `resume_skills` with the section they came from as evidence.

**Candidate profile for embedding.** The candidate representation combines:

| Field | Source (priority order) |
|---|---|
| Skills | Normalized resume skills |
| Degree | Student profile → first parsed education entry |
| Location | Request override → student profile → parsed resume address |
| Summary | Parsed professional summary (first 500 characters) |

The query text is `Skills: … / Education: … / Summary: …`. Names, e-mail addresses and phone numbers are never included.

## 2. Internship dataset

`backend/data/internships.json` contains **180 synthetic internship postings** with invented company names, taken from the Milestone 2 reference project. It is not real job-market data. Only the JSON file was reused; the reference project's pickle and FAISS files were never extracted or loaded.

Every record is validated with a strict schema (unknown fields rejected): UUID identifier, company, title, domain, location, work mode (`Onsite`/`Hybrid`/`Remote`), duration (1–104 weeks), stipend (0–1,000,000 INR/month), minimum education, 1–30 required skills, preferred skills, description. The validator also rejects duplicate IDs, duplicate skills within a list, skills that are both required and preferred, and skills that do not map to the canonical catalog.

## 3. Embedding generation

| Item | Value |
|---|---|
| Model | `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0) |
| Revision | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (pinned) |
| Dimension | 384 |
| Normalization | L2-normalized (unit vectors) |
| Runtime | CPU, local files only, loaded lazily |

**Internship text** (one document per internship):

```
<Title> at <Company>
Domain: <domain>
Required skills: <comma-separated>
Preferred skills: <comma-separated>
Minimum education: <requirement>
Location: <location>, <work mode>
<description>
```

Skills are listed plainly because candidate queries are mostly skills. The same text is stored in `knowledge_documents.content`, so what is retrieved is exactly what was embedded.

## 4. Vector database and retrieval

- **Index:** FAISS `IndexIDMap2(IndexFlatIP)`; exact (brute-force) inner-product search, appropriate for 180 vectors. Vector IDs are `knowledge_documents.document_id`.
- **Build:** rebuilt from PostgreSQL only; a new file is written and fsynced, then `manifest.json` is atomically replaced. The manifest records the model, revision, dimension, vector count, build time and the file's SHA-256.
- **Load:** the file is verified against the manifest (checksum, count, dimension, model) before use.
- **Search:** cosine similarity between the query vector and every internship vector; results are re-checked against PostgreSQL (active, indexed) before being returned.

**Candidate generation for matching:** union of (a) the FAISS nearest neighbours (at least 50, or 5 × k) and (b) every active internship sharing at least one skill with the candidate. Internships outside the FAISS top-N still receive their exact similarity, read back from the index (`IndexIDMap2.reconstruct`).

## 5. Compatibility scoring (algorithm v1)

```
score = 100 × (0.50·skills + 0.20·semantic + 0.15·education + 0.15·location)
```

rounded to one decimal and clamped to 0–100.

| Component | Rule |
|---|---|
| **Skills** | 0.8 × required coverage + 0.2 × preferred coverage. Required only → required coverage. Preferred only → 0.8 × preferred coverage. No skills listed → 0.5 (`not_stated`). |
| **Semantic** | `clamp((cosine − 0.40) / 0.35, 0, 1)` — see calibration below. |
| **Education** | Degree family *and* level must fit. Exact fit 1.0; non-CS branch where CS is preferred 0.85; any-bachelor: master's 0.8, diploma 0.2; higher level 0.7; closely related computing degree 0.6; right degree, other subject 0.5; lower level 0.3; unrelated field 0.1. |
| **Location** | Remote 1.0; same city 1.0 (aliases such as Bangalore = Bengaluru); hybrid in another city 0.3; onsite in another city 0.0. |

**Missing information** is scored conservatively and reported: student data unknown → 0.3 (`unknown`); posting does not state it → 0.5 (`not_stated`); semantic unavailable → 0.3 (`unavailable`). Weights are not redistributed, so missing data never inflates a score.

**Caps:** no required skill matched → score ≤ 50; posting lists no skills → label ≤ Fair; any component not assessed → label ≤ Strong.

**Labels:** Excellent ≥ 80, Strong ≥ 65, Fair ≥ 45, Weak < 45.

**Ranking:** score, then required-skill coverage, then internship ID (fully deterministic).

### Semantic calibration

Raw MiniLM cosine similarities occupy a narrow band, and unrelated pairs are far from zero. A naive mapping would therefore inflate scores. The bounds were chosen from a calibration study (`python -m evaluation.calibration_study`) on all 180 postings and 11 synthetic personas (1,980 pairs):

| Pairs | n | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| Related (same domain) | 186 | 0.499 | 0.572 | 0.627 | 0.675 | 0.730 |
| Unrelated | 1,434 | 0.308 | 0.370 | 0.420 | 0.469 | 0.535 |

| Bounds | Unrelated median → | Related median → | Pairs saturated at 1.0 | Unrelated-chef persona max → |
|---|---|---|---|---|
| 0.15–0.65 (rejected) | 0.541 | 0.953 | 3.5% | 0.502 |
| 0.35–0.75 | 0.176 | 0.691 | 0.05% | 0.128 |
| **0.40–0.75 (in use)** | **0.058** | **0.647** | **0.05%** | **0.003** |
| 0.45–0.80 | 0.000 | 0.504 | 0% | 0.000 |

0.40–0.75 maps a typical unrelated pairing near zero while keeping related pairings in the upper half without saturating. Full results: `docs/assignment/evaluation/calibration_results.json`.

## 6. RAG explanation layer

Explanations are **deterministic templates** filled exclusively from:
- the retrieved internship record in PostgreSQL (title, company, required/preferred skills, education requirement, work mode, location), and
- the candidate's extracted data (normalized skills, degree category, location).

Every result lists matched and missing required/preferred skills, one sentence per score component, any caps applied, and any missing candidate information.

**Why no LLM:** the assignment requires that companies, internships, requirements and candidate facts are never invented. Deterministic explanations satisfy that by construction, are reproducible and testable, and add no external dependency. An LLM layer is planned for later modules (cover letters, interview preparation, assistant); there it will receive retrieved records as its only factual context, and generated text will be labelled separately from source facts.

## 7. Evaluation methodology

`python -m evaluation.rag_evaluation` runs the full pipeline on the isolated `career_companion_test` database:

1. Validate the dataset and verify that every imported row is identical to its source record.
2. Build the FAISS index with the real model in a temporary folder.
3. Verify the index: manifest consistency, vector count, and re-embedding of stored texts (cosine with stored vectors must exceed 0.999).
4. For each of 10 synthetic profiles:
   - render a DOCX resume, parse it with the production parser and store it
   - run pure semantic retrieval (top 5) and full matching (top 5)
   - check grounding: titles, companies and skill lists must equal the source record
   - flag results outside the evaluator's expected domains or scoring below 45
5. Diagnostic only: compare retrieval with experience/project text appended to the query.

The runner refuses to start unless the database name ends in `_test`. Outputs (both in `docs/assignment/evaluation/`): `evaluation_results.json` and the generated `EVALUATION_RAW.md`.

The evaluator's expected domains are a human judgement used only for flagging; they are never given to the system.
