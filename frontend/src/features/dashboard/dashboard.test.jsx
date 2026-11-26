import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { validateResumeFile } from "./components/ResumeCard";
import { applicationStatus, bestMatch, greeting, percent, resumeStatus } from "./format";

// Fixtures follow the backend response schemas (backend/schemas/*.py). They exist only in this
// test file; production components never contain sample data.
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const admin = { ...student, user_id: 1, first_name: "Ada", role: "admin" };

const RESUME = { resume_id: 11, filename: "Asha_Rao_Resume.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-10T09:30:00Z" };
const OLDER = { ...RESUME, resume_id: 3, filename: "old.docx", file_type: "docx", uploaded_at: "2026-10-01T09:30:00Z" };

const internship = (id, title, company) => ({
  internship_id: id, title, company, location: "Bengaluru", work_mode: "Hybrid", domain: "Data Science",
  required_skills: [], preferred_skills: [],
});
const matchItem = (rank, score, id, title, company, extra = {}) => ({
  rank, score, label: score >= 70 ? "Strong match" : "Fair match", algorithm_version: "m1", score_before_caps: score,
  data_completeness: 1, required_skill_coverage: 0.75, components: [], matched_required_skills: ["Python", "SQL", "Pandas"],
  missing_required_skills: ["Docker"], matched_preferred_skills: [], missing_preferred_skills: [], missing_information: [],
  caps_applied: [], explanation: [], internship: internship(id, title, company), ...extra,
});
// Deliberately not sorted by score: the dashboard must pick the highest score itself.
const MATCH_RUN = {
  run_id: "5d7c1c33-35a8-4c40-9a6f-3a3b6f0b8c11", resume_id: 11, algorithm_version: "m1", created_at: "2026-11-12T08:00:00Z",
  semantic_available: true, candidates_considered: 180, filters: {},
  results: [
    matchItem(2, 64.2, 40, "Data Analyst Intern", "Cobalt Cloud"),
    matchItem(1, 82.4, 99, "Machine Learning Intern", "Foxglove Systems LLP"),
  ],
};
const SKILLS = {
  resume_id: 11,
  skills: ["Python", "SQL", "Pandas", "Machine Learning", "Git", "Statistics", "Excel", "Tableau"].map((name, i) => ({
    skill_id: i + 1, name, category: "technical", source: "resume",
  })),
};
const ATS = {
  resume_id: 11, internship: { internship_id: 99, title: "Machine Learning Intern", company: "Foxglove Systems LLP" },
  required_coverage: { present: 3, total: 4 }, preferred_coverage: { present: 1, total: 3 },
  keywords: [], missing_keywords: ["Docker"],
  checks: [
    { check: "contact_email", passed: true, detail: "An e-mail address is present." },
    { check: "contact_phone", passed: true, detail: "A phone number is present." },
    { check: "summary", passed: false, detail: "Add a short professional summary." },
    { check: "skills_section", passed: true, detail: "8 recognised skills." },
    { check: "education", passed: true, detail: "Education is present." },
    { check: "experience_or_projects", passed: true, detail: "Experience or projects are present." },
    { check: "length", passed: false, detail: "About 950 words. Consider shortening to one page." },
  ],
  suggestions: [], format_notes: [],
};
const GAP = {
  resume_id: 11, internship: { internship_id: 99, title: "Machine Learning Intern", company: "Foxglove Systems LLP", domain: "Data Science", is_active: true },
  algorithm_version: "g1", learning_plan_version: "p1",
  summary: { required_total: 4, required_matched: 2, required_partial: 1, required_missing: 1,
    preferred_total: 3, preferred_matched: 1, preferred_partial: 0, preferred_missing: 2 },
  matched: [], partial: [], missing: [], learning_order: ["Docker", "TensorFlow"], learning_plans: [],
};
const rec = (id, status) => ({ recommendation_id: id, resume_id: 11, skill_id: id, skill: `Skill ${id}`, category: null, gap_level: "missing",
  importance: "required", priority_score: 1, demand_count: 1, internship_ids: [99], related_skills: [], recommended_action: "Learn",
  learning_plan: null, learning_plan_version: null, status, completed_via: null, is_current: true, source: "match", source_run_id: null,
  top_internship: null, created_at: "2026-11-12T08:00:00Z", updated_at: "2026-11-12T08:00:00Z", started_at: null, completed_at: null });
