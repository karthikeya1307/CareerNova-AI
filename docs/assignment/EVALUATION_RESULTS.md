# Evaluation Results

**Source of every number below:** a real run of `python -m evaluation.rag_evaluation` on `career_companion_test`, generated 2026-11-15 05:05 UTC.

**Inputs:** the real `all-MiniLM-L6-v2` model, all 180 synthetic postings and 10 synthetic candidate profiles.

**Raw output:**
- `docs/assignment/evaluation/evaluation_results.json`: every field, including the full explanation sentences
- `docs/assignment/evaluation/EVALUATION_RAW.md`: generated tables for every profile

## 1. System checks — all passed (9/9)

| Check | Result |
|---|---|
| Dataset: 180 valid records, no duplicate IDs, no missing values | PASS — 180/180 valid, 0 missing, 0 duplicate IDs |
| Dataset: no duplicate company + title + location | PASS — 0 |
| Dataset: every skill maps to the catalog | PASS — 69 distinct skills, none unmapped |
| Database records identical to the dataset file | PASS — 180 rows, 0 mismatches |
| Embedding model | PASS — `all-MiniLM-L6-v2` @ `1110a243`, 384 dimensions, unit vectors |
| FAISS index consistent with model and PostgreSQL | PASS — 180 vectors = 180 indexed documents = 180 active internships; SHA-256 verified |
| Stored vectors match re-embedded source text | PASS — minimum cosine 1.000000 over 12 sampled documents |
| Retrieval: only active results, sorted by similarity | PASS — 0 problems across 10 profiles |
| Every final recommendation grounded in its source record | PASS — 50/50 results grounded |

## 2. Summary across profiles

The "in expected domain" columns use the evaluator's judgement of relevant domains (see `TEST_CASES.md`).

| Profile | Retrieval top 5 in expected domain | Final top 5 in expected domain | Best score | Mean top-5 score | Labels |
|---|---|---|---|---|---|
| 01 AI/ML | 5/5 | 5/5 | 72.7 | 60.4 | Strong 1, Fair 4 |
| 02 Backend | 5/5 | **2/5** | 65.6 | 63.9 | Strong 1, Fair 4 |
| 03 Data Science | 5/5 | 5/5 | 79.7 | 77.4 | Strong 5 |
| 04 Generative AI | 1/5 | 5/5 | 54.6 | 50.1 | Fair 5 |
| 05 Multi-language | 5/5 | 4/5 | 78.1 | 69.5 | Strong 4, Fair 1 |
| 06 Strong education | 5/5 | 5/5 | 57.5 | 52.4 | Fair 5 |
| 07 Relevant experience | 5/5 | 5/5 | 69.1 | 66.3 | Strong 4, Fair 1 |
| 08 Academic projects | 5/5 | 5/5 | 55.5 | 48.5 | Fair 4, Weak 1 |
| 09 Partial overlap | 2/5 | 3/5 | 53.8 | 50.5 | Fair 5 |
| 10 Limited information | n/a | n/a | 32.8 | 30.8 | Weak 5 |

- **Domain precision@5** over the 9 profiles with expected domains: pure retrieval **38/45 (84%)**; final matching **39/45 (87%)**.
  - Skill-aware scoring corrected the noisy retrieval for profiles 04 (1/5 → 5/5) and 09 (2/5 → 3/5).
  - It lowered precision for profiles 02 (5/5 → 2/5, finding F1) and 05 (5/5 → 4/5).
- **Flags:** 12 of 50 final results were flagged for review. 6 were outside the expected domains (profiles 02, 05 and 09) and 6 scored below 45 (profile 10 and one result in 08).
- **Raw cosine range** among final results: 0.202–0.753.

## 3. Per-profile results

Columns:
- **Cosine:** raw cosine similarity between the candidate and the internship.
- **Semantic:** that similarity after calibration, `clamp((cos − 0.40) / 0.35, 0, 1)`.
- **Score:** the final compatibility score (0–100).

Matched skills marked "(pref)" are preferred skills. Full explanation sentences for every result are in `EVALUATION_RAW.md`.

