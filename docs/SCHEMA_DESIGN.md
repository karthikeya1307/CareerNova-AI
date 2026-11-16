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

\- is\_active: BOOLEAN, default TRUE (deactivated internships are hidden from students and from search)

\- created\_at: TIMESTAMP WITH TIME ZONE

\- updated\_at: TIMESTAMP WITH TIME ZONE

\- Added in migration b7e3d1f4a2c8:

  \- external\_id: VARCHAR(64), UNIQUE, nullable (dataset ID, used for idempotent imports)

  \- domain: VARCHAR(80), nullable, indexed

  \- work\_mode: VARCHAR(20), nullable, CHECK IN ('Onsite', 'Hybrid', 'Remote')

  \- duration\_weeks: Integer, nullable, CHECK > 0

  \- stipend\_per\_month: Integer, nullable, CHECK >= 0

  \- stipend\_currency: VARCHAR(3), NOT NULL, default 'INR'

  \- min\_education: VARCHAR(200), nullable

  \- source: VARCHAR(30), NOT NULL, default 'manual', CHECK IN ('dataset', 'admin', 'manual')



\### 8. internship\_skills

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, Primary Key

\- skill\_id: Integer, Foreign Key -> skills.skill\_id, Primary Key

\- importance: VARCHAR(30), default "required", CHECK IN ('required', 'preferred') (migration b7e3d1f4a2c8)



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

\- Added in migration b7e3d1f4a2c8:

  \- content: TEXT, nullable (exact text that was embedded; used as RAG context)

  \- embedding\_model: VARCHAR(200), nullable

  \- error\_message: TEXT, nullable

  \- UNIQUE (internship\_id, source\_type)

\- indexing\_status values: pending, indexed, failed, inactive

\- document\_id is the vector ID stored in the FAISS index. PostgreSQL is the source of truth; every search result is re-checked here.



\### 10. match\_results

\- match\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- resume\_id: Integer, Foreign Key -> resumes.resume\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id

\- score: FLOAT, NOT NULL (final compatibility score, 0-100; CHECK 0 <= score <= 100)

\- explanation: TEXT, nullable

\- created\_at: TIMESTAMP WITH TIME ZONE

\- Added in migration c4f8a9e2b6d1 (all nullable):

  \- run\_id: UUID, indexed (rows of one matching request share it; earlier runs are kept)

  \- rank: Integer

  \- label: VARCHAR(20), CHECK IN ('Excellent', 'Strong', 'Fair', 'Weak')

  \- algorithm\_version: VARCHAR(20) (currently "v1")

  \- skill\_score, semantic\_score (NULL when unavailable), education\_score, location\_score: FLOAT, 0-1

  \- required\_skill\_coverage: FLOAT, nullable

  \- data\_completeness: FLOAT, CHECK 0-1 (share of weight assessed with real data)

  \- breakdown: JSON (components with status, matched/missing skills, explanation, caps, run metadata)

  \- UNIQUE (run\_id, internship\_id); INDEX (resume\_id, created\_at)

\- Deleting a resume or user deletes its match results (ON DELETE CASCADE); internships and skills are never affected.



\### 11. skill\_gap\_recommendations

\- recommendation\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- skill\_id: Integer, Foreign Key -> skills.skill\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, nullable

\- gap\_level: VARCHAR(30), default "identified", CHECK IN ('identified', 'missing', 'partial')

\- recommended\_action: TEXT, NOT NULL

\- status: VARCHAR(30), default "pending", CHECK IN ('pending', 'in\_progress', 'completed', 'dismissed')

\- created\_at: TIMESTAMP WITH TIME ZONE