const RECS = [rec(1, "completed"), rec(2, "in_progress"), rec(3, "pending"), rec(4, "pending"), rec(5, "dismissed")];
const PROGRESS = {
  sessions_total: 3, sessions_completed: 2, questions_answered: 14, answers_total: 17, average_score: 68.4,
  by_category: { technical: 72.5, behavioral: 58.1, project: 70 }, by_skill: {}, retry_improvement: {}, trend: [],
};
const SUMMARY = {
  generated_at: "2026-11-16T10:00:00Z", saved_internships: 2, total_applications: 6, by_status: { APPLIED: 3, SHORTLISTED: 1 },
  submitted_applications: 5, selected: 1, rejected: 1, interviews_scheduled: 2, upcoming_interviews: 1,
  next_interviews: [{ interview_id: 5, application_id: 21, company_name: "Cobalt Cloud", title: "Data Analyst Intern",
    round_number: 1, interview_type: "technical", mode: "online", scheduled_at: "2026-11-20T05:30:00Z" }],
  pending_reminders: 1, overdue_reminders: 0, completed_reminders: 0, success_rate: 0.2, decision_rate: 0.4, interview_rate: 0.4,
  formulas: {}, recent_activity: [],
};
const application = (id, title, company, status) => ({
  application_id: id, source: "internal", internship_id: id, company_name: company, title, application_url: null, external_reference: null,
  domain: null, location: null, work_mode: null, status, applied_at: null, status_changed_at: null, notes: null, contact_name: null,
  contact_email: null, resume_document_id: null, cover_letter_document_id: null, internship_active: true, deadline_passed: false,
  interview_count: 0, next_interview: null, pending_reminders: 0, next_reminder: null, deleted_at: null,
  created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-14T00:00:00Z",
});
const RECENT = { total: 2, skip: 0, limit: 5, items: [
  application(21, "Data Analyst Intern", "Cobalt Cloud", "INTERVIEW_SCHEDULED"),
  application(22, "ML Intern", "Nimbus Networks LLP", "REJECTED"),
] };
const CONVERSATIONS = { total: 1, skip: 0, limit: 3, items: [{ conversation_id: 4, title: "Which skills should I learn first?",
  resume_id: 11, message_count: 4, last_message_at: "2026-11-15T12:00:00Z", created_at: "2026-11-15T11:00:00Z", updated_at: "2026-11-15T12:00:00Z" }] };

// Records every request path so tests can assert what was (not) called.
function recordRequests() {
  const seen = [];
  server.events.on("request:start", ({ request }) => seen.push(`${request.method} ${new URL(request.url).pathname}`));
  return seen;
}

function fullData() {
  server.use(
    http.get("/api/resumes/", () => HttpResponse.json([RESUME, OLDER])),
    http.get("/api/resumes/11/skills", () => HttpResponse.json(SKILLS)),
    http.get("/api/matches/resumes/11", () => HttpResponse.json(MATCH_RUN)),
    http.get("/api/documents/resumes/11/internships/99/ats-report", () => HttpResponse.json(ATS)),
    http.get("/api/skill-gaps/resumes/11/internships/99", () => HttpResponse.json(GAP)),
    http.get("/api/skill-gaps", () => HttpResponse.json(RECS)),
    http.get("/api/interviews/progress", () => HttpResponse.json(PROGRESS)),
    http.get("/api/applications/dashboard", () => HttpResponse.json(SUMMARY)),
    http.get("/api/applications", () => HttpResponse.json(RECENT)),
    http.get("/api/assistant/conversations", () => HttpResponse.json(CONVERSATIONS)),
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderDashboard(user = student, path = "/") {
  setAccessToken("access-token"); // a signed-in session (F0 keeps it in memory)
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={{ initialUser: user, restoreSession: false }} />
      <LocationProbe />
    </MemoryRouter>,
  );
}

const card = (title) => screen.getByRole("heading", { level: 2, name: title }).closest("section");
const findCard = async (title) => (await screen.findByRole("heading", { level: 2, name: title })).closest("section");

// ================================================================================================
describe("Dashboard: new student (empty data)", () => {
  it("greets the student and shows an empty state in every section without calling resume-only APIs", async () => {
    const seen = recordRequests();
    renderDashboard();
    expect(await screen.findByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening), Asha$/ })).toBeInTheDocument();

    expect(await within(await findCard("Resume")).findByText("No resume yet")).toBeInTheDocument();
    expect(within(card("Resume")).getByRole("button", { name: "Upload resume" })).toBeInTheDocument();
    expect(within(card("Best internship match")).getByText("Upload a resume first")).toBeInTheDocument();
    expect(within(card("ATS check")).getByText("Not available yet")).toBeInTheDocument();
    expect(within(card("Skills & gaps")).getByText("Not available yet")).toBeInTheDocument();
    expect(await within(card("Interview preparation")).findByText("No practice sessions yet")).toBeInTheDocument();
    expect(await within(card("Applications")).findByText("No applications yet")).toBeInTheDocument();
    expect(await within(card("AI assistants")).findByText("No conversations yet.")).toBeInTheDocument();

    await waitFor(() => expect(seen).toContain("GET /api/assistant/conversations"));
    expect(seen.some((r) => /matches|ats-report|skill-gaps|skills/.test(r))).toBe(false);
  });
});

