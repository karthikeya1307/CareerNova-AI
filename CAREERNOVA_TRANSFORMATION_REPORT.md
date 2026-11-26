# CareerNova AI — Transformation Report

*Your Skills. Your Potential. Your Career.*

Date: 2026-11-24 · Branch: `careernova/dashboard-redesign` (rollback checkpoint: stash
`CareerNova pre-dashboard backup`, untouched) · Nothing committed or pushed.

All live checks ran against **`career_companion_test`** with a throw-away super admin and two
throw-away students; emails went to a scratch outbox (`EMAIL_MODE=outbox` forced for the run);
the test search index was built in a scratch folder so the owner's index at
`backend/data/faiss_index` was not touched. `career_companion_dev` was only read (revision check).

## 1. Implemented changes

### Branding
- Product name **CareerNova AI** and tagline everywhere a user sees it: browser titles (every page),
  meta description / theme colour / Open Graph, favicon (`frontend/public/favicon.svg`), logo
  (`BrandMark`: nova star + wordmark), sidebar, sign-in/registration panel, dashboard hero, empty
  states, assistant replies ("Here is what the CareerNova AI guide says"), product guide
  (`backend/data/product_docs/01_overview.md`, `07_…`), API title/description and welcome message.
  Emails already used CareerNova AI.
- The assistant still understands the old name (and "this app") in questions.
- One source of truth: `frontend/src/config/brand.js` (`APP_NAME`, `APP_TAGLINE`, `pageTitle()`).
- Not renamed on purpose: database names, migrations, internal identifiers, API paths, historical
  records, the project folder and older reports.

