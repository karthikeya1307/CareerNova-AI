# RAG Evaluation — Raw Output

> Generated automatically by `python -m evaluation.rag_evaluation`. Do not edit by hand.
> Generated at 2026-11-15T05:05:26.190774+00:00 on database `career_companion_test` (synthetic data only).

## System checks

| Result | Check | Details |
|---|---|---|
| PASS | dataset: 180 valid records, no duplicate ids, no missing values | 180/180 valid, missing=0, duplicate ids=0 |
| PASS | dataset: no duplicate company+title+location | 0 duplicates |
| PASS | dataset: every skill maps to the canonical catalog | 69 distinct skills, unmapped=none |
| PASS | database records identical to dataset file | 180 rows, 0 mismatches |
| PASS | embedding model: all-MiniLM-L6-v2, 384 dimensions, unit vectors | sentence-transformers/all-MiniLM-L6-v2 @ 1110a243, dim=384 |
| PASS | FAISS manifest consistent with model and PostgreSQL | vectors=180, documents=180, active=180, dim=384, sha256 verified on load |
| PASS | stored vectors match re-embedded source text | min cosine over 12 documents = 1.000000 |
| PASS | retrieval: results active and sorted by similarity | 0 profiles with problems |
| PASS | matching: every result grounded in source records | 0 ungrounded results |

## Index

- Model: `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` — 384 dimensions
- FAISS index: `IndexIDMap2` with 180 vectors
- Semantic calibration: floor 0.4, ceiling 0.75
- Weights: {'skills': 0.5, 'semantic': 0.2, 'education': 0.15, 'location': 0.15} — algorithm `v1`

## 01_ai_ml — AI/ML candidate

### Extracted candidate information

- Normalized skills: Python, TensorFlow, PyTorch, Deep Learning, Machine Learning, NumPy, Computer Vision
- Education (resume): B.Tech Computer Science and Engineering, Example Institute of Technology, 2026
- Experience entries: 0 | Project entries: 1
- Degree used: B.Tech Computer Science (source: profile)
- Location used: Bengaluru (source: profile)
- Expected domains (evaluator): Data Science

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | Machine Learning Intern | Pixelforge Softworks | Data Science | 0.5735 |
| 2 | Data Science Intern | Brightloop Robotics | Data Science | 0.5510 |
| 3 | AI Research Intern | Amberline Technologies LLP | Data Science | 0.5250 |
| 4 | Machine Learning Intern | Quantumly Systems Pvt Ltd | Data Science | 0.5215 |
| 5 | Data Science Intern | Pixelforge Ventures LLP | Data Science | 0.5191 |

### Top 5 — final matching (candidates considered: 94)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Machine Learning Intern — Trueform Technologies Pvt Ltd | Data Science | Remote / Hyderabad, India | 0.5059 | 0.30 | 72.7 | Strong | NumPy, Python, PyTorch (pref) | Statistics | — |
| 2 | Machine Learning Intern — Pixelforge Softworks | Data Science | Hybrid / Kolkata, India | 0.5735 | 0.50 | 60.1 | Fair | Machine Learning, NumPy, Python, Deep Learning (pref), TensorFlow (pref) | Data Analysis, Pandas | — |
| 3 | Data Science Intern — Foxglove Systems LLP | Data Science | Remote / Kochi, India | 0.4705 | 0.20 | 58.0 | Fair | Machine Learning, NumPy, Python | Pandas, Scikit-learn | — |
| 4 | Data Analyst Intern — Northstar AI Inc | Data Science | Remote / Jaipur, India | 0.4521 | 0.15 | 56.3 | Fair | Machine Learning, TensorFlow (pref) | Data Analysis, SQL | — |
| 5 | Machine Learning Intern — Foxglove Systems LLP | Data Science | Remote / Hyderabad, India | 0.4892 | 0.25 | 55.1 | Fair | NumPy, Python | Pandas, SQL | — |

#### Why each internship was recommended

**1. Machine Learning Intern — Trueform Technologies Pvt Ltd** (score 72.7, completeness 1.0)
- You have 2 of 3 required skills (NumPy, Python). Missing: Statistics. You have 1 of 1 preferred skills (PyTorch).
- Your resume is moderately related to this role (similarity 0.51).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in engineering (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

**2. Machine Learning Intern — Pixelforge Softworks** (score 60.1, completeness 1.0)
- You have 3 of 5 required skills (Machine Learning, NumPy, Python). Missing: Data Analysis, Pandas. You have 2 of 3 preferred skills (Deep Learning, TensorFlow).
- Your resume is moderately related to this role (similarity 0.57).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in engineering (from your profile) matches the requirement.
- Hybrid in Kolkata, India; you are in a different city (hybrid needs some office days).

**3. Data Science Intern — Foxglove Systems LLP** (score 58.0, completeness 1.0)
- You have 3 of 5 required skills (Machine Learning, NumPy, Python). Missing: Pandas, Scikit-learn. You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.47).
- Requirement: Pursuing B.Tech/B.E. (CS/IT preferred). Your bachelor's in engineering (from your profile) matches the requirement.
- Remote internship, so your location is not a constraint.

**4. Data Analyst Intern — Northstar AI Inc** (score 56.3, completeness 1.0)
- You have 1 of 3 required skills (Machine Learning). Missing: Data Analysis, SQL. You have 1 of 1 preferred skills (TensorFlow).
- Your resume is weakly related to this role (similarity 0.45).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in engineering (from your profile) matches the requirement.
- Remote internship, so your location is not a constraint.

**5. Machine Learning Intern — Foxglove Systems LLP** (score 55.1, completeness 1.0)
- You have 2 of 4 required skills (NumPy, Python). Missing: Pandas, SQL. You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.49).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in engineering (from your profile) matches the requirement.
- Remote internship, so your location is not a constraint.