// ================================================================================================
describe("Dashboard: student with data", () => {
  it("shows the latest resume, best match, ATS checks, skills, interviews, applications and assistant", async () => {
    fullData();
    renderDashboard();

    const resume = await findCard("Resume");
    expect(await within(resume).findByText("Asha_Rao_Resume.pdf")).toBeInTheDocument();
    expect(within(resume).getByText("Parsed")).toBeInTheDocument();
    expect(within(resume).getByText(/2 resumes on file/)).toBeInTheDocument();

    // Highest score wins even though the API listed it second.
    const match = card("Best internship match");
    expect(await within(match).findByText("Machine Learning Intern")).toBeInTheDocument();
    expect(within(match).getByText("Foxglove Systems LLP")).toBeInTheDocument();
    expect(within(match).getByText("82%")).toBeInTheDocument();
    expect(within(match).getByText("Strong match")).toBeInTheDocument();
    expect(within(match).getByRole("list", { name: "Missing required skills" })).toHaveTextContent("Docker");

    const ats = card("ATS check");
    const checks = await within(ats).findByRole("progressbar", { name: "Resume checks passed" });
    expect(checks).toHaveAttribute("aria-valuenow", "5");
    expect(checks).toHaveAttribute("aria-valuemax", "7");
    expect(within(ats).getByRole("progressbar", { name: "Required keywords found" })).toHaveAttribute("aria-valuenow", "3");
    expect(within(ats).getByText("Add a short professional summary.")).toBeInTheDocument();
    // The compatibility score is never shown as an ATS score.
    expect(within(ats).queryByText(/82/)).not.toBeInTheDocument();
    expect(within(ats).getByText("not provided by the backend")).toBeInTheDocument();

    const skills = card("Skills & gaps");
    expect(await within(skills).findByText("8")).toBeInTheDocument();
    expect(within(skills).getByText("+2 more")).toBeInTheDocument();
    const gapList = await within(skills).findByRole("list", { name: "Required skill gap" });
    expect(gapList).toHaveTextContent("Have: 2");
    expect(gapList).toHaveTextContent("Partly: 1");
    expect(gapList).toHaveTextContent("Missing: 1");
    expect(within(skills).getByText("Docker, TensorFlow")).toBeInTheDocument();
    expect(await within(skills).findByText(/Learning plan:/)).toHaveTextContent("1 done · 1 in progress · 2 to start");

    const interviews = card("Interview preparation");
    expect(await within(interviews).findByText("2/3")).toBeInTheDocument();
    expect(within(interviews).getByText("14")).toBeInTheDocument();
    expect(within(interviews).getByText(/average practice score/)).toBeInTheDocument();
    expect(within(interviews).getByText("Behavioral")).toBeInTheDocument(); // weakest category

    const apps = card("Applications");
    expect(await within(apps).findByText("6")).toBeInTheDocument();
    expect(within(apps).getByText(/Next interview:/)).toHaveTextContent("Cobalt Cloud");
    const recent = within(apps).getByRole("list", { name: "Recent applications" });
    expect(within(recent).getByText("Interview scheduled")).toBeInTheDocument();
    expect(within(recent).getByText("Rejected")).toBeInTheDocument();

    expect(await within(card("AI assistants")).findByText("Which skills should I learn first?")).toBeInTheDocument();
    expect(within(card("AI assistants")).getByRole("link", { name: /Ask the Application Assistant/ })).toHaveAttribute("href", "/assistant");
    expect(within(card("AI assistants")).getByRole("link", { name: "Prepare for interviews" })).toHaveAttribute("href", "/interview-assistant");
  });

  it("summarises the skill gap: next recommendation, missing counts and links", async () => {
    fullData();
    renderDashboard();
    const skills = await findCard("Skills & gaps");
    // RECS: #2 is in progress, so it is the next thing to learn (backend priority order otherwise).
    expect(await within(skills).findByText(/Next to learn:/)).toHaveTextContent("Next to learn: Skill 2 (in progress)");
    expect(await within(skills).findByText(/Preferred skills missing:/)).toHaveTextContent("Preferred skills missing: 2 of 3");
    expect(within(skills).getByRole("link", { name: "See this skill gap" })).toHaveAttribute("href", "/skill-gaps/internships/99");
    expect(within(skills).getByRole("link", { name: /View all/ })).toHaveAttribute("href", "/skill-gaps");
  });

  it("shows loading placeholders while sections load", async () => {
    server.use(http.get("/api/resumes/", async () => {
      await delay(200);
      return HttpResponse.json([]);
    }));
    renderDashboard();
    expect(await screen.findByText("Loading your resume…")).toBeInTheDocument();
    expect(await within(card("Resume")).findByText("No resume yet")).toBeInTheDocument();
  });

  it("uses the latest successfully parsed resume when the newest one failed", async () => {
    const seen = recordRequests();
    fullData();
    server.use(http.get("/api/resumes/", () =>
      HttpResponse.json([{ ...RESUME, resume_id: 30, filename: "broken.pdf", status: "failed" }, RESUME])));
    renderDashboard();
    const resume = await findCard("Resume");
    expect(await within(resume).findByText("broken.pdf")).toBeInTheDocument();
    expect(within(resume).getByText(/Matching and skill gaps use/)).toHaveTextContent("Asha_Rao_Resume.pdf");
    expect(await within(card("Best internship match")).findByText("Machine Learning Intern")).toBeInTheDocument();
    expect(seen).toContain("GET /api/matches/resumes/11");
    expect(seen.some((r) => r.includes("/30"))).toBe(false);
  });

  it("explains a resume that could not be parsed and skips resume-based sections", async () => {
    const seen = recordRequests();
    server.use(http.get("/api/resumes/", () => HttpResponse.json([{ ...RESUME, status: "failed" }])));
    renderDashboard();
    expect(await within(await findCard("Resume")).findByText("Parsing failed")).toBeInTheDocument();
    expect(within(card("Best internship match")).getByText("Resume not ready")).toBeInTheDocument();
    await waitFor(() => expect(seen).toContain("GET /api/resumes/"));
    expect(seen.some((r) => /matches|ats-report|skill-gaps|\/skills/.test(r))).toBe(false);
  });
});

