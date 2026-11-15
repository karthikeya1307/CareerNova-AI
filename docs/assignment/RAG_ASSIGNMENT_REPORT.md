# RAG-based Internship Matching System — Assignment Report

**Project:** AI Career Companion (backend modules 2–4)
**Assignment:** RAG-based Internship Matching System, set by Vijay Parmar
**Status:** implemented, verified and evaluated on the isolated test database

| Document | Contents |
|---|---|
| `RAG_ASSIGNMENT_REPORT.md` | This summary: requirements, evidence, results and limitations |
| `SYSTEM_ARCHITECTURE.md` | Components, data stores, retrieval flow and safety properties |
| `APPROACH_AND_METHODOLOGY.md` | Data preparation, dataset, embeddings, FAISS, scoring, calibration and evaluation method |
| `TEST_CASES.md` | The 10 evaluation scenarios, the system checks and the automated test suites |
| `EVALUATION_RESULTS.md` | Actual results for every profile, findings and limitations |
| `evaluation/evaluation_results.json`, `evaluation/EVALUATION_RAW.md` | Raw, machine-generated evaluation output |
| `evaluation/calibration_results.json` | Raw output of the semantic calibration study |

## 1. Summary

The system:
1. Parses a student's resume and normalizes its skills to a canonical catalog.
2. Embeds a candidate profile and 180 internship postings with `all-MiniLM-L6-v2` (384 dimensions).
3. Retrieves candidates from a FAISS vector index, combined with every internship that shares a skill.
4. Grounds every candidate in PostgreSQL.
5. Ranks internships with a transparent compatibility score: skills 50%, semantic similarity 20%, education 15%, location 15%.

Each recommendation lists the matched and missing skills, and gives a sentence for every score component. The sentences are built only from the retrieved internship record and the candidate's extracted data, so no internship, company, requirement or candidate fact can be invented.

**Key results** (actual run, see `EVALUATION_RESULTS.md`):

| Measure | Result |
|---|---|
| System checks (dataset, database, model, index, retrieval, grounding) | **9/9 passed** |
| Recommendations grounded in source records | **50/50** |
| Domain precision@5: pure FAISS retrieval | **38/45 (84%)** |
| Domain precision@5: final matching (retrieval + skill-aware scoring) | **39/45 (87%)** |
| Results flagged for review | 12/50 (6 outside expected domain, 6 scoring below 45) |
| Automated tests | **373 passed, 0 failed, 0 skipped** |

## 2. Requirement-by-requirement verification

### 2.1 Resume data preparation — met, with gaps F2 and F6
| Requirement | Evidence | Status |
|---|---|---|
| Resume parsing and extraction | `resume_parser.py`. All 10 synthetic DOCX resumes parsed by the production parser; skills, education, experience and projects extracted (`tests/test_rag_evaluation.py`, 10 tests) | ✅ |
| Cleaning and structuring | Skill splitting, label and noise removal, canonical normalization (`skill_normalizer.py`, 102 tests) | ✅ |
| Normalized skills, education, experience, projects | Skills are normalized and stored. Education feeds degree classification. Experience and projects are extracted and stored, but **not used for matching** (finding F2) | ⚠️ |
| Candidate profile for embedding | `candidate_profile.py`: skills, degree, location and summary, with the source of each recorded and no personal identifiers | ✅ |

### 2.2 Internship dataset — met; dataset is synthetic; one quality issue (F5)
| Requirement | Evidence | Status |
|---|---|---|
| Validate 180 records | 180/180 valid against a strict schema | ✅ |
| Title, company, description, skills, education, location, mode, duration | All fields present in every record; 0 missing values | ✅ |
| Missing values, duplicates, invalid records | 0 missing, 0 duplicate IDs, 0 duplicate company + title + location, 69 skills all mapped. **10 postings combine Onsite/Hybrid with location "Remote"** (F5) | ⚠️ |
| Documented as synthetic | `APPROACH_AND_METHODOLOGY.md` §2; README | ✅ |

### 2.3 Embedding generation — met
| Requirement | Evidence | Status |
|---|---|---|
| `all-MiniLM-L6-v2` | Pinned revision `1110a243…`, safetensors only, offline | ✅ |
| 384-dimensional embeddings | System check and `tests/test_embeddings_model.py` | ✅ |
| Internship and candidate embeddings | Same model and normalization for both | ✅ |
| FAISS index and metadata consistency | 180 vectors = 180 documents = 180 active internships; manifest checks out; re-embedded texts match stored vectors (cosine 1.000000) | ✅ |