#### Diagnostic: adding experience/project text to the query

- Current top-5 domains: Data Science, Data Science, Data Science, Data Science, Data Science (mean cosine 0.538)
- With experience/projects: Data Science, Data Science, Data Science, Data Science, Data Science (mean cosine 0.5194)
- Shared internships in top 5: 3/5

## 02_backend — Backend developer

### Extracted candidate information

- Normalized skills: Python, FastAPI, Django, PostgreSQL, REST API, Docker, Git
- Education (resume): B.Tech Information Technology, Example Institute of Technology, 2026
- Experience entries: 0 | Project entries: 0
- Degree used: B.Tech IT (source: profile)
- Location used: Pune (source: profile)
- Expected domains (evaluator): Software Development, Web Development

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | Full-Stack Developer Intern | Foxglove Systems LLP | Software Development | 0.6201 |
| 2 | Backend Developer Intern | Nimbus Analytics Pvt Ltd | Software Development | 0.6081 |
| 3 | Frontend Developer Intern | Foxglove Systems LLP | Web Development | 0.5963 |
| 4 | Frontend Developer Intern | Silverline Labs | Web Development | 0.5954 |
| 5 | Backend Developer Intern | Silverline Cloud Inc | Software Development | 0.5908 |

### Top 5 — final matching (candidates considered: 133)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Software Testing Intern — Clearwater Solutions | QA/Testing | Onsite / Pune, India | 0.4984 | 0.28 | 65.6 | Strong | Git, Python, Docker (pref) | Problem Solving, SQL | outside expected domains |
| 2 | Software Testing Intern — Quantumly Robotics LLP | QA/Testing | Remote / Gurugram, India | 0.5471 | 0.42 | 64.4 | Fair | Git, Python, Docker (pref), REST API (pref) | Problem Solving, Selenium, SQL | outside expected domains |
| 3 | React Developer Intern — Bluepeak Digital Pvt Ltd | Web Development | Hybrid / Remote | 0.5258 | 0.36 | 63.9 | Fair | Git, REST API | CSS | — |
| 4 | DevOps Intern — Cascade Solutions Pvt Ltd | DevOps/Cloud | Onsite / Pune, India | 0.5705 | 0.49 | 63.7 | Fair | Docker, Git, Python | AWS | outside expected domains |
| 5 | Backend Developer Intern — Nimbus Analytics Pvt Ltd | Software Development | Hybrid / Chennai, India | 0.6081 | 0.59 | 62.1 | Fair | Git, Python, REST API, Django (pref), Docker (pref) | Data Structures, SQL | — |

#### Why each internship was recommended

**1. Software Testing Intern — Clearwater Solutions** (score 65.6, completeness 1.0)
- You have 2 of 4 required skills (Git, Python). Missing: Problem Solving, SQL. You have 1 of 1 preferred skills (Docker).
- Your resume is weakly related to this role (similarity 0.50).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in engineering (from your profile) meets the requirement.
- Onsite in Pune, India, which matches your location.

**2. Software Testing Intern — Quantumly Robotics LLP** (score 64.4, completeness 1.0)
- You have 2 of 5 required skills (Git, Python). Missing: Problem Solving, Selenium, SQL. You have 2 of 2 preferred skills (Docker, REST API).
- Your resume is moderately related to this role (similarity 0.55).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in engineering (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

**3. React Developer Intern — Bluepeak Digital Pvt Ltd** (score 63.9, completeness 1.0)
- You have 2 of 3 required skills (Git, REST API). Missing: CSS. You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.53).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in engineering (from your profile) matches the requirement.
- Remote internship, so your location is not a constraint.

**4. DevOps Intern — Cascade Solutions Pvt Ltd** (score 63.7, completeness 1.0)
- You have 3 of 4 required skills (Docker, Git, Python). Missing: AWS. You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.57).
- Requirement: Pursuing B.Sc (CS/IT/Stats). Your bachelor's in engineering (from your profile) is a closely related computing degree.
- Onsite in Pune, India, which matches your location.

**5. Backend Developer Intern — Nimbus Analytics Pvt Ltd** (score 62.1, completeness 1.0)
- You have 3 of 5 required skills (Git, Python, REST API). Missing: Data Structures, SQL. You have 2 of 3 preferred skills (Django, Docker).
- Your resume is moderately related to this role (similarity 0.61).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in engineering (from your profile) matches the requirement.
- Hybrid in Chennai, India; you are in a different city (hybrid needs some office days).

## 03_data_science — Data Science candidate

### Extracted candidate information

- Normalized skills: Python, Pandas, NumPy, Scikit-learn, Statistics, SQL, Tableau
- Education (resume): B.Sc Statistics, Example College of Science, 2026
- Experience entries: 0 | Project entries: 0
- Degree used: B.Sc Statistics (source: profile)
- Location used: Hyderabad (source: profile)
- Expected domains (evaluator): Data Science, Business Analysis

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | Data Science Intern | Meridian Systems | Data Science | 0.6431 |
| 2 | Data Analyst Intern | Lumenary Dynamics Inc | Data Science | 0.6411 |
| 3 | Data Science Intern | Foxglove Systems LLP | Data Science | 0.6378 |
| 4 | Data Analyst Intern | Cascade Solutions | Data Science | 0.5986 |
| 5 | Data Science Intern | Wavecrest Solutions Pvt Ltd | Data Science | 0.5978 |

