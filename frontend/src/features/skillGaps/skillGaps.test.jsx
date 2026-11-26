import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { completedViaLabel, countByStatus, nextRecommendation } from "./gapFormat";

// Fictional fixtures shaped like backend/schemas/skill_gap_schema.py.
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const RESUME = { resume_id: 11, filename: "Asha_Rao_Resume.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-10T00:00:00Z" };
const SKILLS = { resume_id: 11, skills: [{ skill_id: 1, name: "Python", category: "programming_language", source: "skills" }, { skill_id: 2, name: "SQL", category: "database", source: "skills" }] };
const CURATED = { skill: "Docker", curated: true, level: "intermediate", estimated_hours: 25, prerequisites: ["Linux"], missing_prerequisites: ["Linux"], topics: ["Images and containers", "Dockerfiles", "Compose"] };
const GENERIC = { skill: "Kafka", curated: false, level: null, estimated_hours: null, prerequisites: [], missing_prerequisites: [], topics: ["Core concepts of Kafka", "Hands-on practice with Kafka"] };
const rec = (id, skill, extra = {}) => ({
  recommendation_id: id, resume_id: 11, skill_id: id, skill, category: "tool", gap_level: "missing", importance: "required",
  priority_score: 90 - id * 10, demand_count: 3, internship_ids: [99], related_skills: [], recommended_action: `Learn ${skill}: required by 3 of the 5 internships analysed.`,
  learning_plan: CURATED, learning_plan_version: "p1", status: "pending", completed_via: null, is_current: true, source: "match_run",
  source_run_id: null, top_internship: { internship_id: 99, title: "Machine Learning Intern", company: "Example Labs", domain: "Data Science", is_active: true },
  created_at: "2026-11-12T00:00:00Z", updated_at: "2026-11-12T00:00:00Z", started_at: null, completed_at: null, ...extra,
});
const RECS = [
  rec(1, "Docker", { related_skills: [{ skill: "Linux", reason: "Docker builds on Linux basics." }] }),
  rec(2, "Kafka", { gap_level: "partial", importance: "preferred", learning_plan: GENERIC, status: "in_progress", started_at: "2026-11-13T00:00:00Z" }),
  rec(3, "Tableau", { status: "completed", completed_via: "resume", completed_at: "2026-11-14T00:00:00Z" }),
  rec(4, "Excel", { status: "dismissed" }),
];
const GAP = {
  resume_id: 11, internship: { internship_id: 99, title: "Machine Learning Intern", company: "Example Labs", domain: "Data Science", is_active: true },
  algorithm_version: "g1", learning_plan_version: "p1",
  summary: { required_total: 5, required_matched: 3, required_partial: 1, required_missing: 1, preferred_total: 2, preferred_matched: 0, preferred_partial: 0, preferred_missing: 2 },
  matched: [{ skill: "Python", category: null, importance: "required", status: "matched", related_skills: [] }],
  partial: [{ skill: "Deep Learning", category: null, importance: "required", status: "partial", related_skills: [{ skill: "Machine Learning", reason: "You know Machine Learning." }] }],
  missing: [{ skill: "Docker", category: null, importance: "required", status: "missing", related_skills: [] }],
  learning_order: ["Docker", "Deep Learning"],
  learning_plans: [{ skill: "Docker", category: null, importance: "required", status: "missing", related_skills: [], plan: CURATED }],
};
const MATCH = {
  rank: null, score: 71.2, label: "Strong match", algorithm_version: "m1", score_before_caps: 71.2, data_completeness: 1, required_skill_coverage: 0.6,
  components: [], matched_required_skills: ["Python"], missing_required_skills: ["Docker"], matched_preferred_skills: [], missing_preferred_skills: [],
  missing_information: [], caps_applied: [], explanation: [], internship: GAP.internship,
};