// ================================================================================================
describe("Dashboard: failures and retries", () => {
  it("isolates a failing section and recovers with Try again", async () => {
    let calls = 0;
    server.use(http.get("/api/applications/dashboard", () => {
      calls += 1;
      return calls === 1 ? HttpResponse.json({ detail: "boom" }, { status: 500 }) : HttpResponse.json(SUMMARY);
    }));
    renderDashboard();
    const apps = await findCard("Applications");
    const alert = await within(apps).findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load application totals.");
    expect(alert).toHaveTextContent("boom");
    // Other sections are unaffected.
    expect(await within(card("Resume")).findByText("No resume yet")).toBeInTheDocument();

    await userEvent.click(within(apps).getByRole("button", { name: "Try again" }));
    expect(await within(apps).findByText("Upcoming interviews")).toBeInTheDocument();
    expect(within(apps).queryByRole("alert")).not.toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("reports network failures in plain language", async () => {
    server.use(http.get("/api/interviews/progress", () => HttpResponse.error()));
    renderDashboard();
    const alert = await within(await findCard("Interview preparation")).findByRole("alert");
    expect(alert).toHaveTextContent("Cannot reach the server");
  });

  it("shows an error state when the ATS check cannot be produced", async () => {
    fullData();
    server.use(http.get("/api/documents/resumes/11/internships/99/ats-report", () =>
      HttpResponse.json({ detail: "Resume has no usable content" }, { status: 422 })));
    renderDashboard();
    const alert = await within(await findCard("ATS check")).findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load the ATS check.");
    expect(within(card("ATS check")).getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("sends the student to sign in when the session has expired", async () => {
    // No valid access token and no refresh token: the API client cannot refresh, so it signs out.
    server.use(http.get("/api/resumes/", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })));
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    server.use(http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })));
    renderDashboard();
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByTestId("location").textContent).toBe("/login?next=%2F");
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
  });
});