### Top 5 — final matching (candidates considered: 108)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Data Science Intern — Brightloop Robotics | Data Science | Remote / Mumbai, India | 0.5697 | 0.48 | 79.7 | Strong | Pandas, SQL, Statistics | — | — |
| 2 | Data Science Intern — Foxglove Systems LLP | Data Science | Remote / Kochi, India | 0.6378 | 0.68 | 79.6 | Strong | NumPy, Pandas, Python, Scikit-learn, Tableau (pref) | Machine Learning | — |
| 3 | Data Analyst Intern — Lumenary Dynamics Inc | Data Science | Onsite / Remote | 0.6411 | 0.69 | 77.8 | Strong | Python, Scikit-learn, SQL | — | — |
| 4 | Machine Learning Intern — Foxglove Systems LLP | Data Science | Remote / Hyderabad, India | 0.5907 | 0.54 | 74.9 | Strong | NumPy, Pandas, Python, SQL | — | — |
| 5 | Machine Learning Intern — Trueform Technologies Pvt Ltd | Data Science | Remote / Hyderabad, India | 0.4842 | 0.24 | 74.8 | Strong | NumPy, Python, Statistics | — | — |

#### Why each internship was recommended

**1. Data Science Intern — Brightloop Robotics** (score 79.7, completeness 1.0)
- You have 3 of 3 required skills (Pandas, SQL, Statistics). You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.57).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in science (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

**2. Data Science Intern — Foxglove Systems LLP** (score 79.6, completeness 1.0)
- You have 4 of 5 required skills (NumPy, Pandas, Python, Scikit-learn). Missing: Machine Learning. You have 1 of 1 preferred skills (Tableau).
- Your resume is closely related to this role (similarity 0.64).
- Requirement: Pursuing B.Tech/B.E. (CS/IT preferred). Your bachelor's in science (from your profile) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

**3. Data Analyst Intern — Lumenary Dynamics Inc** (score 77.8, completeness 1.0)
- You have 3 of 3 required skills (Python, Scikit-learn, SQL). You have 0 of 3 preferred skills.
- Your resume is closely related to this role (similarity 0.64).
- Requirement: Pursuing BCA/MCA. Your bachelor's in science (from your profile) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

**4. Machine Learning Intern — Foxglove Systems LLP** (score 74.9, completeness 1.0)
- You have 4 of 4 required skills (NumPy, Pandas, Python, SQL). You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.59).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in science (from your profile) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