const ROLES = [{ slug: "java-developer", title: "Java Developer" }, { slug: "frontend-developer", title: "Frontend Developer" }];
const CURRENT = [
  { group: "Programming languages", skills: [{ skill: "Java", status: "listed", where: [] }, { skill: "Python", status: "demonstrated", where: ["Sales Report"] }] },
  { group: "Databases", skills: [{ skill: "SQL", status: "demonstrated", where: ["Sales Report"] }] },
];
const ANALYSIS_BASE = { resume: { resume_id: 11, filename: "Asha_Rao_Resume.pdf", label: null }, current_skills: CURRENT, roles: ROLES, counts: { demonstrated: 2, listed: 1 } };
const GENERAL = { ...ANALYSIS_BASE, mode: "general", role: null, requirements: [], gaps: [], learning_priorities: [], note: "General analysis - choose a target role to see the skills that role needs and your gaps." };
const JAVA = {
  ...ANALYSIS_BASE, mode: "role", role: { slug: "java-developer", title: "Java Developer", summary: "Builds backend services in Java." },
  fit: { score: 42, algorithm: "r1", basis: "75% core-skill coverage + 25% advanced-skill coverage (skills found in your resume)", core_found: 2, core_total: 4, core_demonstrated: 1, advanced_found: 0, advanced_total: 2 },
  requirements: [
    { skill: "Java", importance: "core", status: "listed", where: [], group: "Programming languages" },
    { skill: "Spring Boot", importance: "core", status: "not_found", where: [], group: "Backend" },
  ],
  gaps: [
    { skill: "Spring Boot", importance: "core", status: "not_found", headline: "Not found in your resume", priority: "high", why: "Spring Boot is a core skill for a Java Developer.", learn: "Roadmap stage \"Frameworks\": build REST APIs.", practice: "Build a REST API for a library.", resume_tip: "After you have genuinely built the task, add Spring Boot to your Skills section." },
    { skill: "Java", importance: "core", status: "listed", headline: "Listed but not demonstrated", priority: "medium", why: "Java is a core skill for a Java Developer.", learn: "Roadmap stage \"Core Java\": OOP and collections.", practice: "Write a CLI inventory tool.", resume_tip: "Your resume lists Java but no project or experience shows it." },
  ],
  learning_priorities: ["Spring Boot", "Java"], resume_advice: [],
  note: "\"Not found in your resume\" means the resume does not mention the skill - it does not mean you lack it.",
};

function Probe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="location">{location.pathname + location.search}</output>
      <button type="button" onClick={() => navigate(-1)}>
        Browser back
      </button>
    </>
  );
}

function renderAt(path) {
  setAccessToken("access-token");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={{ initialUser: student, restoreSession: false }} />
      <Probe />
    </MemoryRouter>,
  );
}
const location = () => screen.getByTestId("location").textContent;

function backend({ recs = RECS } = {}) {
  const calls = [];
  server.events.on("request:start", ({ request }) => calls.push(`${request.method} ${new URL(request.url).pathname}${new URL(request.url).search}`));
  server.use(
    http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
    http.get("/api/resumes/11/skills", () => HttpResponse.json(SKILLS)),
    http.get("/api/skill-gaps", () => HttpResponse.json(recs)),
    http.get("/api/skill-gaps/role-analysis", ({ request }) =>
      HttpResponse.json(new URL(request.url).searchParams.get("role") === "java-developer" ? JAVA : GENERAL),
    ),
  );
  return calls;
}

const recList = () => screen.getByRole("list", { name: "Learning recommendations" });
const card = (skill) => within(recList()).getByRole("heading", { name: new RegExp(skill) }).closest("article");