### 2.4 Vector database retrieval — met
| Requirement | Evidence | Status |
|---|---|---|
| Semantic search against FAISS | `vector_index.search` and `GET /internships/search` | ✅ |
| Retrieved internships active and valid | Every result re-checked in PostgreSQL. Tests cover deactivated internships, deleted internships and an outdated index | ✅ |
| Similarity scores and ranking | Cosine similarity, sorted in descending order (checked for every profile) | ✅ |
| Grounded in original records | 50/50 final results equal their source JSON record (title, company, required and preferred skills) | ✅ |

### 2.5 Matching and RAG explanation — met, with ranking weaknesses F1 and F2
| Requirement | Evidence | Status |
|---|---|---|
| Candidate and internship information used correctly | Grounding checks; data source recorded for degree and location | ✅ |
| Skill, education, semantic and location compatibility | `compatibility.py` (87 tests); the semantic calibration validated on 1,980 pairs | ✅ |
| Matched skills, missing skills, explanations | Present in every result, in the same structure every time | ✅ |
| Nothing invented | Deterministic templates built only from source records; 50/50 grounded | ✅ |
| LLM layer only if needed | Not added: the deterministic explanations meet the requirement (`APPROACH_AND_METHODOLOGY.md` §6) | ✅ |

### 2.6 Evaluation with at least 10 synthetic profiles — met
All 10 required scenarios were run with the real model. For each profile, the extracted information, the top 5 from retrieval, the top 5 final matches, cosine and calibrated semantic scores, compatibility scores, matched and missing skills and the explanations are in `EVALUATION_RESULTS.md` §3. Each profile's raw output is in `evaluation/EVALUATION_RAW.md`. Weak and incorrect recommendations are identified there rather than hidden.

### 2.7 Deliverables — met
All five documents are in `docs/assignment/`. The code (`backend/`, `evaluation/`), the dataset (`backend/data/internships.json`) and the raw outputs are enough to reproduce the results:

```bash
python -m backend.manage download-embedding-model   # one-time
python -m evaluation.calibration_study
python -m evaluation.rag_evaluation                  # career_companion_test only
python -m pytest
```

## 3. Results by profile

| Profile | Final top 5 in expected domain | Best score | Verdict |
|---|---|---|---|
| 01 AI/ML | 5/5 | 72.7 Strong | Good; no CV/DL-specific postings exist |
| 02 Backend | **2/5** | 65.6 Strong | **Weak ranking.** Backend role ranked 5th (F1) |
| 03 Data Science | 5/5 | 79.7 Strong | Best fit; all results "Strong" |
| 04 Generative AI | 5/5 | 54.6 Fair | Correctly honest; dataset has no GenAI roles (F3) |
| 05 Multi-language | 4/5 | 78.1 Strong | Good |
| 06 Strong education | 5/5 | 57.5 Fair | Correct degree handling; grades not scored (F4) |
| 07 Relevant experience | 5/5 | 69.1 Strong | Excellent domain fit |
| 08 Academic projects | 5/5 | 55.5 Fair | **Project skills not recognised** (F2) |
| 09 Partial overlap | 3/5 | 53.8 Fair | Reasonable; honestly labelled "Fair" |
| 10 Limited information | n/a | 32.8 Weak | Correctly conservative; asks for missing data |

## 4. Known limitations

The full list, with evidence, is in `EVALUATION_RESULTS.md` §4.
- **F1:** when scores are close, location and education can outrank a better role fit (profile 02).
- **F2:** skills shown only in project or experience descriptions are not recognised (profile 08).
- **F3:** the dataset has no Generative AI, LLM or computer-vision postings.
- **F4:** academic distinction (grades, awards) is not scored.
- **F5:** 10 postings have contradictory work mode and location.
- **F6:** resume addresses in contact lines are not extracted, so location relies on the profile page.
- The dataset is **synthetic** (180 postings, invented companies), so results show how the system behaves, not real-market outcomes.

None of these were changed during the evaluation. F1 and F2 would change the reviewed scoring algorithm and need approval and a new algorithm version.
