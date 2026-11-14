\# AI Career Companion — Database Schema Design



\## 1. Purpose



The database supports nine modules of the AI Career Companion:

student profile management, resume parsing, internship knowledge retrieval,

internship matching, skill gap analysis, document customization,

interview preparation, application tracking, and conversational assistance.



Database: PostgreSQL

ORM: SQLAlchemy

Backend: FastAPI (proposed architecture)



\## 2. Tables and Columns



\### 1. users

\- user\_id: Integer, Primary Key

\- first\_name: VARCHAR(100), NOT NULL

\- last\_name: VARCHAR(100), NOT NULL

\- email: VARCHAR(255), UNIQUE, NOT NULL

\- password\_hash: VARCHAR(255), NOT NULL

\- created\_at: TIMESTAMP WITH TIME ZONE, NOT NULL



\### 2. student\_profiles

\- profile\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id, UNIQUE

\- college: VARCHAR(200), nullable

\- degree: VARCHAR(150), nullable

\- graduation\_year: Integer, nullable

\- location: VARCHAR(150), nullable



\### 3. resumes

\- resume\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- filename: VARCHAR(255), NOT NULL

\- file\_path: VARCHAR(500), NOT NULL

\- file\_type: VARCHAR(20), NOT NULL

\- status: VARCHAR(30), default "uploaded"

\- uploaded\_at: TIMESTAMP WITH TIME ZONE



\### 4. resume\_extractions

\- extraction\_id: Integer, Primary Key

\- resume\_id: Integer, Foreign Key -> resumes.resume\_id

\- parser\_type: VARCHAR(30), NOT NULL

\- extracted\_data: JSON, NOT NULL

\- status: VARCHAR(30), default "completed"

\- error\_message: TEXT, nullable

\- created\_at: TIMESTAMP WITH TIME ZONE



\### 5. skills

\- skill\_id: Integer, Primary Key

\- name: VARCHAR(100), UNIQUE, NOT NULL

\- category: VARCHAR(80), nullable

\- Index uq\_skills\_name\_lower: UNIQUE on lower(name), so names are unique regardless of case (added in migration a1c4e2b7d9f0)

\- Rows are shared by all resumes and internships and are never deleted when a resume is deleted. Unknown skills are stored with category "other".



\### 6. resume\_skills

\- resume\_id: Integer, Foreign Key -> resumes.resume\_id, Primary Key

\- skill\_id: Integer, Foreign Key -> skills.skill\_id, Primary Key

\- proficiency: VARCHAR(30), nullable

\- evidence: TEXT, nullable (source section and raw text, e.g. "technical\_skills: React.js")

\- Rows for one resume are replaced on upload and re-parse, and deleted with that resume.



\### 7. internships

\- internship\_id: Integer, Primary Key

\- title: VARCHAR(200), NOT NULL

\- company: VARCHAR(200), NOT NULL

\- description: TEXT, nullable

\- eligibility: TEXT, nullable

\- location: VARCHAR(150), nullable

\- application\_url: VARCHAR(1000), nullable

\- deadline: TIMESTAMP WITH TIME ZONE, nullable

\- is\_active: BOOLEAN, default TRUE

\- created\_at: TIMESTAMP WITH TIME ZONE

\- updated\_at: TIMESTAMP WITH TIME ZONE



\### 8. internship\_skills

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, Primary Key

\- skill\_id: Integer, Foreign Key -> skills.skill\_id, Primary Key

\- importance: VARCHAR(30), default "required"



\### 9. knowledge\_documents

\- document\_id: Integer, Primary Key

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, nullable

\- title: VARCHAR(300), NOT NULL

\- source\_type: VARCHAR(50), NOT NULL

\- source\_url: VARCHAR(1000), nullable

\- storage\_key: VARCHAR(500), nullable

\- content\_hash: VARCHAR(128), nullable

\- indexing\_status: VARCHAR(30), default "pending"

\- created\_at: TIMESTAMP WITH TIME ZONE

\- indexed\_at: TIMESTAMP WITH TIME ZONE, nullable



\### 10. match\_results

\- match\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- resume\_id: Integer, Foreign Key -> resumes.resume\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id

