# CareerNova AI — Product overview

## What CareerNova AI is
CareerNova AI is a web application that helps students go from a resume to internship applications. A student uploads a resume, finds internships, sees how well they match, learns which skills are missing, creates a tailored resume and cover letter, practises interview questions and tracks applications. A career assistant answers questions about the student's own data and about how the product works.

## Who it is for
The application is built for students looking for internships. Administrators manage the internship catalogue, user roles and the search index.

## Main features
The main features are: resume upload and parsing, internship discovery with filters and AI (semantic) search, internship matching with a compatibility score, skill-gap analysis with learning plans, tailored resume and cover-letter generation, interview practice with feedback, application tracking with interview rounds and reminders, and the career assistant.

## How AI is used
Matching, skill gaps and the standard answers are built from the student's own data with deterministic rules and a local embedding model (all-MiniLM-L6-v2); no external AI service is needed. Optional AI features (AI-assisted writing for documents, AI-tailored interview questions and feedback, and AI-written assistant answers) are off by default. They work only when the server has an AI provider configured and the student turns the option on and gives explicit consent for that request.

## Is my data private? Data and privacy
Each student sees only their own resumes, matches, documents, practice sessions, applications and conversations. Before any optional AI request, names, contact details, addresses and PIN codes are removed. Reminders are stored in the application only; no email, SMS or push notification is sent for them.

## Internship data
The internship catalogue currently contains 180 synthetic postings with invented company names, created for demonstration and evaluation. It is not real job-market data.