### 01 — AI/ML candidate
**Extracted:**
- Skills: Python, TensorFlow, PyTorch, Deep Learning, Machine Learning, NumPy, Computer Vision
- Degree: B.Tech Computer Science (profile)
- Location: Bengaluru (profile)
- 1 project

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | Machine Learning Intern (Trueform Technologies Pvt Ltd) | Data Science | 0.506 | 0.30 | 72.7 | Strong | NumPy, Python, PyTorch (pref) | Statistics |
| 2 | Machine Learning Intern (Pixelforge Softworks) | Data Science | 0.574 | 0.50 | 60.1 | Fair | Machine Learning, NumPy, Python, Deep Learning (pref), TensorFlow (pref) | Data Analysis, Pandas |
| 3 | Data Science Intern (Foxglove Systems LLP) | Data Science | 0.470 | 0.20 | 58.0 | Fair | Machine Learning, NumPy, Python | Pandas, Scikit-learn |
| 4 | Data Analyst Intern (Northstar AI Inc) | Data Science | 0.452 | 0.15 | 56.3 | Fair | Machine Learning, TensorFlow (pref) | Data Analysis, SQL |
| 5 | Machine Learning Intern (Foxglove Systems LLP) | Data Science | 0.489 | 0.25 | 55.1 | Fair | NumPy, Python | Pandas, SQL |

**Assessment:** correct domain throughout. The dataset has no computer-vision or deep-learning-specific postings, so no posting covers this candidate's specialism. Scores of 55–73 accurately reflect that every match is missing Pandas, SQL or Statistics.

### 02 — Backend developer
**Extracted:**
- Skills: Python, FastAPI, Django, PostgreSQL, REST API, Docker, Git
- Degree: B.Tech IT (profile)
- Location: Pune (profile)

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | Software Testing Intern (Clearwater Solutions) | QA/Testing | 0.498 | 0.28 | 65.6 | Strong | Git, Python, Docker (pref) | Problem Solving, SQL |
| 2 | Software Testing Intern (Quantumly Robotics LLP) | QA/Testing | 0.547 | 0.42 | 64.4 | Fair | Git, Python, Docker (pref), REST API (pref) | Problem Solving, Selenium, SQL |
| 3 | React Developer Intern (Bluepeak Digital Pvt Ltd) | Web Development | 0.526 | 0.36 | 63.9 | Fair | Git, REST API | CSS |
| 4 | DevOps Intern (Cascade Solutions Pvt Ltd) | DevOps/Cloud | 0.571 | 0.49 | 63.7 | Fair | Docker, Git, Python | AWS |
| 5 | Backend Developer Intern (Nimbus Analytics Pvt Ltd) | Software Development | 0.608 | 0.59 | 62.1 | Fair | Git, Python, REST API, Django (pref), Docker (pref) | Data Structures, SQL |

**Assessment: weak ranking.** Pure retrieval ranked two Backend Developer internships 2nd and 5th. The final matching put two Software Testing internships first and the Backend Developer internship last. The reasons, all visible in the breakdown:
- Testing #1 is onsite in the candidate's own city (location 1.0) and accepts any bachelor's degree (education 1.0).
- The Backend posting is hybrid in another city (location 0.3).
- The Backend posting's required skills include Data Structures and SQL, which this candidate's resume doesn't list.

The scores are all close (62.1–65.6), so small location and education differences decide the order. See finding F1.

### 03 — Data Science candidate
**Extracted:**
- Skills: Python, Pandas, NumPy, Scikit-learn, Statistics, SQL, Tableau
- Degree: B.Sc Statistics (profile)
- Location: Hyderabad (profile)

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | Data Science Intern (Brightloop Robotics) | Data Science | 0.570 | 0.48 | 79.7 | Strong | Pandas, SQL, Statistics | — |
| 2 | Data Science Intern (Foxglove Systems LLP) | Data Science | 0.638 | 0.68 | 79.6 | Strong | NumPy, Pandas, Python, Scikit-learn, Tableau (pref) | Machine Learning |
| 3 | Data Analyst Intern (Lumenary Dynamics Inc) | Data Science | 0.641 | 0.69 | 77.8 | Strong | Python, Scikit-learn, SQL | — |
| 4 | Machine Learning Intern (Foxglove Systems LLP) | Data Science | 0.591 | 0.54 | 74.9 | Strong | NumPy, Pandas, Python, SQL | — |
| 5 | Machine Learning Intern (Trueform Technologies Pvt Ltd) | Data Science | 0.484 | 0.24 | 74.8 | Strong | NumPy, Python, Statistics | — |

**Assessment:** the strongest result set. Every result is in-domain, four of them cover all required skills, and every label is "Strong".

