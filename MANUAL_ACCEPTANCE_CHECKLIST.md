# CareerNova AI — Manual Acceptance Checklist

For the owner to run by hand. **Nothing here is pre-marked as passed** - write PASS / FAIL and a note in the last column.

**Where to test:** open http://localhost:5173 (development app). Recommended: use a **new test account** with a fictional
name and a test email you control, so existing records stay untouched. Use your own resume only if you are happy for
it to be stored in the dev database. Have ready: two resume versions (PDF and/or DOCX), one small PDF and one DOCX of
study notes, and a PNG/JPEG picture under 2 MB.

| # | Area | Steps | Expected result | Result |
|---|---|---|---|---|
| 1 | Registration and login | Register at `/register` → open the verification email (outbox folder in dev) → sign in | Account verified; dashboard opens | |
| 2 | Dashboard | Look at the four headline tiles and the cards | Real numbers or "—" with a reason; readiness tile names the scored resume version | |
| 3 | Profile editing | Profile → fill college, degree, graduation year, location → Save; reload | Values kept; completeness updates | |
| 4 | Profile picture | Upload a picture; check header and dashboard; then Remove | Picture shown everywhere; after removal, initials | |
| 5 | Resume upload | Resumes → upload a PDF or DOCX | "uploaded and parsed"; listed as V1 | |
| 6 | Resume extraction | Open the resume; check Projects, Education, Skills | One card per real project, with title, "Technologies:" line and all bullets; nothing invented | |
| 7 | Manual corrections | *Edit details* → fix something → Save | "Corrections saved"; readiness recalculates | |
| 8 | Re-parse confirmation | On the corrected resume press *Re-parse* → *Cancel* | Dialog "Re-parse and replace your corrections?"; Cancel keeps your corrections | |
| 9 | Resume versions | Upload a second version; *Rename version*; *Set as preferred* | V2 with your name; Preferred badge; "Used for matching" moves | |
| 10 | Resume comparison | *Compare versions* → pick V1 and V2 (optionally a role) | Added/removed skills and sections, measured verdict with reasons | |
| 11 | Readiness | Resumes → readiness panel | Score with categories, "Scored version: V…", explanation of what the score uses | |
| 12 | ATS keyword analysis | Matches → *Find my matches*; then Dashboard → ATS check | Keyword checks for the best match, labelled as checks (not an overall ATS score) | |
| 13 | Application Assistant | Ask "How does this application work?", "tell me more about step 4", "How can I improve my resume?", "who is ronaldo", "Give me HR interview questions" | Numbered steps with links and real status; step detail; your resume's own tips; polite refusal; redirect to the Interview assistant | |
| 14 | Interview Preparation Assistant | Open it; "Which roles are suitable for my resume?" → pick a role → *Technical questions* → "How do I answer question 2?" | Roles from your preferred resume; role questions; guidance with samples labelled as samples | |
| 15 | Career recommendations | Interview assistant → *Recommend suitable roles*; Career tracks page | Roles with evidence, missing skills and matching internships | |
| 16 | Mock interview | *Mock interview: <role>* → answer 2 questions → *Finish session* | Scores labelled as practice guidance; summary | |
| 17 | PDF/DOCX upload | Interview assistant → *Upload a study document* → PDF, then DOCX | Both uploaded and attached | |
| 18 | Multi-document Q&A | Ask a question needing both documents; then a question neither covers | Answer cites both files; honest "couldn't find" | |
| 19 | Citations | Check the references in the answer | File name and page (PDF) or section (DOCX); no invented pages | |
| 20 | Mobile responsiveness | Browser dev tools → 375 px width → Dashboard, Resumes, both assistants | No sideways scrolling; buttons usable | |

After testing, tell me which rows failed (with the note), and I will investigate.