### Design system (Tailwind, no new dependencies)
- Tokens in `frontend/tailwind.config.js`: `brand` indigo (#635BDB, 5.2:1 on white), `navy`
  (#101B36), `mint` (#EAF7F3 … #0F3D31), re-tuned `slate` neutrals (page #F5F6FA, text #172033,
  secondary #697386 at 4.8:1), fonts (Inter body, Plus Jakarta Sans headings), shadows, radii,
  keyframes.
- `frontend/src/index.css`: base styles, focus ring, `cn-card`, `cn-hero`, `cn-input`,
  `cn-gradient-text`, `cn-skeleton` (shimmer), and a global `prefers-reduced-motion` rule.
- Shared components restyled with unchanged props: Button (+ `inverse` variant, press feedback),
  Badge (+ `ai` tone, ring), Card, Input, Select, Checkbox, Modal (blurred backdrop, scale-in,
  scrollable), EmptyState (icon), ErrorAlert (icon), Spinner, ProfileMenu (gradient avatar,
  role badge).
- 46 page files moved to the tokens: raw inputs use `cn-input`, cards use the card shadow, link
  buttons use the button radius/weight, success colour `emerald` → `mint`, page headings use the
  display font at a larger size.

### Layout and navigation
- **Sidebar**: navy with indigo glow; groups Overview / Your profile / Opportunities / Grow your
  skills / AI assistant; **Admin** group only for administrators (unchanged rule, backend still
  enforces it); active indicator bar plus `aria-current`; tagline card.
- **Mobile drawer**: same design, slide-in, keeps the focus trap, Escape, backdrop close, close on
  navigation and focus return.
- **Header**: sticky, translucent; "Ask the assistant" shortcut; profile menu with logout.
- **Page transitions**: fade-in per top-level section (re-keying by full path would remount the
  assistant mid-conversation — found by a test and fixed).

### Dashboard (career command center)
- Navy hero: greeting, tagline, primary actions (Browse internships, Practise interviews, Admin
  overview for admins).
- **Four live stats**: resume readiness (`GET /resumes/{id}/readiness`), best match
  (latest match run), applications plus upcoming interviews (`/applications/dashboard`), and
  interview practice average (`/interviews/progress`). Each shows "—" with the reason when there
  is no data. No invented numbers.
- **Next step**: one action chosen only from the student's real state (upload, fix an unreadable
  resume, find matches, start an application, open the skill-gap roadmap).
- Sections in order of importance: Resume · Best match · ATS check · Skills & gaps (wide) ·
  Interview · Applications (wide) · Assistant. Gap-free packing on tablets.
- **ATS card**:
  - adds the missing-keyword chips and a "How to improve" link to tailor the resume;
  - animated coverage meters;
  - still states that the backend gives no single ATS score (the checks are shown instead of a
    made-up number).

### Pages
- Every page inherits the system through the tokens and shared components.
- Targeted fixes:
  - resume detail header stacks on laptops;
  - Interview prep and Matches switch to two columns only from `xl` (they were cramped);
  - polished 404, 403 and placeholder pages;
  - **Admin overview** now shows real active/deactivated account counts. It used to say "the
    backend has no active status", which stopped being true after the account-security
    migration.

### Accounts (verified, no auth code changed)
Registration, validation, duplicate prevention, email verification, sign-in, sign-out and per-user
isolation all already existed and were re-verified live (see §5). Passwords use the existing
Argon2 hasher (`pwdlib`).

## 2. Files changed in this transformation
- **Frontend:**
  - `tailwind.config.js`, `index.html`, `package.json`, `package-lock.json` (name only)
  - `public/favicon.svg`
  - `src/index.css`, `src/config/brand.js`
  - `src/components/brand/BrandMark.jsx`, `src/components/ui/*`
  - `src/layouts/AppLayout.jsx`, `AuthLayout.jsx`, `ProfileMenu.jsx`
  - `src/routes/navigation.js`
  - `src/features/dashboard/DashboardPage.jsx`
  - `src/features/dashboard/components/{HeroStats (new), AtsCard, DashboardCard, ScoreRing, SkillsCard}.jsx`
  - `src/features/admin/AdminOverviewPage.jsx`
  - `src/features/system/*`
  - class-only updates in 46 page files
  - `README.md` (design system section)
  - tests: `dashboard.test.jsx` (+4 tests), `admin.test.jsx` (+1 test, +1 assertion)
- **Backend:**
  - `backend/main.py` (title, description, welcome text)
  - `backend/routes/assistant.py`, `backend/services/assistant/product_help.py`,
    `backend/services/assistant/service.py`, `backend/services/resume_parser.py` (docstring),
    `backend/data/product_docs/01_overview.md`, `07_applications_and_assistant.md`
  - Tests that quote those texts: `test_assistant_product_rag.py`,
    `test_assistant_product_rag_real_model.py`, `test_model_unavailable.py`,
    `test_ollama_provider.py`
  - No routes, schemas, models, migrations, auth or business logic changed.

## 3. AI features — tested live (test DB, local Ollama `gemma3`)

| Feature | Result |
|---|---|
| Resume parsing | Fictional test PDF parsed: name, contact, 10 skills, education, projects, experience. Readiness **90/100 Excellent** |
| ATS report | Required keywords 4/4, preferred 0/1, missing `NLP`, 7/7 checks — rendered on the dashboard |
| Job matching | 149 internships considered; best "Machine Learning Intern" 76 (Strong) without the semantic part, **88.3 "Data Science Intern"** with the semantic part |
| Semantic search | **Works** (PyTorch loads again — see §7). "analyse sales data and build dashboards" → Business/Data Analyst roles; "protect networks from attackers" → Security roles; "build mobile apps" → Android/Mobile roles |
| Skill gaps | Dashboard gap bar (have 4 / partly 0 / missing 0 required), learn-next `NLP` |
| Cover letter | Standard: 192 words in 0.1 s. **AI (Ollama): `generation_method=llm`, no warnings, 50.8 s** |
| Interview practice | Session with 4 questions; an off-topic answer scored 20/100 (correctly low) |
| Career assistant | Standard answer with 10 sources in 0.2 s; **AI-reworded answer (`llm`) with 10 sources in 12.8 s**; product question answered from the guide with the new name; privacy notice says the model runs on this server |
| Groq | **Not tested live** — no `GROQ_API_KEY` configured |

Limitation seen: "Which skills am I missing for my best match?" answers from *stored* skill-gap
recommendations, so before the student generates them it suggests doing so, rather than using the
match's missing-skill list.

## 4. Job and internship data
- Source: `backend/data/internships.json` — **180 fictional sample listings**. No source URLs,
  application links, posted dates or verification dates. They are labelled "Sample listing"
  / "sample data" in the UI.
- **Nothing is live.** De-duplication, freshness labels, source filters and admin "Mark verified"
  exist and are tested. External links appear only when an admin adds a real `source_url`.
- Legitimate feeds that need the owner's keys or terms: Adzuna, Jooble, Greenhouse and Lever job
  boards, Remotive/Arbeitnow, USAJOBS. LinkedIn, Indeed, Naukri and Internshala have no open API.
  See `FINAL_BLOCKER_CHECKLIST.md` §5.

## 5. Accounts and isolation — tested live
1. Register form validation: invalid email, weak password (live rule checklist), missing fields → clear messages.
2. Registered **Priya** → verification email (scratch outbox) → link verified, token removed from the URL.
3. Re-registering `Priya.Test@example.com` (different case) → "An account with this email already exists."
4. Registered and verified **Rahul**.
5. Wrong password → "The email or password is incorrect."; correct password → returns to the requested page.
6. Sign-out → sign-in page; protected pages redirect to `/login?next=…`.
7. Rahul's token on Priya's data: `/resumes/1`, `/resumes/1/readiness`, `/resumes/1/download`,
   `/matches/resumes/1`, `/assistant/conversations/1` → **404**; his own lists empty; no token → 401;
   student on `/admin/users` → 403. Rahul's UI shows no resumes; the admin Users page lists all three accounts.

## 6. Responsive and accessibility checks
- 375 px: no horizontal page scroll on any of the 12 student pages checked; drawer works with the
  keyboard; admin links hidden from students.
- About 1024 px laptop and desktop checked by screenshots; the cramped layouts found were fixed.
- Admin tables scroll inside their own container.
- Focus ring on every control; headings in order; decorative layers `aria-hidden`; progress bars
  carry ARIA values; reduced motion disables animations.

## 7. Checks run

| Check | Result |
|---|---|
| Frontend tests (Vitest) | **395 passed** (19 files) after the redesign (390 existing + 5 new) |
| Frontend production build | OK — pages lazy-loaded; main bundle 360 kB (115 kB gzip) |
| Lint / type check | Not configured in this project (no ESLint/TypeScript) — not run |
| Backend full suite (`career_companion_test`) | **1204 passed, 0 failed, 0 skipped, 0 errors** (34 min) — includes the 63 real-model tests that could not run this morning |
| API health | `GET /health` Healthy (test DB) |

## 8. Known issues and limitations
- Job listings are sample data; no live feed (needs an owner decision and keys).
- Groq not verified live (no key). Ollama is slow on CPU: 13–50 s per AI answer, more on the first call.
- The assistant's "missing skills" answer needs stored skill-gap recommendations first.
- No single ATS score exists in the backend; the UI shows the real checks instead.
- Web fonts load from Google Fonts. Offline, the system font is used. A strict production CSP
  must allow `fonts.googleapis.com` and `fonts.gstatic.com`, or the fonts can be self-hosted.
- No ESLint/TypeScript checks are configured.
- Outside this redesign (changes made since the morning audit, not by this work):
  - `career_companion_dev` is now at head `e1f3a5c7b9d2`;
  - a dev search index was built at 13:27;
  - a backup of the database and uploads exists from 13:14;
  - `.env` now has `EMAIL_MODE=smtp` with a valid configuration (validation only; nothing sent).
  - Dev still has **no super admin**.
- PyTorch loads again with Smart App Control still on. Code Integrity's last torch block was at
  12:02 today, most likely after cloud reputation recovered. It could be blocked again, in which
  case the keyword fallback takes over.

## 9. Run the application
```powershell
cd "<project-root>"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
```powershell
cd "<project-root>\frontend"
npm run dev
```
Open http://localhost:5173. Optional local AI: set `LLM_PROVIDER=ollama` in `.env` (Ollama running
with `gemma3`).

## 10. Deployment preparation checklist
- [ ] Create the real super admin on dev: `python -m backend.manage create-superadmin --email … --first-name … --last-name …`
- [ ] `python -m backend.manage index-status` shows the index is current after any internship change
- [ ] Send one test email to your own address: `python -m backend.manage email-check --send-test <you>` (real email — your decision)
- [ ] Production `FRONTEND_URL` and `CORS_ORIGINS`, HTTPS reverse proxy, `/docs` disabled or protected, security headers
- [ ] `npm run build` and serve `frontend/dist` statically; uvicorn without `--reload`
- [ ] Decide on job data: keep labelled samples or integrate one approved feed
- [ ] Commit this branch when satisfied (nothing is committed yet); keep the stash until then
- [ ] Re-run the full test plan on the deployment machine