\- Added in migration d5a1c7e3f9b2 (Phase 4, additive):

  \- resume\_id: Integer, Foreign Key -> resumes.resume\_id (ON DELETE CASCADE), nullable, indexed

  \- importance: VARCHAR(20), CHECK IN ('required', 'preferred')

  \- priority\_score: FLOAT, CHECK 0-100

  \- demand\_count: Integer; internship\_ids: JSON (internships that need the skill)

  \- related\_skills: JSON (candidate skills that partially cover it)

  \- learning\_plan: JSON; learning\_plan\_version: VARCHAR(20)

  \- source: VARCHAR(30) ('match\_run' or 'selection'); source\_run\_id: UUID

  \- is\_current: BOOLEAN NOT NULL default TRUE (false when the latest analysis no longer includes the skill)

  \- completed\_via: VARCHAR(20), CHECK IN ('user', 'resume'); started\_at, completed\_at: TIMESTAMP WITH TIME ZONE

  \- updated\_at: TIMESTAMP WITH TIME ZONE NOT NULL default now()

  \- UNIQUE (user\_id, resume\_id, skill\_id); INDEX (user\_id, status)

\- Regenerating recommendations updates the existing row for the same skill and preserves its progress status.



\### 12. generated\_documents

\- document\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- resume\_id: Integer, Foreign Key -> resumes.resume\_id, nullable

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, nullable

\- document\_type: VARCHAR(50), NOT NULL, CHECK IN ('resume', 'cover\_letter')

\- title: VARCHAR(255), nullable

\- content: TEXT, NOT NULL (rendered text of the current version)

\- file\_path: VARCHAR(500), nullable (unused; downloads are rendered on request)

\- created\_at: TIMESTAMP WITH TIME ZONE

\- Added in migration e7b2d4f6a8c1 (Phase 5, additive):

  \- content\_json: JSON (structured sections/paragraphs with cited fact ids)

  \- generation\_method: VARCHAR(20), CHECK IN ('deterministic', 'llm'); llm\_provider, llm\_model

  \- fact\_check: JSON (checked statements, rejected statements, warnings); ats\_report: JSON; options: JSON

  \- current\_version: Integer NOT NULL default 1 (CHECK >= 1); updated\_at: TIMESTAMP NOT NULL default now()