// ================================================================================================
describe("Dashboard: matching", () => {
  it("offers to run matching when none has run, then shows the best match", async () => {
    const posted = [];
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
      http.get("/api/resumes/11/skills", () => HttpResponse.json(SKILLS)),
      http.get("/api/skill-gaps", () => HttpResponse.json([])),
      http.get("/api/matches/resumes/11", () => HttpResponse.json({ detail: "No matching results yet for this resume" }, { status: 404 })),
      http.post("/api/matches/resumes/11", () => {
        posted.push(true);
        return HttpResponse.json(MATCH_RUN, { status: 201 });
      }),
      http.get("/api/documents/resumes/11/internships/99/ats-report", () => HttpResponse.json(ATS)),
      http.get("/api/skill-gaps/resumes/11/internships/99", () => HttpResponse.json(GAP)),
    );
    renderDashboard();
    const match = await findCard("Best internship match");
    expect(await within(match).findByText("No matches yet")).toBeInTheDocument();
    expect(within(card("ATS check")).getByText(/Run internship matching first/)).toBeInTheDocument();

    await userEvent.click(within(match).getByRole("button", { name: "Find my matches" }));
    expect(await within(match).findByText("Machine Learning Intern")).toBeInTheDocument();
    expect(posted).toHaveLength(1);
    // The ATS check and skill gap follow the new best match.
    expect(await within(card("ATS check")).findByRole("progressbar", { name: "Resume checks passed" })).toBeInTheDocument();
    expect(await within(card("Skills & gaps")).findByRole("list", { name: "Required skill gap" })).toBeInTheDocument();
  });

  it("shows why matching could not run", async () => {
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
      http.get("/api/resumes/11/skills", () => HttpResponse.json({ resume_id: 11, skills: [] })),
      http.get("/api/skill-gaps", () => HttpResponse.json([])),
      http.get("/api/matches/resumes/11", () => HttpResponse.json({ detail: "No matching results yet for this resume" }, { status: 404 })),
      http.post("/api/matches/resumes/11", () =>
        HttpResponse.json({ detail: "The resume has no recognised skills to match against." }, { status: 422 })),
    );
    renderDashboard();
    const match = await findCard("Best internship match");
    await userEvent.click(await within(match).findByRole("button", { name: "Find my matches" }));
    expect(await within(match).findByRole("alert")).toHaveTextContent("The resume has no recognised skills to match against.");
  });
});