**5. Machine Learning Intern — Trueform Technologies Pvt Ltd** (score 74.8, completeness 1.0)
- You have 3 of 3 required skills (NumPy, Python, Statistics). You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.48).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in science (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

## 04_generative_ai — Generative AI candidate

### Extracted candidate information

- Normalized skills: Python, LLM, Generative AI, NLP, PyTorch, Prompt Engineering (other), LangChain (other)
- Education (resume): M.Tech Computer Science, Example Institute of Technology, 2026
- Experience entries: 0 | Project entries: 1
- Degree used: M.Tech CSE (source: profile)
- Location used: Chennai (source: profile)
- Expected domains (evaluator): Data Science

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | AI Research Intern | Amberline Technologies LLP | Data Science | 0.5377 |
| 2 | Software Engineering Intern | Quantumly Robotics LLP | Software Development | 0.5352 |
| 3 | Software Testing Intern | Quantumly Robotics LLP | QA/Testing | 0.5213 |
| 4 | Frontend Developer Intern | Foxglove Systems LLP | Web Development | 0.5169 |
| 5 | Test Automation Intern | Northstar AI Inc | QA/Testing | 0.5160 |

### Top 5 — final matching (candidates considered: 99)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Machine Learning Intern — Trueform Technologies Pvt Ltd | Data Science | Remote / Hyderabad, India | 0.4751 | 0.21 | 54.6 | Fair | Python, PyTorch (pref) | NumPy, Statistics | — |
| 2 | AI Research Intern — Clearwater Solutions Inc | Data Science | Hybrid / Chennai, India | 0.4640 | 0.18 | 50.7 | Fair | Python, PyTorch (pref) | Machine Learning, Scikit-learn, Statistics | — |
| 3 | Machine Learning Intern — Foxglove Systems LLP | Data Science | Remote / Hyderabad, India | 0.4735 | 0.21 | 49.7 | Fair | Python, NLP (pref) | NumPy, Pandas, SQL | — |
| 4 | AI Research Intern — Amberline Technologies LLP | Data Science | Remote / Gurugram, India | 0.5377 | 0.39 | 49.2 | Fair | Python, NLP (pref) | Machine Learning, Scikit-learn, SQL, Statistics | — |
| 5 | Data Analyst Intern — Lumenary Dynamics Inc | Data Science | Onsite / Remote | 0.4370 | 0.11 | 46.1 | Fair | Python, NLP (pref), PyTorch (pref) | Scikit-learn, SQL | — |

#### Why each internship was recommended

**1. Machine Learning Intern — Trueform Technologies Pvt Ltd** (score 54.6, completeness 1.0)
- You have 1 of 3 required skills (Python). Missing: NumPy, Statistics. You have 1 of 1 preferred skills (PyTorch).
- Your resume is weakly related to this role (similarity 0.48).
- Requirement: Any Bachelor's degree (final year). Your master's in engineering (from your profile) exceeds the bachelor's-level requirement.
- Remote internship, so your location is not a constraint.

**2. AI Research Intern — Clearwater Solutions Inc** (score 50.7, completeness 1.0)
- You have 1 of 4 required skills (Python). Missing: Machine Learning, Scikit-learn, Statistics. You have 1 of 1 preferred skills (PyTorch).
- Your resume is weakly related to this role (similarity 0.46).
- Requirement: Any Bachelor's degree (final year). Your master's in engineering (from your profile) exceeds the bachelor's-level requirement.
- Hybrid in Chennai, India, which matches your location.

**3. Machine Learning Intern — Foxglove Systems LLP** (score 49.7, completeness 1.0)
- You have 1 of 4 required skills (Python). Missing: NumPy, Pandas, SQL. You have 1 of 1 preferred skills (NLP).
- Your resume is weakly related to this role (similarity 0.47).
- Requirement: Pursuing B.Tech/B.E.. Your master's in engineering (from your profile) is a higher level than this internship targets.
- Remote internship, so your location is not a constraint.

**4. AI Research Intern — Amberline Technologies LLP** (score 49.2, completeness 1.0)
- You have 1 of 5 required skills (Python). Missing: Machine Learning, Scikit-learn, SQL, Statistics. You have 1 of 3 preferred skills (NLP).
- Your resume is moderately related to this role (similarity 0.54).
- Requirement: Pursuing M.Tech/M.E.. Your master's in engineering (from your profile) matches the requirement.
- Remote internship, so your location is not a constraint.

**5. Data Analyst Intern — Lumenary Dynamics Inc** (score 46.1, completeness 1.0)
- You have 1 of 3 required skills (Python). Missing: Scikit-learn, SQL. You have 2 of 3 preferred skills (NLP, PyTorch).
- Your resume is weakly related to this role (similarity 0.44).
- Requirement: Pursuing BCA/MCA. Your master's in engineering (from your profile) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

#### Diagnostic: adding experience/project text to the query

- Current top-5 domains: Data Science, Software Development, QA/Testing, Web Development, QA/Testing (mean cosine 0.5254)
- With experience/projects: Software Development, QA/Testing, Web Development, QA/Testing, QA/Testing (mean cosine 0.5467)
- Shared internships in top 5: 4/5

## 05_multi_language — Candidate with multiple programming skills

### Extracted candidate information

- Normalized skills: Java, Python, C++, JavaScript, Kotlin, Go, SQL, Git
- Education (resume): B.Tech Computer Science, Example Institute of Technology, 2026
- Experience entries: 0 | Project entries: 0
- Degree used: B.Tech CSE (source: profile)
- Location used: Noida (source: profile)
- Expected domains (evaluator): Software Development, Web Development, Mobile Development

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | UI Engineering Intern | Meridian Systems | Web Development | 0.5639 |
| 2 | Web Developer Intern | Wavecrest Solutions Pvt Ltd | Web Development | 0.5594 |
| 3 | Web Developer Intern | Fernwood Digital | Web Development | 0.5515 |
| 4 | React Developer Intern | Bluepeak Digital Pvt Ltd | Web Development | 0.5504 |
| 5 | Backend Developer Intern | Silverline Cloud Inc | Software Development | 0.5484 |

### Top 5 — final matching (candidates considered: 152)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Software Engineering Intern — Cascade Ventures LLP | Software Development | Remote / Remote | 0.5412 | 0.40 | 78.1 | Strong | C++, Git, Java, JavaScript | — | — |
| 2 | Backend Developer Intern — Silverline Cloud Inc | Software Development | Remote / Chennai, India | 0.5484 | 0.42 | 72.5 | Strong | Git, Java, JavaScript, Python, SQL | — | — |
| 3 | Full-Stack Developer Intern — Nimbus Analytics Pvt Ltd | Software Development | Hybrid / Noida, India | 0.4712 | 0.20 | 68.1 | Strong | C++, Git, Python | — | — |
| 4 | Software Testing Intern — Nimbus Analytics Pvt Ltd | QA/Testing | Remote / Gurugram, India | 0.4871 | 0.25 | 65.0 | Strong | Git, Java, SQL | Selenium | outside expected domains |
| 5 | Java Developer Intern — Quantumly Software Pvt Ltd | Software Development | Remote / Mumbai, India | 0.5248 | 0.36 | 63.8 | Fair | C++, Git | Algorithms | — |

#### Why each internship was recommended

**1. Software Engineering Intern — Cascade Ventures LLP** (score 78.1, completeness 1.0)
- You have 4 of 4 required skills (C++, Git, Java, JavaScript). You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.54).
- Requirement: Pursuing B.Tech/B.E. (CS/IT preferred). Your bachelor's in engineering (from your profile) matches the requirement.
- Remote internship, so your location is not a constraint.

**2. Backend Developer Intern — Silverline Cloud Inc** (score 72.5, completeness 1.0)
- You have 5 of 5 required skills (Git, Java, JavaScript, Python, SQL). You have 0 of 2 preferred skills.
- Your resume is moderately related to this role (similarity 0.55).
- Requirement: Pursuing BCA/MCA. Your bachelor's in engineering (from your profile) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

**3. Full-Stack Developer Intern — Nimbus Analytics Pvt Ltd** (score 68.1, completeness 1.0)
- You have 3 of 3 required skills (C++, Git, Python). You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.47).
- Requirement: Pursuing BCA/MCA. Your bachelor's in engineering (from your profile) is a closely related computing degree.
- Hybrid in Noida, India, which matches your location.

**4. Software Testing Intern — Nimbus Analytics Pvt Ltd** (score 65.0, completeness 1.0)
- You have 3 of 4 required skills (Git, Java, SQL). Missing: Selenium. You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.49).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in engineering (from your profile) matches the requirement.
- Remote internship, so your location is not a constraint.

