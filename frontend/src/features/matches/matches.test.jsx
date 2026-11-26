import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { orderedResults } from "./MatchesPage";

// Fictional fixtures shaped like backend/schemas/match_schema.py.
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const RESUME = { resume_id: 11, filename: "Asha_Rao_Resume.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-10T00:00:00Z" };
const internship = (id, title) => ({ internship_id: id, title, company: `Company ${id}`, location: "Bengaluru", work_mode: "Hybrid", domain: "Data Science", required_skills: [], preferred_skills: [] });
const item = (rank, score, id, title, extra = {}) => ({
  rank, score, label: score >= 70 ? "Strong match" : "Fair match", algorithm_version: "m1", score_before_caps: score, data_completeness: 1,
  required_skill_coverage: 0.75,
  components: [{ name: "skills", score: 0.8, weight: 0.5, weighted: 40, status: "assessed", detail: "3 of 4 required skills matched." }],
  matched_required_skills: ["Python"], missing_required_skills: ["Docker"], matched_preferred_skills: [], missing_preferred_skills: [],
  missing_information: [], caps_applied: [], explanation: ["Matches most required skills."], internship: internship(id, title), ...extra,
});
const RUN = (runId, results, extra = {}) => ({
  run_id: runId, resume_id: 11, algorithm_version: "m1", created_at: "2026-11-12T08:00:00Z", semantic_available: true,
  candidates_considered: 180, filters: {}, results, ...extra,
});
const LATEST = RUN("aaaaaaaa-0000-4000-8000-000000000001", [item(2, 64.2, 40, "Data Analyst Intern"), item(1, 82.4, 99, "Machine Learning Intern")]);
const OLDER = RUN("bbbbbbbb-0000-4000-8000-000000000002", [item(1, 55, 7, "QA Intern")], { created_at: "2026-11-01T08:00:00Z" });
const HISTORY = [
  { run_id: LATEST.run_id, created_at: LATEST.created_at, algorithm_version: "m1", result_count: 2, top_score: 82.4, top_label: "Strong match" },
  { run_id: OLDER.run_id, created_at: OLDER.created_at, algorithm_version: "m1", result_count: 1, top_score: 55, top_label: "Fair match" },
];

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderMatches(path = "/matches") {
  setAccessToken("access-token");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={{ initialUser: student, restoreSession: false }} />
      <LocationProbe />
    </MemoryRouter>,
  );
}

function backend({ latest = LATEST, history = HISTORY } = {}) {
  server.use(
    http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
    http.get("/api/matches/resumes/11", () => (latest ? HttpResponse.json(latest) : HttpResponse.json({ detail: "No matching results yet for this resume" }, { status: 404 }))),
    http.get("/api/matches/resumes/11/history", () => HttpResponse.json(history)),
    http.get(`/api/matches/runs/${OLDER.run_id}`, () => HttpResponse.json(OLDER)),
  );
}

const resultTitles = () =>
  within(screen.getByRole("list", { name: "Match results" })).getAllByRole("link").map((a) => a.textContent);