### 04 — Generative AI candidate
**Extracted:**
- Skills: Python, LLM, Generative AI, NLP, PyTorch, Prompt Engineering *(other)*, LangChain *(other)*
- Degree: M.Tech CSE (profile)
- Location: Chennai (profile)
- 1 project

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | Machine Learning Intern (Trueform Technologies Pvt Ltd) | Data Science | 0.475 | 0.21 | 54.6 | Fair | Python, PyTorch (pref) | NumPy, Statistics |
| 2 | AI Research Intern (Clearwater Solutions Inc) | Data Science | 0.464 | 0.18 | 50.7 | Fair | Python, PyTorch (pref) | Machine Learning, Scikit-learn, Statistics |
| 3 | Machine Learning Intern (Foxglove Systems LLP) | Data Science | 0.473 | 0.21 | 49.7 | Fair | Python, NLP (pref) | NumPy, Pandas, SQL |
| 4 | AI Research Intern (Amberline Technologies LLP) | Data Science | 0.538 | 0.39 | 49.2 | Fair | Python, NLP (pref) | Machine Learning, Scikit-learn, SQL, Statistics |
| 5 | Data Analyst Intern (Lumenary Dynamics Inc) | Data Science | 0.437 | 0.11 | 46.1 | Fair | Python, NLP (pref), PyTorch (pref) | Scikit-learn, SQL |

**Assessment: correct behaviour, and it exposes a dataset gap.**
- **No posting** in the dataset mentions generative AI or LLMs, and "LLM" and "Generative AI" appear in no posting's skill list.
- Pure retrieval was noisy: only 1 of its top 5 was in-domain (the rest were Software Development, QA and Web).
- The skill-aware final matching moved all 5 results into Data Science. It labelled every one "Fair" and named each missing skill.
- The system did not invent any GenAI internship. See finding F3.

### 05 — Multiple programming skills
**Extracted:**
- Skills: Java, Python, C++, JavaScript, Kotlin, Go, SQL, Git
- Degree: B.Tech CSE (profile)
- Location: Noida (profile)

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | Software Engineering Intern (Cascade Ventures LLP) | Software Development | 0.541 | 0.40 | 78.1 | Strong | C++, Git, Java, JavaScript | — |
| 2 | Backend Developer Intern (Silverline Cloud Inc) | Software Development | 0.548 | 0.42 | 72.5 | Strong | Git, Java, JavaScript, Python, SQL | — |
| 3 | Full-Stack Developer Intern (Nimbus Analytics Pvt Ltd) | Software Development | 0.471 | 0.20 | 68.1 | Strong | C++, Git, Python | — |
| 4 | Software Testing Intern (Nimbus Analytics Pvt Ltd) | QA/Testing | 0.487 | 0.25 | 65.0 | Strong | Git, Java, SQL | Selenium |
| 5 | Java Developer Intern (Quantumly Software Pvt Ltd) | Software Development | 0.525 | 0.36 | 63.8 | Fair | C++, Git | Algorithms |

**Assessment:** good. The QA result at #4 falls outside the expected domains, but it is defensible: 3 of its 4 required skills match.

### 06 — Strong educational qualifications
**Extracted:**
- Skills: Python, Data Structures, Algorithms, Machine Learning
- Degree: M.Tech Computer Science (gold medal, CGPA 9.6), read from the resume because the profile field was blank
- Location: Kolkata (profile)

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | AI Research Intern (Amberline Technologies LLP) | Data Science | 0.601 | 0.57 | 57.5 | Fair | Machine Learning, Python | Scikit-learn, SQL, Statistics |
| 2 | Software Engineering Intern (Quantumly Robotics LLP) | Software Development | 0.522 | 0.35 | 52.5 | Fair | Algorithms, Data Structures | JavaScript, REST API |
| 3 | Data Science Intern (Foxglove Systems LLP) | Data Science | 0.581 | 0.52 | 51.8 | Fair | Machine Learning, Python | NumPy, Pandas, Scikit-learn |
| 4 | Machine Learning Intern (Pixelforge Softworks) | Data Science | 0.565 | 0.47 | 50.9 | Fair | Machine Learning, Python | Data Analysis, NumPy, Pandas |
| 5 | Machine Learning Intern (Trueform Technologies Pvt Ltd) | Data Science | 0.554 | 0.44 | 49.1 | Fair | Python | NumPy, Statistics |