**5. Java Developer Intern — Quantumly Software Pvt Ltd** (score 63.8, completeness 1.0)
- You have 2 of 3 required skills (C++, Git). Missing: Algorithms. You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.52).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in engineering (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

## 06_strong_education — Candidate with strong educational qualifications

### Extracted candidate information

- Normalized skills: Python, Data Structures, Algorithms, Machine Learning
- Education (resume): M.Tech Computer Science (Gold Medal, CGPA 9.6), Example Institute of Technology, 2026
- Experience entries: 0 | Project entries: 0
- Degree used: M.Tech Computer Science (Gold Medal, CGPA 9.6), Example Institute of Technology, 2026 (source: resume)
- Location used: Kolkata (source: profile)
- Expected domains (evaluator): Data Science, Software Development

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | Data Science Intern | Brightloop Robotics | Data Science | 0.6092 |
| 2 | AI Research Intern | Amberline Technologies LLP | Data Science | 0.6008 |
| 3 | Machine Learning Intern | Quantumly Software Pvt Ltd | Data Science | 0.5946 |
| 4 | Machine Learning Intern | Foxglove Systems LLP | Data Science | 0.5917 |
| 5 | Data Analyst Intern | Foxglove Systems LLP | Data Science | 0.5862 |

### Top 5 — final matching (candidates considered: 97)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AI Research Intern — Amberline Technologies LLP | Data Science | Remote / Gurugram, India | 0.6008 | 0.57 | 57.5 | Fair | Machine Learning, Python | Scikit-learn, SQL, Statistics | — |
| 2 | Software Engineering Intern — Quantumly Robotics LLP | Software Development | Onsite / Kolkata, India | 0.5222 | 0.35 | 52.5 | Fair | Algorithms, Data Structures | JavaScript, REST API | — |
| 3 | Data Science Intern — Foxglove Systems LLP | Data Science | Remote / Kochi, India | 0.5807 | 0.52 | 51.8 | Fair | Machine Learning, Python | NumPy, Pandas, Scikit-learn | — |
| 4 | Machine Learning Intern — Pixelforge Softworks | Data Science | Hybrid / Kolkata, India | 0.5645 | 0.47 | 50.9 | Fair | Machine Learning, Python | Data Analysis, NumPy, Pandas | — |
| 5 | Machine Learning Intern — Trueform Technologies Pvt Ltd | Data Science | Remote / Hyderabad, India | 0.5541 | 0.44 | 49.1 | Fair | Python | NumPy, Statistics | — |

#### Why each internship was recommended

**1. AI Research Intern — Amberline Technologies LLP** (score 57.5, completeness 1.0)
- You have 2 of 5 required skills (Machine Learning, Python). Missing: Scikit-learn, SQL, Statistics. You have 0 of 3 preferred skills.
- Your resume is moderately related to this role (similarity 0.60).
- Requirement: Pursuing M.Tech/M.E.. Your master's in engineering (from your resume) matches the requirement.
- Remote internship, so your location is not a constraint.

**2. Software Engineering Intern — Quantumly Robotics LLP** (score 52.5, completeness 1.0)
- You have 2 of 4 required skills (Algorithms, Data Structures). Missing: JavaScript, REST API. You have 0 of 3 preferred skills.
- Your resume is moderately related to this role (similarity 0.52).
- Requirement: Pursuing B.Tech/B.E.. Your master's in engineering (from your resume) is a higher level than this internship targets.
- Onsite in Kolkata, India, which matches your location.

**3. Data Science Intern — Foxglove Systems LLP** (score 51.8, completeness 1.0)
- You have 2 of 5 required skills (Machine Learning, Python). Missing: NumPy, Pandas, Scikit-learn. You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.58).
- Requirement: Pursuing B.Tech/B.E. (CS/IT preferred). Your master's in engineering (from your resume) is a higher level than this internship targets.
- Remote internship, so your location is not a constraint.

**4. Machine Learning Intern — Pixelforge Softworks** (score 50.9, completeness 1.0)
- You have 2 of 5 required skills (Machine Learning, Python). Missing: Data Analysis, NumPy, Pandas. You have 0 of 3 preferred skills.
- Your resume is moderately related to this role (similarity 0.56).
- Requirement: Pursuing B.Tech/B.E.. Your master's in engineering (from your resume) is a higher level than this internship targets.
- Hybrid in Kolkata, India, which matches your location.

**5. Machine Learning Intern — Trueform Technologies Pvt Ltd** (score 49.1, completeness 1.0)
- You have 1 of 3 required skills (Python). Missing: NumPy, Statistics. You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.55).
- Requirement: Any Bachelor's degree (final year). Your master's in engineering (from your resume) exceeds the bachelor's-level requirement.
- Remote internship, so your location is not a constraint.

## 07_relevant_experience — Candidate with relevant experience

### Extracted candidate information

- Normalized skills: Selenium, Java, JIRA, Agile, SQL
- Education (resume): BCA, Example College of Computer Applications, 2025
- Experience entries: 1 | Project entries: 0
- Degree used: BCA, Example College of Computer Applications, 2025 (source: resume)
- Location used: Chennai (source: profile)
- Expected domains (evaluator): QA/Testing

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | QA Engineering Intern | Northstar AI Inc | QA/Testing | 0.7529 |
| 2 | QA Engineering Intern | Nimbus Analytics Pvt Ltd | QA/Testing | 0.7480 |
| 3 | QA Engineering Intern | Highfield Innovations LLP | QA/Testing | 0.7434 |
| 4 | Test Automation Intern | Wavecrest Solutions Pvt Ltd | QA/Testing | 0.6991 |
| 5 | Test Automation Intern | Northstar AI Inc | QA/Testing | 0.6684 |

