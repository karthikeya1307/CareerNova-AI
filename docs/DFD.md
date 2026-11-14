# AI Career Companion — Data Flow Diagram (DFD)

## 1. Purpose

This DFD explains how data flows between the student, React
frontend, FastAPI backend, nine project modules, PostgreSQL,
private file storage, the vector index, and the LLM service.

## 2. Level 1 Data Flow Diagram

```mermaid
flowchart TD
    STUDENT[Student]
    UI[React Frontend]
    API([FastAPI Backend API])

    P1([1. Account and Profile Management])
    P2([2. Resume Parsing and Skill Extraction])
    P3([3. Internship Knowledge Base and RAG])
    P4([4. Internship Matching])
    P5([5. Skill Gap Analysis])
    P6([6. Resume and Cover Letter Generation])
    P7([7. Interview Preparation])
    P8([8. Application Tracking])
    P9([9. Conversational Career Assistant])

    D1[(D1: PostgreSQL Database)]
    D2[(D2: Private File Storage)]
    D3[(D3: Vector Index)]

    SOURCE[Trusted Internship Sources]
    LLM[LLM Service]

    STUDENT -->|Actions and questions| UI
    UI -->|HTTP requests, JSON and files| API

    API --> P1
    API --> P2
    API --> P3
    API --> P4
    API --> P5
    API --> P6
    API --> P7
    API --> P8
    API --> P9

    P1 -->|Account and profile records| D1
    D1 -->|Authorized profile data| P1
    P1 -->|Authentication and profile result| API

    P2 -->|Original resume| D2
    D2 -->|Resume file for processing| P2
    P2 -->|Extracted data and skills| D1
    P2 -->|Extraction result| API

    SOURCE -->|Internship descriptions and resources| P3
    P3 -->|Internship records and metadata| D1
    P3 -->|Text chunks and embeddings| D3
    P3 -->|Indexing result| API

    D1 -->|Student skills and internship requirements| P4
    P4 -->|Compatibility scores and explanations| D1
    P4 -->|Matching results| API

    D1 -->|Student skills and role requirements| P5
    P5 -->|Skill-gap recommendations| D1
    P5 -->|Learning suggestions| API

    D1 -->|Resume and internship context| P6
    P6 -->|Generated document metadata| D1
    P6 -->|Generated files| D2
    P6 -->|Customized documents| API

    D1 -->|Student and internship context| P7
    P7 -->|Questions, answers and feedback| D1
    P7 -->|Interview results| API

    P8 -->|Application records| D1
    D1 -->|Saved applications and statuses| P8
    P8 -->|Tracking results| API

    D1 -->|Authorized student context| P9
    D3 -->|Relevant knowledge chunks| P9
    P9 -->|Question and retrieved evidence| LLM
    LLM -->|Generated answer| P9
    P9 -->|Conversation and message records| D1
    P9 -->|Answer and available sources| API

    API -->|HTTP status and JSON response| UI
    UI -->|Display results| STUDENT
```

## 3. Data Stores

- D1 — PostgreSQL: Stores user accounts, profiles, resume metadata,
  extracted information, skills, internships, matching results,
  recommendations, generated-document metadata, interview records,
  applications, conversations, and messages.

- D2 — Private File Storage: Stores original resumes and generated
  files. PostgreSQL stores their metadata and file locations.

- D3 — Vector Index: Stores searchable text chunks and embeddings
  for Retrieval-Augmented Generation (RAG).

## 4. Process Summary

1. Account and Profile Management handles account and profile data.
2. Resume Parsing extracts structured information from uploaded resumes.
3. Internship Knowledge Base and RAG prepare and retrieve relevant
   internship and career-resource information.
4. Internship Matching compares student skills with internship
   requirements and calculates compatibility scores.
5. Skill Gap Analysis identifies missing skills and recommends
   learning activities.
6. Document Generation creates customized resumes and cover letters.
7. Interview Preparation manages practice questions, answers, and feedback.
8. Application Tracking manages saved internships and application statuses.
9. Career Assistant retrieves relevant context and asks the LLM to
   generate an evidence-grounded response.

## 5. Security and Design Notes

- Protected endpoints must validate authentication and authorization.
- Students must only access records they are permitted to view.
- Uploaded files must be validated and stored privately.
- Internship-specific answers should use reliable, relevant sources
  where available.
- This DFD represents the proposed architecture; it does not imply
  that all nine modules have already been implemented.