**Assessment:** the domain is correct.
- The M.Tech was correctly detected from the resume and matched the "Pursuing M.Tech/M.E." requirement (#1, education 1.0).
- It was rated as "higher level" (0.7) against bachelor's-level postings.
- Academic distinction (gold medal, CGPA) is **not** scored; the algorithm uses only the degree family and level. Scores stay "Fair" because the candidate lists only 4 skills. See finding F4.

### 07 — Relevant experience
**Extracted:**
- Skills: Selenium, Java, JIRA, Agile, SQL
- Degree: BCA (resume)
- Location: Chennai (profile)
- 1 experience entry (QA automation internship)

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | QA Engineering Intern (Highfield Innovations LLP) | QA/Testing | 0.743 | 0.98 | 69.1 | Strong | Java, SQL, JIRA (pref) | Git, Python |
| 2 | Software Testing Intern (Cascade Ventures LLP) | QA/Testing | 0.646 | 0.70 | 68.1 | Strong | Java, Selenium, SQL | Problem Solving |
| 3 | QA Engineering Intern (Northstar AI Inc) | QA/Testing | 0.753 | 1.00 | 66.8 | Strong | Java, Selenium, SQL, JIRA (pref) | Git, Python |
| 4 | Software Testing Intern (Nimbus Analytics Pvt Ltd) | QA/Testing | 0.602 | 0.58 | 65.5 | Strong | Java, Selenium, SQL | Git |
| 5 | Software Testing Intern (Silverline Cloud Inc) | QA/Testing | 0.636 | 0.67 | 61.8 | Fair | Selenium, JIRA (pref) | Problem Solving, Python |

**Assessment:** excellent domain fit, with the highest semantic similarity of any profile (0.75).
- The experience text itself is **not** part of the query; the match comes from the skills.
- In the diagnostic, adding the experience text raised the mean top-5 similarity from 0.722 to 0.763 with the same 5 internships, so the ranking didn't change. See finding F2.

### 08 — Relevant academic projects
**Extracted:**
- Skills: Figma, HTML, CSS
- Degree: B.Sc Computer Science (resume)
- Location: **missing**
- 2 project entries describing wireframes, prototypes, user research and a design system

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | UI/UX Design Intern (Foxglove Systems LLP) | UI/UX Design | 0.583 | 0.52 | 55.5 | Fair | Figma, CSS (pref) | Adobe XD, User Research, Wireframing |
| 2 | React Developer Intern (Wavecrest Solutions LLP) | Web Development | 0.506 | 0.30 | 52.2 | Fair | CSS, HTML | REST API |
| 3 | UI/UX Design Intern (Clearwater Solutions Inc) | UI/UX Design | 0.483 | 0.24 | 45.4 | Fair | Figma, HTML (pref) | User Research, Wireframing |
| 4 | UI Engineering Intern (Ironbridge Networks LLP) | Web Development | 0.492 | 0.26 | 45.3 | Fair | CSS | Git, JavaScript, REST API |
| 5 | Product Design Intern (Meridian Systems) | UI/UX Design | 0.590 | 0.54 | 44.3 | **Weak** | Figma, HTML (pref) | Adobe XD, User Research, Wireframing |

**Assessment: the clearest gap.**
- The projects demonstrate **Wireframing** and **User Research**, but those skills are reported as *missing*: skills are taken only from the skills section, never from project descriptions.
- Product Design (#5) has the highest semantic similarity (0.590) but is labelled "Weak". It loses on location (hybrid in another city while the student's location is unknown, 0.3) and on the "missing" skills.
- Missing location was handled correctly: status `unknown`, completeness 0.85, and the student is told to "Add your city to your profile".
- In the diagnostic, adding project text made all 5 retrieved results UI/UX Design (previously 4 of 5).

See finding F2.

### 09 — Partial skill overlap
**Extracted:**
- Skills: Linux, Excel, Networking, Communication
- Degree: B.Com (profile)
- Location: Jaipur (profile)

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | Product Management Intern (Cascade Ventures LLP) | Product Management | 0.467 | 0.19 | 53.8 | Fair | Communication, Excel | Market Research, Problem Solving |
| 2 | Financial Analyst Intern (Pixelforge Softworks) | Finance | 0.544 | 0.41 | 51.4 | Fair | Communication, Excel | Financial Modeling |
| 3 | Operations Intern (Meridian Analytics Inc) | Business Analysis | 0.534 | 0.38 | 50.8 | Fair | Communication, Excel | SQL |
| 4 | DevOps Intern (Quantumly Systems Pvt Ltd) | DevOps/Cloud | 0.505 | 0.30 | 49.4 | Fair | Linux | AWS, CI/CD |
| 5 | Cybersecurity Intern (Meridian Analytics Inc) | Cybersecurity | 0.468 | 0.19 | 47.2 | Fair | Linux | Python, SQL |

**Assessment:** reasonable.
- No posting is a strong fit, and all five are honestly labelled "Fair", with each missing skill named.
- The Product Management and Finance results fall outside the evaluator's expected domains. They are still defensible for a B.Com graduate with Excel and Communication skills.
- Unrelated-degree handling worked: B.Com against "Pursuing B.Sc (CS/IT/Stats)" and "BCA/MCA" requirements scored education 0.1.

### 10 — Limited or missing information
**Extracted:**
- Skills: Communication only
- No degree, location or summary

| # | Internship (company) | Domain | Cosine | Semantic | Score | Label | Matched | Missing required |
|---|---|---|---|---|---|---|---|---|
| 1 | Financial Analyst Intern (Pixelforge Softworks) | Finance | 0.220 | 0.00 | 32.8 | Weak | Communication | Excel, Financial Modeling |
| 2 | Operations Intern (Meridian Analytics Inc) | Business Analysis | 0.229 | 0.00 | 32.8 | Weak | Communication | Excel, SQL |
| 3 | Business Analyst Intern (Skyfield Ventures) | Business Analysis | 0.215 | 0.00 | 29.5 | Weak | Communication | Data Analysis, Excel, SQL |
| 4 | Business Analyst Intern (Pixelforge Softworks) | Business Analysis | 0.227 | 0.00 | 29.5 | Weak | Communication | Data Analysis, Excel, SQL |
| 5 | Business Analyst Intern (Ironbridge Softworks Inc) | Business Analysis | 0.202 | 0.00 | 29.5 | Weak | Communication | Data Analysis, Excel, SQL |

**Assessment:** correct conservative behaviour.
- All results are labelled "Weak" (≤ 32.8), the semantic score is 0.00, and completeness is 0.85.
- Each result tells the student to "Add your degree … to your profile".
- Missing data did not inflate any score.

## 4. Findings and limitations

| ID | Finding | Evidence | Severity | Suggested remedy (not implemented; needs approval) |
|---|---|---|---|---|
| **F1** | Location and education can outrank a better role fit when scores are close | Profile 02: Backend Developer ranked 5th behind Testing/DevOps postings (62.1 vs 65.6) | Medium | Add a small role-fit signal (e.g. title/domain similarity), or rank within score bands by semantic similarity. This would change the reviewed scoring, so it needs a new algorithm version. |
| **F2** | Skills demonstrated only in experience/project descriptions are not recognised | Profile 08: Wireframing / User Research reported missing; diagnostic query with project text retrieves 5/5 UI/UX | Medium | Extract catalog skills from experience and project text as lower-confidence evidence; optionally add project/experience text to the query (needs re-calibration). |
| **F3** | Dataset coverage gaps: no Generative AI, LLM or computer-vision-specific postings | Profile 04 best 54.6; 0 postings mention GenAI or LLMs | Dataset | Add postings for these domains; the system already handles the absence honestly. |
| **F4** | Academic distinction (grades, awards) is not scored | Profile 06: gold medal / CGPA 9.6 has no effect | Low (by design) | Optional bonus component; deliberately excluded so far to keep scoring skill-centred. |
| **F5** | Dataset inconsistency: 10 postings have work mode Onsite/Hybrid but location "Remote" | 6 × Hybrid/Remote, 4 × Onsite/Remote (e.g. Lumenary Dynamics "Onsite / Remote") | Low | Add a validator warning and clean the synthetic data. Currently these are scored as remote (location 1.0). |
| **F6** | The resume address is not extracted from a contact line such as "… \| Pune, India" | Every profile's address was empty; location came from the profile page | Low | Improve address extraction, or ask for the location at upload time. |
| **F7** | Pure semantic retrieval alone is noisy for unusual profiles | Profile 04 retrieval 1/5 in-domain; profile 09 2/5 | Informational | Already mitigated by the hybrid candidate set and skill-weighted scoring (final 5/5 and 3/5). |

**Correct behaviours confirmed:**
- No invented internships, companies or requirements: 50/50 results grounded.
- Missing data never increased a score (profiles 08 and 10).
- Unrelated degrees score 0.1 (profile 09).
- A degree read from the resume works when the profile is empty (profiles 06–08).

## 5. Automated test results

Full regression on `career_companion_test` at the time of this evaluation: **373 passed, 0 failed, 0 skipped** (`python -m pytest`).

That is the 361 tests from Phases 0–3 plus 12 evaluation-package tests.