### Top 5 — final matching (candidates considered: 113)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | QA Engineering Intern — Highfield Innovations LLP | QA/Testing | Hybrid / Hyderabad, India | 0.7434 | 0.98 | 69.1 | Strong | Java, SQL, JIRA (pref) | Git, Python | — |
| 2 | Software Testing Intern — Cascade Ventures LLP | QA/Testing | Remote / Gurugram, India | 0.6463 | 0.70 | 68.1 | Strong | Java, Selenium, SQL | Problem Solving | — |
| 3 | QA Engineering Intern — Northstar AI Inc | QA/Testing | Hybrid / Kochi, India | 0.7529 | 1.00 | 66.8 | Strong | Java, Selenium, SQL, JIRA (pref) | Git, Python | — |
| 4 | Software Testing Intern — Nimbus Analytics Pvt Ltd | QA/Testing | Remote / Gurugram, India | 0.6016 | 0.58 | 65.5 | Strong | Java, Selenium, SQL | Git | — |
| 5 | Software Testing Intern — Silverline Cloud Inc | QA/Testing | Remote / Jaipur, India | 0.6356 | 0.67 | 61.8 | Fair | Selenium, JIRA (pref) | Problem Solving, Python | — |

#### Why each internship was recommended

**1. QA Engineering Intern — Highfield Innovations LLP** (score 69.1, completeness 1.0)
- You have 2 of 4 required skills (Java, SQL). Missing: Git, Python. You have 1 of 1 preferred skills (JIRA).
- Your resume is closely related to this role (similarity 0.74).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in computer applications (from your resume) meets the requirement.
- Hybrid in Hyderabad, India; you are in a different city (hybrid needs some office days).

**2. Software Testing Intern — Cascade Ventures LLP** (score 68.1, completeness 1.0)
- You have 3 of 4 required skills (Java, Selenium, SQL). Missing: Problem Solving. You have 0 of 2 preferred skills.
- Your resume is closely related to this role (similarity 0.65).
- Requirement: Pursuing B.Tech/B.E. (CS/IT preferred). Your bachelor's in computer applications (from your resume) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

**3. QA Engineering Intern — Northstar AI Inc** (score 66.8, completeness 1.0)
- You have 3 of 5 required skills (Java, Selenium, SQL). Missing: Git, Python. You have 1 of 3 preferred skills (JIRA).
- Your resume is closely related to this role (similarity 0.75).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in computer applications (from your resume) meets the requirement.
- Hybrid in Kochi, India; you are in a different city (hybrid needs some office days).

**4. Software Testing Intern — Nimbus Analytics Pvt Ltd** (score 65.5, completeness 1.0)
- You have 3 of 4 required skills (Java, Selenium, SQL). Missing: Git. You have 0 of 1 preferred skills.
- Your resume is moderately related to this role (similarity 0.60).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in computer applications (from your resume) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

**5. Software Testing Intern — Silverline Cloud Inc** (score 61.8, completeness 1.0)
- You have 1 of 3 required skills (Selenium). Missing: Problem Solving, Python. You have 1 of 2 preferred skills (JIRA).
- Your resume is closely related to this role (similarity 0.64).
- Requirement: Pursuing BCA/MCA. Your bachelor's in computer applications (from your resume) matches the requirement.
- Remote internship, so your location is not a constraint.

#### Diagnostic: adding experience/project text to the query

- Current top-5 domains: QA/Testing, QA/Testing, QA/Testing, QA/Testing, QA/Testing (mean cosine 0.7224)
- With experience/projects: QA/Testing, QA/Testing, QA/Testing, QA/Testing, QA/Testing (mean cosine 0.7626)
- Shared internships in top 5: 5/5

## 08_academic_projects — Candidate with relevant academic projects

### Extracted candidate information

- Normalized skills: Figma, HTML, CSS
- Education (resume): B.Sc Computer Science, Example College of Science, 2026
- Experience entries: 0 | Project entries: 2
- Degree used: B.Sc Computer Science, Example College of Science, 2026 (source: resume)
- Location used: — (source: missing)
- Expected domains (evaluator): UI/UX Design, Web Development

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | Product Design Intern | Meridian Systems | UI/UX Design | 0.5895 |
| 2 | Product Design Intern | Trueform Studio | UI/UX Design | 0.5851 |
| 3 | UI/UX Design Intern | Foxglove Systems LLP | UI/UX Design | 0.5829 |
| 4 | Product Design Intern | Cobalt Cloud | UI/UX Design | 0.5673 |
| 5 | Web Developer Intern | Pixelforge Softworks Pvt Ltd | Web Development | 0.5556 |

### Top 5 — final matching (candidates considered: 50)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | UI/UX Design Intern — Foxglove Systems LLP | UI/UX Design | Remote / Hyderabad, India | 0.5829 | 0.52 | 55.5 | Fair | Figma, CSS (pref) | Adobe XD, User Research, Wireframing | — |
| 2 | React Developer Intern — Wavecrest Solutions LLP | Web Development | Hybrid / Chennai, India | 0.5062 | 0.30 | 52.2 | Fair | CSS, HTML | REST API | — |
| 3 | UI/UX Design Intern — Clearwater Solutions Inc | UI/UX Design | Remote / Gurugram, India | 0.4834 | 0.24 | 45.4 | Fair | Figma, HTML (pref) | User Research, Wireframing | — |
| 4 | UI Engineering Intern — Ironbridge Networks LLP | Web Development | Remote / Hyderabad, India | 0.4922 | 0.26 | 45.3 | Fair | CSS | Git, JavaScript, REST API | — |
| 5 | Product Design Intern — Meridian Systems | UI/UX Design | Hybrid / Jaipur, India | 0.5895 | 0.54 | 44.3 | Weak | Figma, HTML (pref) | Adobe XD, User Research, Wireframing | weak score (<45) |

#### Why each internship was recommended