describe("Matches page", () => {
  it("shows the latest run in rank order with an expandable breakdown", async () => {
    backend();
    renderMatches();
    await screen.findByRole("list", { name: "Match results" });
    expect(resultTitles()).toEqual(["Machine Learning Intern", "Data Analyst Intern"]);
    expect(screen.getByText("180 internships considered")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /Show breakdown for Machine Learning Intern/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("list", { name: "Score components" })).toHaveTextContent("3 of 4 required skills matched.");
    expect(screen.getByText("Matches most required skills.")).toBeInTheDocument();
  });

  it("runs matching with the chosen filters and refreshes history", async () => {
    let historyCalls = 0;
    backend({ latest: null });
    const runs = [];
    server.use(
      http.get("/api/matches/resumes/11/history", () => {
        historyCalls += 1;
        return HttpResponse.json(historyCalls === 1 ? [] : HISTORY.slice(0, 1));
      }),
      http.post("/api/matches/resumes/11", ({ request }) => {
        runs.push(Object.fromEntries(new URL(request.url).searchParams));
        return HttpResponse.json(LATEST, { status: 201 });
      }),
    );
    renderMatches();
    const user = userEvent.setup();
    expect(await screen.findByText("No matches yet")).toBeInTheDocument();
    expect(screen.getByText("No runs yet.")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Results"), "20");
    await user.selectOptions(screen.getByLabelText("Work mode"), "Remote");
    await user.type(screen.getByLabelText("Location (optional)"), " Pune ");
    await user.click(screen.getByRole("button", { name: "Run matching" }));

    await screen.findByRole("list", { name: "Match results" });
    expect(runs).toEqual([{ k: "20", work_mode: "Remote", location: "Pune" }]);
    expect(await screen.findByRole("list", { name: "Previous runs" })).toBeInTheDocument();
  });

  it("validates the location filter before running", async () => {
    backend();
    const runs = [];
    server.use(http.post("/api/matches/resumes/11", () => {
      runs.push(1);
      return HttpResponse.json(LATEST, { status: 201 });
    }));
    renderMatches();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Location (optional)"), "P");
    await user.click(screen.getByRole("button", { name: "Run matching" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Location must be 2 to 150 characters.");
    expect(runs).toHaveLength(0);
  });

  it("explains when the resume lacks data for matching", async () => {
    backend();
    server.use(http.post("/api/matches/resumes/11", () => HttpResponse.json({ detail: "The resume has no recognised skills to match against." }, { status: 422 })));
    renderMatches();
    await userEvent.click(await screen.findByRole("button", { name: "Run matching" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The resume has no recognised skills to match against.");
  });

  it("opens an earlier run from the history", async () => {
    backend();
    renderMatches();
    const user = userEvent.setup();
    const history = await screen.findByRole("list", { name: "Previous runs" });
    expect(within(history).getAllByRole("button")[0]).toHaveAttribute("aria-current", "true");
    await user.click(within(history).getAllByRole("button")[1]);
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe(`/matches?run=${OLDER.run_id}`));
    await waitFor(() => expect(resultTitles()).toEqual(["QA Intern"]));
    expect(screen.getByText("Earlier run")).toBeInTheDocument();
  });

  it("notes when semantic similarity was unavailable for a run", async () => {
    backend({ latest: { ...LATEST, semantic_available: false } });
    renderMatches();
    expect(await screen.findByText(/Semantic similarity was unavailable for this run/)).toBeInTheDocument();
  });

  it("asks for a resume when none has been parsed", async () => {
    server.use(http.get("/api/resumes/", () => HttpResponse.json([{ ...RESUME, status: "failed" }])));
    renderMatches();
    expect(await screen.findByText("Upload a resume to get matches")).toBeInTheDocument();
  });

  it("orders results by rank, then score", () => {
    const run = { results: [item(null, 50, 3, "c"), item(2, 70, 2, "b"), item(1, 60, 1, "a"), item(null, 80, 4, "d")] };
    expect(orderedResults(run).map((r) => r.internship.title)).toEqual(["a", "b", "d", "c"]);
  });
});

// ================================================================================================
const INSIGHTS = (extra = {}) => ({
  algorithm: "insights-v1", skill_match: 72, application_readiness: 74, category: "improve", category_label: "Apply After Improvement",
  eligibility: { status: "eligible", label: "Eligible", detail: "B.Tech meets the requirement", requirement: "B.Tech" },
  matched_skills: [{ skill: "Python", importance: "required" }], partial_skills: [{ skill: "PostgreSQL", importance: "required", related: ["MySQL"] }],
  missing_skills: [{ skill: "Docker", importance: "required" }],
  reasons: ["You have 1 of 3 required skills: Python."], improvements: ["Learn Docker (required for this role) - start with: Containers."],
  application_url: "https://example.com/apply/99", source: "dataset",
  relevant_experience: [{ skill: "Python", where: ["Sales Report"] }], listed_only_skills: ["SQL"], ...extra,
});
const EXPLORE = (items, counts) => ({ mode: "explore", resume_id: counts ? 11 : null, total: items.length, skip: 0, limit: 20, category_counts: counts || null, items });
const exploreItem = (id, title, insights) => ({ internship: internship(id, title), score: insights ? 60 : null, label: insights ? "Fair" : null, insights: insights || null });

describe("Matching modes (P2)", () => {
  it("shows the category and insights for each For-my-resume result", async () => {
    backend({ latest: RUN(LATEST.run_id, [item(1, 82.4, 99, "Machine Learning Intern", { insights: INSIGHTS() })]) });
    renderMatches();
    await screen.findByRole("list", { name: "Match results" });
    expect(screen.getByText("Apply After Improvement")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Show breakdown for Machine Learning Intern/ }));
    const insights = screen.getByLabelText("Job insights");
    expect(within(insights).getByText("72%")).toBeInTheDocument();
    expect(within(insights).getByText("Eligible")).toBeInTheDocument();
    expect(within(insights).getByRole("list", { name: "Partially matched skills" })).toHaveTextContent("PostgreSQL ~ MySQL");
    expect(within(insights).getByRole("list", { name: "Not found in your resume" })).toHaveTextContent("Docker");
    expect(within(insights).getByText(/does not mean you lack the skill/)).toBeInTheDocument();
    expect(within(insights).getByText(/Learn Docker/)).toBeInTheDocument();
    expect(within(insights).getByRole("list", { name: "Relevant projects and experience" })).toHaveTextContent("Python: Sales Report");
    expect(within(insights).getByText(/Only in your skills list/)).toHaveTextContent("SQL");
    expect(within(insights).getByRole("link", { name: "Open application page" })).toHaveAttribute("href", "https://example.com/apply/99");
  });

  it("explores every job with the resume's insights and filters by category", async () => {
    backend();
    const calls = [];
    server.use(http.get("/api/matches/explore", ({ request }) => {
      const params = Object.fromEntries(new URL(request.url).searchParams);
      calls.push(params);
      const all = [exploreItem(1, "Data Analyst Intern", INSIGHTS({ category: "apply_now", category_label: "Apply Now" })),
        exploreItem(2, "Cloud Intern", INSIGHTS({ category: "long_term", category_label: "Long-Term Target", skill_match: 10 }))];
      const items = params.category ? all.filter((i) => i.insights.category === params.category) : all;
      return HttpResponse.json(EXPLORE(items, { apply_now: 1, improve: 0, long_term: 1 }));
    }));
    renderMatches("/matches?mode=explore");
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Opportunities" });
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThanOrEqual(2);
    expect(calls[0]).toMatchObject({ resume_id: "11", skip: "0", limit: "20" });
    expect(screen.getByRole("tab", { name: "Explore any job" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("button", { name: "Long-Term Target (1)" }));
    await waitFor(() => expect(calls.at(-1)).toMatchObject({ category: "long_term" }));
    await waitFor(() => expect(screen.queryByText("Data Analyst Intern")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /Show details for Cloud Intern/ }));
    expect(screen.getByLabelText("Job insights")).toHaveTextContent("10%");

    await user.type(screen.getByLabelText("Search role, company or domain"), "cloud");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(calls.at(-1)).toMatchObject({ q: "cloud", category: "long_term" }));
  });

  it("explores without a resume and says what a resume would add", async () => {
    const calls = [];
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([])),
      http.get("/api/matches/explore", ({ request }) => {
        calls.push(Object.fromEntries(new URL(request.url).searchParams));
        return HttpResponse.json(EXPLORE([exploreItem(1, "Data Analyst Intern")]));
      }),
    );
    renderMatches("/matches?mode=explore");
    expect(await screen.findByText("Data Analyst Intern")).toBeInTheDocument();
    expect(screen.getByText(/Upload a resume to see your skill match/)).toBeInTheDocument();
    expect(calls[0].resume_id).toBeUndefined();
    expect(screen.queryByRole("group", { name: "Filter by category" })).not.toBeInTheDocument();
  });

  it("switches back to For my resume", async () => {
    backend();
    server.use(http.get("/api/matches/explore", () => HttpResponse.json(EXPLORE([]))));
    renderMatches("/matches?mode=explore");
    await screen.findByText("No opportunities found");
    await userEvent.click(screen.getByRole("tab", { name: "For my resume" }));
    expect(await screen.findByRole("list", { name: "Match results" })).toBeInTheDocument();
  });
});