// ================================================================================================
describe("Dashboard: resume upload", () => {
  it("rejects unsupported and oversized files before uploading", async () => {
    const seen = recordRequests();
    renderDashboard();
    const resume = await findCard("Resume");
    await within(resume).findByText("No resume yet");
    const user = userEvent.setup({ applyAccept: false });
    const input = screen.getByTestId("resume-file-input");

    await user.upload(input, new File(["hello"], "notes.txt", { type: "text/plain" }));
    expect(within(resume).getByRole("alert")).toHaveTextContent("Upload a PDF, Word (.docx) or OpenDocument (.odt) file.");

    const big = new File(["x"], "big.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 5 * 1024 * 1024 + 1 });
    await user.upload(input, big);
    expect(within(resume).getByRole("alert")).toHaveTextContent("Resume files must be 5 MB or smaller.");
    expect(seen.some((r) => r.startsWith("POST /api/resumes/upload"))).toBe(false);
  });

  it("uploads a PDF as multipart form data and refreshes the dashboard", async () => {
    // jsdom's File loses its name when MSW re-serialises the body with Node's undici (it arrives as
    // "blob"), so the filename is asserted where the app sets it: FormData.append(field, file, name).
    const append = vi.spyOn(globalThis.FormData.prototype, "append");
    let part = null;
    let listCalls = 0;
    server.use(
      http.get("/api/resumes/", () => {
        listCalls += 1;
        return HttpResponse.json(listCalls === 1 ? [] : [RESUME]);
      }),
      http.post("/api/resumes/upload", async ({ request }) => {
        const file = (await request.formData()).get("file");
        part = { type: file.type, text: await file.text() };
        return HttpResponse.json({ ...RESUME, extracted_data: {}, normalized_skills: [] }, { status: 201 });
      }),
      http.get("/api/resumes/11/skills", () => HttpResponse.json(SKILLS)),
      http.get("/api/skill-gaps", () => HttpResponse.json([])),
      http.get("/api/matches/resumes/11", () => HttpResponse.json({ detail: "No matching results yet for this resume" }, { status: 404 })),
    );
    renderDashboard();
    const resume = await findCard("Resume");
    await within(resume).findByText("No resume yet");
    await userEvent.upload(screen.getByTestId("resume-file-input"), new File(["%PDF-1.7"], "Asha_Rao_Resume.pdf", { type: "application/pdf" }));

    expect(await within(resume).findByText("Asha_Rao_Resume.pdf")).toBeInTheDocument();
    expect(append).toHaveBeenCalledWith("file", expect.any(File), "Asha_Rao_Resume.pdf");
    expect(part).toEqual({ type: "application/pdf", text: "%PDF-1.7" });
    expect(await screen.findByText("Asha_Rao_Resume.pdf uploaded and parsed.")).toBeInTheDocument(); // toast
    expect(await within(card("Best internship match")).findByText("No matches yet")).toBeInTheDocument();
  });

  it("shows the backend's reason when an upload is rejected", async () => {
    server.use(http.post("/api/resumes/upload", () => HttpResponse.json({ detail: "Invalid PDF file content." }, { status: 400 })));
    renderDashboard();
    const resume = await findCard("Resume");
    await within(resume).findByText("No resume yet");
    await userEvent.upload(screen.getByTestId("resume-file-input"), new File(["not a pdf"], "cv.pdf", { type: "application/pdf" }));
    expect(await within(resume).findByRole("alert")).toHaveTextContent("Invalid PDF file content.");
  });
});

// ================================================================================================
describe("App shell: navigation, profile menu and roles", () => {
  it("never shows admin links to students, but does to administrators", async () => {
    const { unmount } = renderDashboard(student);
    await screen.findByRole("navigation", { name: "Main" });
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Search index" })).not.toBeInTheDocument();
    unmount();

    renderDashboard(admin);
    expect(await screen.findByRole("link", { name: "Search index" })).toHaveAttribute("href", "/admin/index");
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("marks the current page in the navigation", async () => {
    renderDashboard(student, "/matches");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Matches" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });

  it("opens the mobile navigation drawer, closes it with Escape and returns focus", async () => {
    renderDashboard();
    const user = userEvent.setup();
    const toggle = await screen.findByRole("button", { name: "Open navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);

    const drawer = screen.getByRole("dialog", { name: "Navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(drawer).getByRole("link", { name: "Applications" })).toBeInTheDocument();
    await waitFor(() => expect(drawer.contains(document.activeElement)).toBe(true));

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
  });

  it("closes the mobile drawer after choosing a page", async () => {
    renderDashboard();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open navigation" }));
    await user.click(within(screen.getByRole("dialog", { name: "Navigation" })).getByRole("link", { name: "Applications" }));
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
    expect(screen.getByTestId("location").textContent).toBe("/applications");
  });

  it("supports the profile menu with the keyboard", async () => {
    renderDashboard();
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: /account menu/ });
    expect(button).toHaveAttribute("aria-haspopup", "menu");
    button.focus();
    await user.keyboard("{ArrowDown}");

    const menu = screen.getByRole("menu", { name: "Account" });
    expect(within(menu).getByText("asha@example.com")).toBeInTheDocument();
    await waitFor(() => expect(within(menu).getByRole("menuitem", { name: "Profile" })).toHaveFocus());
    await user.keyboard("{ArrowDown}");
    expect(within(menu).getByRole("menuitem", { name: "Sign out" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(within(menu).getByRole("menuitem", { name: "Profile" })).toHaveFocus(); // wraps
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("opens the profile page from the menu", async () => {
    renderDashboard();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /account menu/ }));
    await user.click(screen.getByRole("menuitem", { name: "Profile" }));
    expect(screen.getByTestId("location").textContent).toBe("/profile");
    expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
  });

  it("offers a skip link to the main content", async () => {
    renderDashboard();
    expect(await screen.findByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main-content");
    expect(document.getElementById("main-content")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Dashboard helpers", () => {
  it("picks the best match by score, then rank", () => {
    expect(bestMatch(MATCH_RUN).internship.internship_id).toBe(99);
    expect(bestMatch({ results: [{ score: 70, rank: 2, id: "b" }, { score: 70, rank: 1, id: "a" }] }).id).toBe("a");
    expect(bestMatch({ results: [] })).toBeNull();
    expect(bestMatch(null)).toBeNull();
  });

  it("labels statuses and computes percentages", () => {
    expect(applicationStatus("INTERVIEW_SCHEDULED")).toEqual({ label: "Interview scheduled", tone: "warning" });
    expect(applicationStatus("SOMETHING_NEW").label).toBe("Something new");
    expect(resumeStatus("completed").label).toBe("Parsed");
    expect(percent(3, 4)).toBe(75);
    expect(percent(1, 0)).toBe(0);
  });

  it("greets by time of day", () => {
    expect(greeting(new Date(2026, 0, 1, 9))).toBe("Good morning");
    expect(greeting(new Date(2026, 0, 1, 14))).toBe("Good afternoon");
    expect(greeting(new Date(2026, 0, 1, 20))).toBe("Good evening");
  });

  it("validates resume files like the backend", () => {
    expect(validateResumeFile(new File(["x"], "CV.PDF"))).toBeNull();
    expect(validateResumeFile(new File(["x"], "cv.docx"))).toBeNull();
    expect(validateResumeFile(new File(["x"], "cv.doc"))).toMatch(/PDF, Word .* or OpenDocument/);
    expect(validateResumeFile(new File([], "cv.pdf"))).toBe("That file is empty.");
    expect(validateResumeFile(null)).toBe("Choose a file to upload.");
  });
});

// ================================================================================================
describe("CareerNova redesign: hero and branding", () => {
  it("shows hero numbers only from real responses and the next step for the student's state", async () => {
    fullData();
    renderDashboard();
    const stats = await screen.findByRole("list", { name: "Your progress at a glance" });
    // readiness from GET /resumes/11/readiness (default handler: 78), best match 82, applications 6, interviews 68.4
    await waitFor(() => expect(stats).toHaveTextContent("78/100"));
    // The tile names the scored version, so the number can be traced to a resume.
    expect(within(stats).getByRole("link", { name: /Resume readiness/ })).toHaveTextContent("Good · V2 Asha_Rao_CV.pdf");
    await waitFor(() => expect(stats).toHaveTextContent("82%"));
    expect(stats).toHaveTextContent("6");
    expect(stats).toHaveTextContent("68/100");
    expect(within(stats).getByRole("link", { name: /Best match/ })).toHaveAttribute("href", "/matches");
    // 6 applications exist, so the next step is the skill-gap roadmap for the best match.
    expect(await screen.findByText(/Close your skill gap/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open roadmap" })).toHaveAttribute("href", "/skill-gaps/internships/99");
  });

  it("shows dashes, not invented numbers, for a new student and asks for a resume first", async () => {
    renderDashboard();
    const stats = await screen.findByRole("list", { name: "Your progress at a glance" });
    expect(within(stats).getByText("No parsed resume yet")).toBeInTheDocument();
    expect(within(stats).getByText("Needs a parsed resume")).toBeInTheDocument();
    expect(await screen.findByText(/Upload your resume to unlock matches, ATS checks/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload resume" })).toHaveAttribute("href", "/resumes");
  });

  it("uses the CareerNova AI name in the sidebar and the tab title", async () => {
    renderDashboard();
    await screen.findByRole("navigation", { name: "Main" });
    expect(screen.getAllByText("CareerNova AI").length).toBeGreaterThan(0);
    await waitFor(() => expect(document.title).toBe("Dashboard · CareerNova AI"));
    expect(screen.queryByText(/AI Career Companion/)).not.toBeInTheDocument();
  });
});

describe("App shell: page transitions", () => {
  it("keys the page fade by top-level section so in-section URL changes keep page state", async () => {
    const { sectionKey } = await import("../../layouts/AppLayout");
    expect(sectionKey("/")).toBe("/");
    expect(sectionKey("/assistant")).toBe("/assistant");
    expect(sectionKey("/assistant/12")).toBe("/assistant");
    expect(sectionKey("/internships/5")).toBe("/internships");
    expect(sectionKey("/admin")).toBe("/admin");
    expect(sectionKey("/admin/users")).toBe("/admin/users");
    expect(sectionKey("/admin/internships/7/edit")).toBe("/admin/internships");
  });
});