**1. UI/UX Design Intern — Foxglove Systems LLP** (score 55.5, completeness 1.0)
- You have 1 of 4 required skills (Figma). Missing: Adobe XD, User Research, Wireframing. You have 1 of 2 preferred skills (CSS).
- Your resume is moderately related to this role (similarity 0.58).
- Requirement: Pursuing B.Sc (CS/IT/Stats). Your bachelor's in science (from your resume) matches the requirement.
- Remote internship, so your location is not a constraint.

**2. React Developer Intern — Wavecrest Solutions LLP** (score 52.2, completeness 0.85)
- You have 2 of 3 required skills (CSS, HTML). Missing: REST API. You have 0 of 2 preferred skills.
- Your resume is moderately related to this role (similarity 0.51).
- Requirement: Pursuing B.Sc (CS/IT/Stats). Your bachelor's in science (from your resume) matches the requirement.
- Hybrid in Chennai, India. Your location is unknown.
- _Missing information:_ Add your city to your profile to assess location fit.

**3. UI/UX Design Intern — Clearwater Solutions Inc** (score 45.4, completeness 1.0)
- You have 1 of 3 required skills (Figma). Missing: User Research, Wireframing. You have 1 of 3 preferred skills (HTML).
- Your resume is weakly related to this role (similarity 0.48).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in science (from your resume) is a closely related computing degree.
- Remote internship, so your location is not a constraint.

**4. UI Engineering Intern — Ironbridge Networks LLP** (score 45.3, completeness 1.0)
- You have 1 of 4 required skills (CSS). Missing: Git, JavaScript, REST API. You have 0 of 3 preferred skills.
- Your resume is weakly related to this role (similarity 0.49).
- Requirement: Pursuing B.Sc (CS/IT/Stats). Your bachelor's in science (from your resume) matches the requirement.
- Remote internship, so your location is not a constraint.

**5. Product Design Intern — Meridian Systems** (score 44.3, completeness 0.85)
- You have 1 of 4 required skills (Figma). Missing: Adobe XD, User Research, Wireframing. You have 1 of 1 preferred skills (HTML).
- Your resume is moderately related to this role (similarity 0.59).
- Requirement: Pursuing B.Tech/B.E.. Your bachelor's in science (from your resume) is a closely related computing degree.
- Hybrid in Jaipur, India. Your location is unknown.
- _Missing information:_ Add your city to your profile to assess location fit.

#### Diagnostic: adding experience/project text to the query

- Current top-5 domains: UI/UX Design, UI/UX Design, UI/UX Design, UI/UX Design, Web Development (mean cosine 0.5761)
- With experience/projects: UI/UX Design, UI/UX Design, UI/UX Design, UI/UX Design, UI/UX Design (mean cosine 0.5692)
- Shared internships in top 5: 3/5

## 09_partial_overlap — Candidate with partial skill overlap

### Extracted candidate information

- Normalized skills: Linux, Excel, Networking, Communication
- Education (resume): B.Com, Example Commerce College, 2025
- Experience entries: 0 | Project entries: 0
- Degree used: B.Com (source: profile)
- Location used: Jaipur (source: profile)
- Expected domains (evaluator): Cybersecurity, DevOps/Cloud, Business Analysis

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | Data Analyst Intern | Foxglove Systems LLP | Data Science | 0.6274 |
| 2 | Data Science Intern | Foxglove Systems LLP | Data Science | 0.6163 |
| 3 | Business Analyst Intern | Fernwood Analytics Pvt Ltd | Business Analysis | 0.6092 |
| 4 | Web Developer Intern | Wavecrest Solutions Pvt Ltd | Web Development | 0.6027 |
| 5 | Platform Engineering Intern | Bluepeak Digital Pvt Ltd | DevOps/Cloud | 0.6024 |

### Top 5 — final matching (candidates considered: 91)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Product Management Intern — Cascade Ventures LLP | Product Management | Remote / Kolkata, India | 0.4670 | 0.19 | 53.8 | Fair | Communication, Excel | Market Research, Problem Solving | outside expected domains |
| 2 | Financial Analyst Intern — Pixelforge Softworks | Finance | Remote / Noida, India | 0.5439 | 0.41 | 51.4 | Fair | Communication, Excel | Financial Modeling | outside expected domains |
| 3 | Operations Intern — Meridian Analytics Inc | Business Analysis | Remote / Bengaluru, India | 0.5336 | 0.38 | 50.8 | Fair | Communication, Excel | SQL | — |
| 4 | DevOps Intern — Quantumly Systems Pvt Ltd | DevOps/Cloud | Remote / Hyderabad, India | 0.5054 | 0.30 | 49.4 | Fair | Linux | AWS, CI/CD | — |
| 5 | Cybersecurity Intern — Meridian Analytics Inc | Cybersecurity | Remote / Gurugram, India | 0.4680 | 0.19 | 47.2 | Fair | Linux | Python, SQL | — |

#### Why each internship was recommended