\- score: FLOAT, NOT NULL

\- explanation: TEXT, nullable

\- created\_at: TIMESTAMP WITH TIME ZONE



\### 11. skill\_gap\_recommendations

\- recommendation\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- skill\_id: Integer, Foreign Key -> skills.skill\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, nullable

\- gap\_level: VARCHAR(30), default "identified"

\- recommended\_action: TEXT, NOT NULL

\- status: VARCHAR(30), default "pending"

\- created\_at: TIMESTAMP WITH TIME ZONE



\### 12. generated\_documents

\- document\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- resume\_id: Integer, Foreign Key -> resumes.resume\_id, nullable

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, nullable

\- document\_type: VARCHAR(50), NOT NULL

\- title: VARCHAR(255), nullable

\- content: TEXT, NOT NULL

\- file\_path: VARCHAR(500), nullable

\- created\_at: TIMESTAMP WITH TIME ZONE



\### 13. interview\_sessions

\- session\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, nullable

\- status: VARCHAR(30), default "started"

\- score: FLOAT, nullable

\- started\_at: TIMESTAMP WITH TIME ZONE

\- completed\_at: TIMESTAMP WITH TIME ZONE, nullable



\### 14. interview\_questions

\- question\_id: Integer, Primary Key

\- session\_id: Integer, Foreign Key -> interview\_sessions.session\_id

\- question\_text: TEXT, NOT NULL

\- question\_type: VARCHAR(50), nullable

\- user\_answer: TEXT, nullable

\- feedback: TEXT, nullable

\- score: FLOAT, nullable

\- created\_at: TIMESTAMP WITH TIME ZONE



\### 15. applications

\- application\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id

\- status: VARCHAR(30), default "saved"

\- notes: TEXT, nullable

\- applied\_at: TIMESTAMP WITH TIME ZONE, nullable

\- created\_at: TIMESTAMP WITH TIME ZONE

\- updated\_at: TIMESTAMP WITH TIME ZONE

\- Constraint: one application record per user and internship



\### 16. conversations

\- conversation\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- title: VARCHAR(255), nullable

\- created\_at: TIMESTAMP WITH TIME ZONE

\- updated\_at: TIMESTAMP WITH TIME ZONE



\### 17. messages

\- message\_id: Integer, Primary Key

\- conversation\_id: Integer, Foreign Key -> conversations.conversation\_id

\- sender: VARCHAR(20), NOT NULL

\- content: TEXT, NOT NULL

\- sources: JSON, nullable

\- created\_at: TIMESTAMP WITH TIME ZONE

\- Constraint: sender is user, assistant, or system



\## 3. Key Relationships



1\. users -> student\_profiles: One-to-one

2\. users -> resumes: One-to-many

3\. resumes -> resume\_extractions: One-to-many

4\. resumes <-> skills: Many-to-many through resume\_skills

5\. internships <-> skills: Many-to-many through internship\_skills

6\. internships -> knowledge\_documents: One-to-many

7\. users, resumes, internships -> match\_results

8\. users, skills, internships -> skill\_gap\_recommendations

9\. users, resumes, internships -> generated\_documents

10\. users -> interview\_sessions: One-to-many

11\. interview\_sessions -> interview\_questions: One-to-many

12\. users and internships -> applications

13\. users -> conversations: One-to-many

14\. conversations -> messages: One-to-many



\## 4. Storage Design



\- PostgreSQL: structured application records.

\- Private file storage: original resumes and generated files.

\- Vector index: text chunks and embeddings for RAG retrieval.

\- The relational database stores metadata about knowledge documents,

&#x20; not the entire vector index.



\## 5. Data Integrity and Security



\- Primary keys identify records.

\- Foreign keys maintain relationships.

\- Unique constraints prevent duplicate email addresses and duplicate

&#x20; user-internship application pairs.

\- Passwords must be securely hashed; plain-text passwords must never

&#x20; be stored.

\- Protected endpoints must check authentication and resource ownership.

\- Database credentials must be kept outside source code.



\## 6. Implementation Status



The 17 SQLAlchemy model definitions and their mapper relationships

have been verified in Python.



The PostgreSQL tables still need to be created and verified locally.