// ================================================================================================
describe("Skill gaps page", () => {
  it("shows the student's skills and the backend's open recommendations in priority order", async () => {
    const calls = backend();
    renderAt("/skill-gaps");
    expect(await screen.findByRole("list", { name: "Skills you have" })).toHaveTextContent("PythonSQL");
    const list = await screen.findByRole("list", { name: "Learning recommendations" });
    const titles = within(list).getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual(["#1Docker", "#2Kafka"]); // "To learn" filter: pending + in progress
    expect(calls).toContain("GET /api/skill-gaps?resume_id=11");

    const docker = card("Docker");
    expect(within(docker).getByText("Missing")).toBeInTheDocument();
    expect(within(docker).getByText("Required")).toBeInTheDocument();
    expect(within(docker).getByText("80")).toBeInTheDocument(); // priority_score from backend
    expect(within(docker).getByText(/required by 3 of the 5 internships analysed/)).toBeInTheDocument();
    expect(within(docker).getByRole("link", { name: "Machine Learning Intern at Example Labs" })).toHaveAttribute("href", "/internships/99");
    expect(within(docker).getByRole("list", { name: "Related skills for Docker" })).toHaveTextContent("Linux: Docker builds on Linux basics.");
    expect(within(card("Kafka")).getByText("Partly there")).toBeInTheDocument();
    // Completed (Tableau) and dismissed (Excel) skills are not counted as open gaps.
    expect(screen.getByText("1 missing and 1 partly-covered skills to learn · 1 completed")).toBeInTheDocument();
  });

  it("shows learning plans exactly as provided, with no invented resources", async () => {
    backend();
    renderAt("/skill-gaps");
    const user = userEvent.setup();
    await screen.findByRole("list", { name: "Learning recommendations" });
    const docker = card("Docker");
    await user.click(within(docker).getByRole("button", { name: /Show learning plan for Docker/ }));
    expect(within(docker).getByText("About 25 hours")).toBeInTheDocument();
    expect(within(docker).getByText("Intermediate")).toBeInTheDocument();
    expect(within(docker).getByText(/Learn first:/)).toHaveTextContent("Linux");
    expect(within(docker).getByText("Dockerfiles")).toBeInTheDocument();
    expect(within(docker).queryByRole("link", { name: /http/ })).not.toBeInTheDocument();

    const kafka = card("Kafka");
    await user.click(within(kafka).getByRole("button", { name: /Show learning plan for Kafka/ }));
    expect(within(kafka).getByText("General outline")).toBeInTheDocument();
    expect(within(kafka).getByText(/No curated plan exists for this skill yet/)).toBeInTheDocument();
    expect(within(kafka).queryByText(/hours/)).not.toBeInTheDocument();
  });

  it("persists a status change once and shows the saved state", async () => {
    backend();
    const patches = [];
    // The response is held until the test releases it, so the second click is guaranteed to
    // happen while the first save is still in flight (no timing assumptions).
    let release;
    const held = new Promise((resolve) => {
      release = resolve;
    });
    server.use(http.patch("/api/skill-gaps/:id", async ({ params, request }) => {
      patches.push({ id: params.id, body: await request.json() });
      await held;
      return HttpResponse.json({ ...RECS[0], status: "in_progress", started_at: "2026-11-16T00:00:00Z" });
    }));
    renderAt("/skill-gaps");
    const user = userEvent.setup();
    await screen.findByRole("list", { name: "Learning recommendations" });
    const group = within(card("Docker")).getByRole("group", { name: "Progress for Docker" });
    await user.click(within(group).getByRole("button", { name: "In progress" }));
    expect(within(group).getByRole("button", { name: "Saving…" })).toBeDisabled();
    await user.click(within(group).getByRole("button", { name: "Completed" })); // ignored while saving
    await waitFor(() => expect(patches).toHaveLength(1));
    release();

    await waitFor(() => expect(within(group).getByRole("button", { name: "In progress" })).toHaveAttribute("aria-pressed", "true"));
    expect(patches).toEqual([{ id: "1", body: { status: "in_progress" } }]);
    expect(within(card("Docker")).getAllByText("In progress").length).toBeGreaterThan(0);
    expect(within(card("Docker")).getByText(/Started/)).toBeInTheDocument();
  });

  it("keeps the previous status and explains a failed update", async () => {
    backend();
    server.use(http.patch("/api/skill-gaps/:id", () => HttpResponse.json({ detail: "Recommendation not found" }, { status: 404 })));
    renderAt("/skill-gaps");
    const user = userEvent.setup();
    await screen.findByRole("list", { name: "Learning recommendations" });
    const docker = card("Docker");
    await user.click(within(docker).getByRole("button", { name: "Completed" }));
    expect(await within(docker).findByRole("alert")).toHaveTextContent("Couldn't update progress. Recommendation not found");
    expect(within(docker).getByRole("button", { name: "To do" })).toHaveAttribute("aria-pressed", "true");
  });

  it("filters by status in the URL and supports Back", async () => {
    backend();
    renderAt("/skill-gaps");
    const user = userEvent.setup();
    await screen.findByRole("list", { name: "Learning recommendations" });
    await user.click(screen.getByRole("button", { name: /^Completed 1$/ }));
    await waitFor(() => expect(location()).toBe("/skill-gaps?status=completed"));
    expect(within(recList()).getAllByRole("article")).toHaveLength(1);
    expect(within(card("Tableau")).getByText(/Detected on your resume/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Dismissed 1$/ }));
    await waitFor(() => expect(location()).toBe("/skill-gaps?status=dismissed"));
    await user.click(screen.getByRole("button", { name: "Browser back" }));
    await waitFor(() => expect(location()).toBe("/skill-gaps?status=completed"));
    expect(screen.getByRole("button", { name: /^Completed 1$/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("generates recommendations from the latest matches and shows what changed", async () => {
    backend({ recs: [] });
    const bodies = [];
    server.use(http.post("/api/skill-gaps/resumes/11", async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json({
        resume_id: 11, algorithm_version: "g1", learning_plan_version: "p1", source: "match_run", run_id: null,
        internships: [{ ...GAP.internship, relevance: 0.82 }, { internship_id: 40, title: "Data Analyst Intern", company: "Example Co", domain: null, is_active: true, relevance: 0.64 }],
        skipped_internship_ids: [7], newly_acquired_skills: ["Pandas"], learning_order: ["Docker"], recommendations: [RECS[0]],
      }, { status: 201 });
    }));
    renderAt("/skill-gaps");
    const user = userEvent.setup();
    expect(await screen.findByText("No skill gaps yet")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Internships to analyse"), "10");
    await user.click(screen.getByRole("button", { name: "Analyse my top matches" }));
    const status = await screen.findByText(/Analysed 2 internships from your latest matches\./);
    expect(status).toHaveTextContent("Now on your resume: Pandas.");
    expect(status).toHaveTextContent("1 closed internship(s) were skipped.");
    expect(bodies).toEqual([{ top_k: 10 }]);
    expect(within(recList()).getAllByRole("article")).toHaveLength(1);
  });

  it.each([
    [409, "No matching run yet. Run matching first or provide internship_ids.", true],
    [422, "This resume has no recognised skills. Add a skills section and re-parse it.", false],
  ])("explains a %i when generating", async (code, detail, linksToMatches) => {
    backend({ recs: [] });
    server.use(http.post("/api/skill-gaps/resumes/11", () => HttpResponse.json({ detail }, { status: code })));
    renderAt("/skill-gaps");
    await userEvent.click(await screen.findByRole("button", { name: "Analyse my top matches" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(detail);
    expect(Boolean(within(alert).queryByRole("link", { name: "Go to matches" }))).toBe(linksToMatches);
  });

  it("asks for a resume when none has been parsed, without calling skill-gap APIs", async () => {
    const calls = [];
    server.events.on("request:start", ({ request }) => calls.push(new URL(request.url).pathname));
    server.use(http.get("/api/resumes/", () => HttpResponse.json([{ ...RESUME, status: "failed" }])));
    renderAt("/skill-gaps");
    expect(await screen.findByText("Upload a resume to see your skill gaps")).toBeInTheDocument();
    expect(calls.some((p) => p.startsWith("/api/skill-gaps"))).toBe(false);
  });

  it("retries after a failure to load recommendations", async () => {
    let n = 0;
    backend();
    server.use(http.get("/api/skill-gaps", () => {
      n += 1;
      return n === 1 ? HttpResponse.error() : HttpResponse.json(RECS);
    }));
    renderAt("/skill-gaps");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Cannot reach the server");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Learning recommendations" })).toBeInTheDocument();
  });

  it("sends the student to sign in when the session has expired", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })),
      http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })),
    );
    renderAt("/skill-gaps");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/login?next=%2Fskill-gaps"));
  });

  it("is reachable from the navigation and marked as the current page", async () => {
    backend();
    renderAt("/skill-gaps");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Skill gaps" })).toHaveAttribute("aria-current", "page");
  });
});