\- Resume deletion sets resume\_id to NULL (the student's document is kept); user deletion deletes documents.

\### 12a. generated\_document\_versions (Phase 5)

\- version\_id: Integer, Primary Key

\- document\_id: Integer, Foreign Key -> generated\_documents.document\_id (ON DELETE CASCADE), indexed

\- version: Integer; UNIQUE (document\_id, version)

\- content: TEXT, NOT NULL; content\_json: JSON, NOT NULL

\- source: VARCHAR(20), CHECK IN ('generated', 'edited', 'restored')

\- fact\_check: JSON, nullable; created\_at: TIMESTAMP WITH TIME ZONE



\### 13. interview\_sessions

\- session\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id, nullable

\- status: VARCHAR(30), default "started", CHECK IN ('started', 'in\_progress', 'completed', 'abandoned')

\- score: FLOAT, nullable (overall 0-100; unanswered questions count as 0)

\- started\_at: TIMESTAMP WITH TIME ZONE

\- completed\_at: TIMESTAMP WITH TIME ZONE, nullable

\- Added in migration f3c9e1a5b7d2 (Phase 6, additive):

  \- resume\_id: Integer, Foreign Key -> resumes.resume\_id (ON DELETE SET NULL), indexed

  \- title, mode (CHECK IN ('practice', 'mock')), question\_mix JSON, difficulty

  \- generation\_method, llm\_provider, llm\_model

  \- total\_questions, answered\_count (NOT NULL default 0), summary JSON, updated\_at

  \- INDEX (user\_id, status)



\### 14. interview\_questions

\- question\_id: Integer, Primary Key

\- session\_id: Integer, Foreign Key -> interview\_sessions.session\_id

\- question\_text: TEXT, NOT NULL

\- question\_type: VARCHAR(50), nullable

\- user\_answer: TEXT, nullable (latest attempt)

\- feedback: TEXT, nullable (latest attempt)

\- score: FLOAT, nullable (latest attempt, 0-100)

\- created\_at: TIMESTAMP WITH TIME ZONE

\- Added in migration f3c9e1a5b7d2 (Phase 6, additive):

  \- category: CHECK IN ('technical', 'project', 'behavioral', 'internship'); position (UNIQUE per session)

  \- skill\_id: Foreign Key -> skills.skill\_id (ON DELETE SET NULL); bank\_question\_id; source\_fact\_ids JSON

  \- difficulty: CHECK IN ('easy', 'medium', 'hard'); key\_points JSON; explanation; suggested\_answer JSON; context JSON

  \- time\_limit\_seconds; revealed\_at; answered\_at; evaluation JSON

\### 14a. interview\_answers (Phase 6)

\- answer\_id: Integer, Primary Key

\- question\_id: Integer, Foreign Key -> interview\_questions.question\_id (ON DELETE CASCADE), indexed

\- attempt: Integer; UNIQUE (question\_id, attempt)

\- answer\_text: TEXT NOT NULL; time\_taken\_seconds: Integer

\- score: FLOAT NOT NULL (0-100); evaluation: JSON NOT NULL; feedback: TEXT NOT NULL

\- feedback\_source: VARCHAR(20), CHECK IN ('rubric', 'llm'); created\_at

\- Deleting a session deletes its questions and answers; deleting a user deletes everything; deleting a resume keeps the history with resume\_id NULL.



\### 15. applications

\- application\_id: Integer, Primary Key

\- user\_id: Integer, Foreign Key -> users.user\_id

\- internship\_id: Integer, Foreign Key -> internships.internship\_id

\- status: VARCHAR(30), default "saved"

\- notes: TEXT, nullable

\- applied\_at: TIMESTAMP WITH TIME ZONE, nullable

\- created\_at: TIMESTAMP WITH TIME ZONE

\- updated\_at: TIMESTAMP WITH TIME ZONE

\- Extended in migration a9d3f6b2c8e4 (Phase 7):

  \- internship\_id: now nullable, Foreign Key -> internships.internship\_id ON DELETE SET NULL (was CASCADE)

  \- source: VARCHAR(20) NOT NULL, CHECK IN ('internal', 'external'); external rows have no internship\_id

  \- company\_name, title: VARCHAR(200) NOT NULL (copied from the internship for internal applications); company\_key: normalised company name

  \- application\_url (1000), application\_url\_normalized (1000), external\_reference (100), domain (80), location (150), work\_mode (CHECK IN ('Onsite', 'Hybrid', 'Remote'))

  \- contact\_name (120), contact\_email (255): optional

  \- resume\_document\_id, cover\_letter\_document\_id: Foreign Key -> generated\_documents.document\_id ON DELETE SET NULL

  \- status: VARCHAR(30), default 'SAVED', CHECK IN ('SAVED', 'APPLIED', 'SHORTLISTED', 'INTERVIEW\_SCHEDULED', 'SELECTED', 'REJECTED', 'WITHDRAWN'); legacy lowercase values are mapped by the migration, and legacy rows already past SAVED (except WITHDRAWN) without an application date get applied\_at = updated\_at (else created\_at)

  \- status\_changed\_at, deleted\_at (trash / soft delete): TIMESTAMP WITH TIME ZONE

  \- Indexes: (user\_id, status), (user\_id, updated\_at), (user\_id, applied\_at)

  \- Partial unique indexes (ignoring trashed rows): (user\_id, internship\_id); (user\_id, application\_url\_normalized) for external rows; (user\_id, company\_key, external\_reference)

  \- The original UNIQUE (user\_id, internship\_id) constraint is replaced by the partial unique index

\### 15a. saved\_internships (Phase 7)

\- bookmark\_id: Integer, Primary Key

\- user\_id: Foreign Key -> users.user\_id ON DELETE CASCADE, indexed

\- internship\_id: Foreign Key -> internships.internship\_id ON DELETE CASCADE, indexed

\- created\_at; UNIQUE (user\_id, internship\_id)

\### 15b. application\_status\_history (Phase 7)

\- history\_id: Integer, Primary Key

\- application\_id: Foreign Key -> applications.application\_id ON DELETE CASCADE

\- from\_status (nullable), to\_status: CHECK against the seven statuses

\- change\_type: CHECK IN ('created', 'manual', 'correction', 'interview\_added', 'interview\_cancelled', 'migrated')

\- changed\_at; INDEX (application\_id, changed\_at)

\### 15c. application\_interviews (Phase 7)

\- interview\_id: Integer, Primary Key; application\_id: Foreign Key ON DELETE CASCADE

\- round\_number: UNIQUE per application, >= 1

\- interview\_type: CHECK IN ('technical', 'hr', 'behavioral', 'managerial', 'case\_study', 'assignment', 'group', 'other'); mode: CHECK IN ('online', 'offline', 'phone')

\- scheduled\_at (TIMESTAMP WITH TIME ZONE), duration\_minutes (5-600), meeting\_url (500), location (200), preparation\_notes, feedback

\- outcome: CHECK IN ('pending', 'passed', 'failed', 'cancelled', 'no\_show'), default 'pending'

\- interview\_session\_id: Foreign Key -> interview\_sessions.session\_id ON DELETE SET NULL (Phase 6 link)

\- created\_at, updated\_at; INDEX (application\_id, scheduled\_at)

\### 15d. application\_reminders (Phase 7)

\- reminder\_id: Integer, Primary Key; application\_id: Foreign Key ON DELETE CASCADE

\- title (150), description, remind\_at (TIMESTAMP WITH TIME ZONE), is\_completed (default false), completed\_at, created\_at, updated\_at

\- INDEX (application\_id, remind\_at), INDEX (is\_completed, remind\_at). Stored only; never delivered.

\### 15e. application\_activity (Phase 7)

\- activity\_id: Integer, Primary Key; application\_id: Foreign Key ON DELETE CASCADE

\- event\_type: CHECK against 13 event names; details: JSON (statuses, field names, round numbers and ids only)

\- created\_at; INDEX (application\_id, created\_at)

\- Deletion: moving an application to the trash keeps every related row; permanent deletion removes the application and (by cascade) its history, rounds, reminders and activity; deleting a user removes everything.


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

\- Extended in migration b2e8c4a7d1f5 (Phase 8):

  \- conversations.resume\_id: Foreign Key -> resumes.resume\_id ON DELETE SET NULL, indexed

  \- conversations.context: JSON - pointers only (last\_result\_message\_id, focus {type, id, message\_id}); never resume facts

  \- conversations.message\_count (NOT NULL, default 0), last\_message\_at; INDEX (user\_id, updated\_at)

  \- messages.resume\_id: Foreign Key -> resumes.resume\_id ON DELETE CASCADE - set on both messages of a turn that used resume data, so deleting the resume deletes that turn

  \- messages.intent, entities (JSON), result\_set (JSON: ordered items shown, for follow-ups), suggested\_actions (JSON), generation\_method (CHECK IN ('deterministic', 'llm')), llm\_provider, llm\_model, fact\_check (JSON), warnings (JSON); INDEX (conversation\_id, message\_id)

  \- messages.sources: JSON list of {type, id, label}

\### 17a. assistant\_rate\_limits (Phase 8)

\- user\_id: Foreign Key -> users.user\_id ON DELETE CASCADE

\- bucket: CHECK IN ('minute', 'day', 'llm\_hour'); window\_start: TIMESTAMP WITH TIME ZONE; count: Integer >= 0

\- PRIMARY KEY (user\_id, bucket, window\_start); INDEX (window\_start); incremented atomically with INSERT ... ON CONFLICT DO UPDATE; rows older than two days are removed



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

12\. users and internships -> applications (internship optional for external applications); applications -> status history, interview rounds, reminders and activity: one-to-many; users -> saved\_internships <- internships

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

