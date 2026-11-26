# CareerNova AI — Demo Guide

Demos 1–6 were run live on 2026-11-25 against the **test** database (backend port 8001, frontend port 5174). Every
"You should see" is what was actually seen, except steps marked † (covered by automated tests, not repeated live). The earlier demos A–C (2026-11-24) are kept at the end.

> Changes made after the live run (covered by automated tests, not re-demoed): quoted passages are limited to those
> scoring ≥ 60% of the best one, and the Application Assistant again answers "give me a learning plan" / skill-gap /
> practice-question requests itself instead of redirecting them.
> Later the same day (also tests only): a short unrelated question right after a product question ("who is ronaldo")
> is declined instead of being answered from the product guide, and the Application Assistant's
> "Help me prepare for an interview" suggestion is now a link that opens the Interview Prep Assistant directly.

## Before the demo

1. **Pick the database.**
   - **`career_companion_test`** (recommended): no dev data is touched.
   - **`career_companion_dev`:** migrated to head (`a7c9e1b3d5f6`) on 2026-11-25. Never register demo accounts or
     upload demo files there; use the test database for demos.
2. **Start the backend and the frontend:**

   ```powershell
   cd "<project-root>"
   $env:DB_NAME='career_companion_test'
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
   ```

   ```powershell
   cd "<project-root>\frontend"
   $env:BACKEND_URL='http://127.0.0.1:8001'
   npm run dev -- --port 5174
   ```

   Check http://127.0.0.1:8001/health shows `career_companion_test`.
3. **Optional AI** for document answers: `LLM_PROVIDER=ollama` with Ollama running (`ollama pull gemma3`).
4. **Sign in** as a student with a parsed resume. Have ready: a second resume version (PDF/DOCX), a short PDF and a
   DOCX of study notes (selectable text), and a small PNG/JPEG for the profile picture.

## Before demoing a deployed copy
The production deployment is prepared but not yet done (see `DEPLOYMENT_AND_HANDOVER_GUIDE.md` §7). Until it is, run
the demos locally as described below. In production, `EMAIL_MODE=outbox` means new users cannot verify their email -
configure SMTP first or demo with an invited/admin account.

## Final audit additions (2026-11-26, verified live on the test stack)

- **Application Assistant:** ask "How does this application work?" - 10 numbered steps with ✓ only for what your data
  proves, "Your next step" with an Open… link; then "tell me more about step 6", "How can I find internships?",
  "How can I improve my resume?" (shows that resume's own top readiness recommendations).
- **Resume extraction:** upload a resume whose projects use dash bullets and a right-aligned technology list - each
  project appears once with its title, a "Technologies:" line and all bullets.
- **Corrections:** Edit details → save; then Re-parse asks "Re-parse and replace your corrections?" - Cancel keeps them.
- **Readiness:** the panel shows "Scored version: V…"; uploading the same file again shows the identical-content note.

## Demo 1 — Application Assistant (2 minutes)

| # | Do | You should see |
|---|---|---|
| 1 | Sidebar → **AI assistants → Application Assistant** | Chat titled Application Assistant; switch at the top to the Interview Prep Assistant |
| 2 | Ask "How do I upload my resume?" | Steps from the CareerNova guide, with a link to Resumes |
| 3 | Ask "What's the capital of France?" | Polite refusal: it only helps with CareerNova and your own data |
| 4 | Ask "Give me HR interview questions" | Redirect card with a button to the **Interview Prep Assistant** |
| 5 | Ask "Which internships match me?" † | Your matches, with sources |
| 6 | Ask "How do I upload my resume?", then "who is ronaldo" † | The second answer is the polite refusal, with no guide text and no sources |
| 7 | Click the suggestion **Help me prepare for an interview** † | Opens the Interview Prep Assistant directly; no message is sent |

## Demo 2 — Interview Preparation Assistant (4 minutes)

| # | Do | You should see |
|---|---|---|
| 1 | Switch to **Interview Prep Assistant** | Its own conversation list, the prep chips and the study-document panel |
| 2 | **Recommend suitable roles** | Roles with fit /100, evidence, missing skills, **preparation priorities** and **matching internships** per role. Uses your **preferred** resume version |
| 3 | Pick **Data Analyst** | "Target role set"; **Mock interview: Data Analyst** button |
| 4 | **Technical questions**, then "How do I answer question 2?" | Levelled questions; guidance with a sample labelled as a sample |
| 5 | **HR questions** | Includes a problem-solving question |
| 6 | **My preparation roadmap** | Priorities, hours, "Interview questions to practise" and "Resource:" lines |
| 7 | **Mock interview: Data Analyst** → Start | Questions only about the role's skills (SQL first); scores labelled as practice |
| 8 | In this chat ask "How do I change my password?" † | Redirect to the Application Assistant |

## Demo 3 — Several study documents (4 minutes)

| # | Do | You should see |
|---|---|---|
| 1 | Study panel → upload the PDF, then the DOCX → **Use in this chat** for both | Both listed as attached (up to 5), each with **Remove** |
| 2 | Ask a question each document answers part of (e.g. "What is ACID and what is encapsulation?") | One answer citing both, e.g. **[dbms.pdf, p. 2]** and **[oop.docx, section "…"]** |
| 3 | Ask a follow-up ("explain the first one more") | Answer stays on the same topic |
| 4 | "Generate interview questions from these documents" | Questions with the documents' answers and references |
| 5 | Ask something neither document covers | "I couldn't find this in your documents…", no sources |

## Demo 4 — Profile picture and bio (2 minutes)

| # | Do | You should see |
|---|---|---|
| 1 | Profile → **Profile picture** → upload a PNG/JPEG | Preview; picture in the header menu, dashboard hero and your chat messages |
| 2 | Try a `.gif` or a >2 MB file † | Clear error; nothing saved |
| 3 | Edit the **bio** → Save → reload | Bio and picture persist |
| 4 | **Remove** picture † | Initials shown everywhere |

## Demo 5 — Resume versions and comparison (3 minutes)

| # | Do | You should see |
|---|---|---|
| 1 | Resumes → upload a second version | Listed as **V2**; V1 kept |
| 2 | **Rename** V2 ("Data-analyst focused"), **Set as preferred** | Preferred badge moves to V2 |
| 3 | **Compare** V1 with V2, role Data Analyst (optionally an internship) | Verdict with measured reasons (in the live run: contact 10 vs 8, Data Analyst fit 100 vs 75), skills added/removed, section changes, keywords that lost evidence, recommendations |

## Demo 6 — Privacy (1 minute, API)

A second student requesting the first student's resume, comparison, study document, chats or prep data gets **404**;
requests without a token get **401**. (Run live with a script against port 8001.)

## Earlier demos (2026-11-24)

- **A — Resume-based preparation:** roles → technical/HR questions → guidance → roadmap.
- **B — Document Q&A:** single PDF/DOCX, page/section references, "not found", optional AI summary.
- **C — Mock interview:** role-based session, feedback with missing concepts, summary.

## Talking points

- The two assistants are deliberately separate: the Application Assistant never becomes a general chatbot.
- Everything about the candidate comes from their own resume; samples are labelled; nothing is invented.
- Comparison verdicts come only from measured score differences of at least 5 points.
- Document answers cite file and page/section; "auto" RAG uses the agentic path only for multi-part questions, where
  the evaluation showed it helps.
- AI is optional and local; every feature works without it.
