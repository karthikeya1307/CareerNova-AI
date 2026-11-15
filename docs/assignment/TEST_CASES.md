# Test Cases

Two kinds of tests support the assignment:
1. **Evaluation scenarios.** Ten synthetic candidate profiles are run through the full pipeline by `python -m evaluation.rag_evaluation`.
2. **Automated tests.** The pytest suite runs on the isolated `career_companion_test` database.

## 1. Evaluation scenarios (synthetic candidate profiles)

All profiles are defined in `evaluation/profiles.py`. Each is rendered as a real DOCX resume and parsed by the production parser. Names, e-mails and phone numbers are fictional placeholders.

"Profile page" means what the student typed into their profile. If it's blank, the system falls back to the resume. "Expected domains" is the evaluator's judgement and is used only to flag results; the system never sees it.

| # | Scenario | Resume content | Profile page | What it tests | Expected domains |
|---|---|---|---|---|---|
| 01 | AI/ML candidate | Python, TensorFlow, PyTorch, Deep Learning, Machine Learning, NumPy, Computer Vision; B.Tech CSE; CNN project | B.Tech CS, Bengaluru | ML skills against Data Science postings | Data Science |
| 02 | Backend developer | Python, FastAPI, Django, PostgreSQL, REST API, Docker, Git; B.Tech IT | B.Tech IT, Pune | Backend skills; whether backend roles rank first | Software Dev., Web Dev. |
| 03 | Data Science candidate | Python, Pandas, NumPy, Scikit-learn, Statistics, SQL, Tableau; B.Sc Statistics | B.Sc Statistics, Hyderabad | Strong skill fit; B.Sc against engineering requirements | Data Science, Business Analysis |
| 04 | Generative AI candidate | Python, LLM, Generative AI, NLP, PyTorch, Prompt Engineering, LangChain; M.Tech CS; RAG project | M.Tech CSE, Chennai | A specialism the dataset doesn't contain; must not invent GenAI roles | Data Science |
| 05 | Multiple programming skills | Java, Python, C++, JavaScript, Kotlin, Go, SQL, Git; B.Tech CS | B.Tech CSE, Noida | Breadth of skills across domains | Software, Web, Mobile Dev. |
| 06 | Strong education | Python, Data Structures, Algorithms, Machine Learning; M.Tech CS (gold medal, CGPA 9.6) | *degree blank*, Kolkata | Degree read from the resume; few skills | Data Science, Software Dev. |
| 07 | Relevant experience | Selenium, Java, JIRA, Agile, SQL; BCA; QA automation internship | *degree blank*, Chennai | Experience section; BCA against other requirements | QA/Testing |
| 08 | Academic projects | Figma, HTML, CSS; B.Sc CS; two UI/UX projects (wireframes, prototypes, user research) | *blank* | Project evidence; missing location | UI/UX Design, Web Dev. |
| 09 | Partial skill overlap | Linux, Excel, Communication, Networking; B.Com | B.Com, Jaipur | Weak, cross-domain overlap; non-computing degree | Cybersecurity, DevOps/Cloud, Business Analysis |
| 10 | Limited information | Communication only; no summary, education or location | *blank* | Missing data handled conservatively and reported | — |

**What every scenario checks automatically:**
- Every recommended internship exists in PostgreSQL with exactly the source record's title, company and required and preferred skills.
- Matched skills are a subset of both the candidate's skills and the internship's skills.
- Pure retrieval returns only active internships, ordered by similarity.
- Results outside the expected domains, or scoring below 45, are flagged for review.

## 2. System checks run by the evaluator
| Check | Pass condition |
|---|---|
| Dataset validity | 180/180 valid, no duplicate IDs, no missing values |
| Dataset duplicates | No duplicate company + title + location |
| Skill mapping | Every dataset skill maps to the canonical catalog |
| Database vs. source file | Every imported row identical to its JSON record (fields and skills) |
| Embedding model | `all-MiniLM-L6-v2`, 384 dimensions, unit vectors |
| Index consistency | Vectors = indexed documents = active internships = 180; model, revision and dimension match; SHA-256 verified |
| Stored vectors | Re-embedding stored document text gives cosine > 0.999 with the stored vectors |
| Retrieval | Results active and sorted by similarity, for every profile |
| Grounding | Every final recommendation grounded in its source record |

## 3. Automated tests related to the assignment
| Test file | Tests | Covers |
|---|---|---|
| `tests/test_skill_normalizer.py` | 102 | Every dataset skill maps to itself; aliases, spacing repair, noise removal, de-duplication |
| `tests/test_resume_lifecycle.py` | 24 | Upload stores normalized skills; re-parse keeps history; ownership; download and delete safety |
| `tests/test_internship_seed.py` | 23 | Full dataset validation; detection of bad records; idempotent import |
| `tests/test_vector_index.py` | 15 | Native index files, no pickle, checksum and model checks, inactive internships never returned, atomic and concurrent rebuilds |
| `tests/test_internships_api.py` | 30 | Catalog, filters, semantic search API, admin permissions, soft delete |
| `tests/test_embeddings_model.py` | 5 | Real model offline, 384 dimensions, safetensors only, full-dataset index, model not loaded at API startup |
| `tests/test_compatibility.py` | 87 | Every scoring rule; education table; false-positive degree text; bounds and mathematical consistency |
| `tests/test_matching_agent.py` | 18 | Candidate sources, union without duplicates, inactive/expired exclusion, graceful degradation, concurrency, persistence |
| `tests/test_matches_api.py` | 16 | Ownership on every endpoint, runs, history, validation, deletion cascades |
| `tests/test_matching_real_model.py` | 5 | Real model on all 180 postings: personas reach their domains, unrelated resumes score low, calibration guard |
| `tests/test_rag_evaluation.py` | 12 | All 10 profiles parse correctly; scenarios match the assignment; the runner refuses non-test databases |

For the total test count and results, see `EVALUATION_RESULTS.md` §5.

## 4. Reproducing
```bash
python -m backend.manage download-embedding-model   # one-time, ~92 MB
python -m evaluation.calibration_study               # in memory, no database
python -m evaluation.rag_evaluation                  # uses career_companion_test only
python -m pytest                                     # full test suite
```