**1. Product Management Intern — Cascade Ventures LLP** (score 53.8, completeness 1.0)
- You have 2 of 4 required skills (Communication, Excel). Missing: Market Research, Problem Solving. You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.47).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in commerce (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

**2. Financial Analyst Intern — Pixelforge Softworks** (score 51.4, completeness 1.0)
- You have 2 of 3 required skills (Communication, Excel). Missing: Financial Modeling. You have 0 of 3 preferred skills.
- Your resume is moderately related to this role (similarity 0.54).
- Requirement: Pursuing B.Sc (CS/IT/Stats). Your bachelor's in commerce (from your profile) is in an unrelated field.
- Remote internship, so your location is not a constraint.

**3. Operations Intern — Meridian Analytics Inc** (score 50.8, completeness 1.0)
- You have 2 of 3 required skills (Communication, Excel). Missing: SQL. You have 0 of 2 preferred skills.
- Your resume is moderately related to this role (similarity 0.53).
- Requirement: Pursuing BCA/MCA. Your bachelor's in commerce (from your profile) is in an unrelated field.
- Remote internship, so your location is not a constraint.

**4. DevOps Intern — Quantumly Systems Pvt Ltd** (score 49.4, completeness 1.0)
- You have 1 of 3 required skills (Linux). Missing: AWS, CI/CD. You have 0 of 2 preferred skills.
- Your resume is moderately related to this role (similarity 0.51).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in commerce (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

**5. Cybersecurity Intern — Meridian Analytics Inc** (score 47.2, completeness 1.0)
- You have 1 of 3 required skills (Linux). Missing: Python, SQL. You have 0 of 2 preferred skills.
- Your resume is weakly related to this role (similarity 0.47).
- Requirement: Any Bachelor's degree (final year). Your bachelor's in commerce (from your profile) meets the requirement.
- Remote internship, so your location is not a constraint.

## 10_limited_information — Candidate with limited or missing information

### Extracted candidate information

- Normalized skills: Communication
- Education (resume): —
- Experience entries: 0 | Project entries: 0
- Degree used: — (source: missing)
- Location used: — (source: missing)
- Expected domains (evaluator): —

### Top 5 — pure semantic retrieval (FAISS)

| # | Internship | Company | Domain | Cosine |
|---|---|---|---|---|
| 1 | Content Marketing Intern | Lumenary Dynamics Inc | Digital Marketing | 0.3842 |
| 2 | Content Marketing Intern | Brightloop Robotics | Digital Marketing | 0.3473 |
| 3 | SEO Intern | Quantumly Systems Pvt Ltd | Digital Marketing | 0.3312 |
| 4 | Software Engineering Intern | Quantumly Robotics LLP | Software Development | 0.3300 |
| 5 | Frontend Developer Intern | Lumenary Dynamics LLP | Web Development | 0.3287 |

### Top 5 — final matching (candidates considered: 63)

| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Financial Analyst Intern — Pixelforge Softworks | Finance | Remote / Noida, India | 0.2196 | 0.00 | 32.8 | Weak | Communication | Excel, Financial Modeling | weak score (<45) |
| 2 | Operations Intern — Meridian Analytics Inc | Business Analysis | Remote / Bengaluru, India | 0.2293 | 0.00 | 32.8 | Weak | Communication | Excel, SQL | weak score (<45) |
| 3 | Business Analyst Intern — Skyfield Ventures | Business Analysis | Onsite / Remote | 0.2147 | 0.00 | 29.5 | Weak | Communication | Data Analysis, Excel, SQL | weak score (<45) |
| 4 | Business Analyst Intern — Pixelforge Softworks | Business Analysis | Remote / Chennai, India | 0.2274 | 0.00 | 29.5 | Weak | Communication | Data Analysis, Excel, SQL | weak score (<45) |
| 5 | Business Analyst Intern — Ironbridge Softworks Inc | Business Analysis | Remote / Jaipur, India | 0.2018 | 0.00 | 29.5 | Weak | Communication | Data Analysis, Excel, SQL | weak score (<45) |

#### Why each internship was recommended

**1. Financial Analyst Intern — Pixelforge Softworks** (score 32.8, completeness 0.85)
- You have 1 of 3 required skills (Communication). Missing: Excel, Financial Modeling. You have 0 of 3 preferred skills.
- Your resume is weakly related to this role (similarity 0.22).
- Requirement: Pursuing B.Sc (CS/IT/Stats). Your degree is unknown.
- Remote internship, so your location is not a constraint.
- _Missing information:_ Add your degree (for example 'B.Tech Computer Science') to your profile.

**2. Operations Intern — Meridian Analytics Inc** (score 32.8, completeness 0.85)
- You have 1 of 3 required skills (Communication). Missing: Excel, SQL. You have 0 of 2 preferred skills.
- Your resume is weakly related to this role (similarity 0.23).
- Requirement: Pursuing BCA/MCA. Your degree is unknown.
- Remote internship, so your location is not a constraint.
- _Missing information:_ Add your degree (for example 'B.Tech Computer Science') to your profile.

**3. Business Analyst Intern — Skyfield Ventures** (score 29.5, completeness 0.85)
- You have 1 of 4 required skills (Communication). Missing: Data Analysis, Excel, SQL. You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.21).
- Requirement: Pursuing B.Tech/B.E. (CS/IT preferred). Your degree is unknown.
- Remote internship, so your location is not a constraint.
- _Missing information:_ Add your degree (for example 'B.Tech Computer Science') to your profile.

**4. Business Analyst Intern — Pixelforge Softworks** (score 29.5, completeness 0.85)
- You have 1 of 4 required skills (Communication). Missing: Data Analysis, Excel, SQL. You have 0 of 3 preferred skills.
- Your resume is weakly related to this role (similarity 0.23).
- Requirement: Pursuing MBA. Your degree is unknown.
- Remote internship, so your location is not a constraint.
- _Missing information:_ Add your degree (for example 'B.Tech Computer Science') to your profile.

**5. Business Analyst Intern — Ironbridge Softworks Inc** (score 29.5, completeness 0.85)
- You have 1 of 4 required skills (Communication). Missing: Data Analysis, Excel, SQL. You have 0 of 1 preferred skills.
- Your resume is weakly related to this role (similarity 0.20).
- Requirement: Pursuing MBA. Your degree is unknown.
- Remote internship, so your location is not a constraint.
- _Missing information:_ Add your degree (for example 'B.Tech Computer Science') to your profile.