// ================================================================================================
describe("Role-specific skills analysis", () => {
  const section = async () => (await screen.findByRole("heading", { name: "Skills analysis for a target role" })).closest("section");

  it("labels the general analysis and groups skills by how the resume shows them", async () => {
    backend();
    renderAt("/skill-gaps");
    const box = await section();
    expect(await within(box).findByText("Choose a target role")).toBeInTheDocument();
    expect(within(box).getByRole("list", { name: "Programming languages skills" })).toHaveTextContent(/Python.*Shown in a project/);
    expect(within(box).getByRole("list", { name: "Programming languages skills" })).toHaveTextContent(/Java.*Listed only/);
    expect(within(box).queryByRole("list", { name: "Skill gaps for this role" })).not.toBeInTheDocument();
  });

  it("shows the role's fit, requirements and prioritised gaps, and keeps the role in the URL", async () => {
    const calls = backend();
    renderAt("/skill-gaps");
    const user = userEvent.setup();
    const box = await section();
    await within(box).findByText("Choose a target role");
    await user.selectOptions(within(box).getByLabelText("Target role"), "java-developer");
    expect(location()).toContain("role=java-developer");
    const gaps = await within(box).findByRole("list", { name: "Skill gaps for this role" });
    expect(calls).toContain("GET /api/skill-gaps/role-analysis?role=java-developer&resume_id=11");
    expect(within(box).getByText("42")).toBeInTheDocument();
    expect(within(box).getByText("2 of 4")).toBeInTheDocument();
    const cards = within(gaps).getAllByRole("article");
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual(["Gap: Spring Boot", "Gap: Java"]);
    expect(within(cards[0]).getByText("high priority")).toBeInTheDocument();
    expect(within(cards[0]).getByText("Build a REST API for a library.")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Listed but not demonstrated")).toBeInTheDocument();
    expect(within(box).getByText(/does not mean you lack it/)).toBeInTheDocument();
    expect(within(box).getByRole("list", { name: "Role requirements" })).toHaveTextContent(/Spring Boot.*Not found in resume/);
  });

  it("shows an error with a retry when the analysis fails", async () => {
    backend();
    server.use(http.get("/api/skill-gaps/role-analysis", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderAt("/skill-gaps?role=java-developer");
    const box = await section();
    expect(await within(box).findByRole("button", { name: /try again|retry/i })).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Internship skill gap", () => {
  function gapBackend() {
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
      http.get("/api/skill-gaps/resumes/11/internships/99", () => HttpResponse.json(GAP)),
      http.get("/api/matches/resumes/11/internships/99", () => HttpResponse.json(MATCH)),
    );
  }

  it("shows coverage, skill groups, learning order, plans and the match breakdown", async () => {
    gapBackend();
    renderAt("/skill-gaps/internships/99");
    expect(await screen.findByRole("heading", { level: 1, name: "Machine Learning Intern" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Required skills you have: 3 have, 1 partly, 1 missing of 5" })).toBeInTheDocument();
    expect(screen.getByText("3 of 5")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Missing skills" })).toHaveTextContent("Docker");
    expect(screen.getByRole("list", { name: "Partly covered" })).toHaveTextContent("You know Machine Learning.");
    expect(screen.getByRole("list", { name: "Skills you have" })).toHaveTextContent("Python");
    expect(screen.getByText("Suggested order: Docker → Deep Learning")).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("list", { name: "Learning plans" })).getByRole("button"));
    expect(screen.getByText("About 25 hours")).toBeInTheDocument();
    expect(await screen.findByText("Strong match")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View internship" })).toHaveAttribute("href", "/internships/99");
  });

  it("explains when nothing is missing", async () => {
    gapBackend();
    server.use(http.get("/api/skill-gaps/resumes/11/internships/99", () =>
      HttpResponse.json({ ...GAP, summary: { ...GAP.summary, required_matched: 5, required_partial: 0, required_missing: 0 }, partial: [], missing: [], learning_order: [], learning_plans: [] })));
    renderAt("/skill-gaps/internships/99");
    expect(await screen.findByText(/No missing skills — your resume covers everything/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing to learn for this internship/)).toBeInTheDocument();
  });

  it("explains an internship that is unavailable", async () => {
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
      http.get("/api/skill-gaps/resumes/11/internships/5", () => HttpResponse.json({ detail: "Internship not found" }, { status: 404 })),
      http.get("/api/matches/resumes/11/internships/5", () => HttpResponse.json({ detail: "Internship not found" }, { status: 404 })),
    );
    renderAt("/skill-gaps/internships/5");
    expect(await screen.findByText("Internship not found")).toBeInTheDocument();
  });

  it("uses the internship for the learning plan only after confirmation", async () => {
    gapBackend();
    const bodies = [];
    server.use(http.post("/api/skill-gaps/resumes/11", async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json({ resume_id: 11, algorithm_version: "g1", learning_plan_version: "p1", source: "selection", run_id: null,
        internships: [], skipped_internship_ids: [], newly_acquired_skills: [], learning_order: [], recommendations: [RECS[0], RECS[1]] }, { status: 201 });
    }));
    renderAt("/skill-gaps/internships/99");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Use for my learning plan" }));
    let dialog = screen.getByRole("dialog", { name: "Base your learning plan on this internship?" });
    expect(dialog).toHaveTextContent("will be replaced");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(bodies).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Use for my learning plan" }));
    dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Update learning plan" }));
    expect(await screen.findByText(/Learning plan updated: 2 skills to work on\./)).toBeInTheDocument();
    expect(bodies).toEqual([{ internship_ids: [99] }]);
    expect(screen.getByRole("link", { name: "Open learning plan" })).toHaveAttribute("href", "/skill-gaps");
  });

  it("is linked from the internship detail page", async () => {
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
      http.get("/api/internships/99", () => HttpResponse.json({
        internship_id: 99, external_id: null, title: "Machine Learning Intern", company: "Example Labs", description: "x", eligibility: null,
        location: "Pune", application_url: null, deadline: null, domain: "Data Science", work_mode: "Hybrid", duration_weeks: 12,
        stipend_per_month: 10000, stipend_currency: "INR", min_education: null, source: "dataset", is_active: true,
        created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", required_skills: [], preferred_skills: [], skills: [],
      })),
      http.get("/api/applications/bookmarks/99", () => HttpResponse.json({ saved: false, bookmark: null })),
    );
    renderAt("/internships/99");
    expect(await screen.findByRole("link", { name: "View skill gap and learning plan" })).toHaveAttribute("href", "/skill-gaps/internships/99");
  });
});

// ================================================================================================
describe("Skill-gap helpers", () => {
  it("picks the next recommendation: in progress first, then the highest-priority open item", () => {
    expect(nextRecommendation(RECS).skill).toBe("Kafka");
    expect(nextRecommendation([RECS[0], RECS[2]]).skill).toBe("Docker");
    expect(nextRecommendation([RECS[2], RECS[3]])).toBeNull();
  });

  it("counts real records and labels completion sources", () => {
    expect(countByStatus(RECS)).toEqual({ pending: 1, in_progress: 1, completed: 1, dismissed: 1 });
    expect(completedViaLabel("resume")).toBe("Detected on your resume");
    expect(completedViaLabel("user")).toBe("Marked by you");
    expect(completedViaLabel(null)).toBeNull();
  });
});
