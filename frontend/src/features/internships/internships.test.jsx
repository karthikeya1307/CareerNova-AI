import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { deadlineInfo, formatDuration, formatStipend, sortInternships } from "./internshipFormat";
import { similarityPercent } from "./SemanticSearch";

// Fictional fixtures shaped like backend/schemas/internship_schema.py InternshipResponse.
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const make = (id, extra = {}) => ({
  internship_id: id, external_id: null, title: `Intern ${id}`, company: `Company ${id}`, description: `Description ${id}`,
  eligibility: null, location: "Bengaluru", application_url: null, deadline: null, domain: "Data Science", work_mode: "Hybrid",
  duration_weeks: 12, stipend_per_month: 10000 + id, stipend_currency: "INR", min_education: "Bachelor's degree", source: "dataset",
  is_active: true, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
  required_skills: ["Python", "SQL"], preferred_skills: ["Docker"], skills: [], ...extra,
});
const FILTERS = { domains: ["Data Science", "Web Development"], work_modes: ["Hybrid", "Onsite", "Remote"], locations: ["Bengaluru", "Pune"] };

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderAt(path) {
  setAccessToken("access-token");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={{ initialUser: student, restoreSession: false }} />
      <LocationProbe />
    </MemoryRouter>,
  );
}
const location = () => screen.getByTestId("location").textContent;

// A paginating fake of GET /internships/ over `all`, recording every query.
function catalogue(all) {
  const calls = [];
  server.use(
    http.get("/api/internships/filters", () => HttpResponse.json(FILTERS)),
    http.get("/api/internships/", ({ request }) => {
      const params = Object.fromEntries(new URL(request.url).searchParams);
      calls.push(params);
      const skip = Number(params.skip || 0);
      const limit = Number(params.limit || 20);
      return HttpResponse.json({ total: all.length, skip, limit, items: all.slice(skip, skip + limit) });
    }),
  );
  return calls;
}

// ================================================================================================
describe("Browse internships", () => {
  it("lists the first page with filter options from the backend", async () => {
    const calls = catalogue(Array.from({ length: 30 }, (_, i) => make(i + 1)));
    renderAt("/internships");
    expect(await screen.findByText("Showing 1–12 of 30 internships")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Internships" })).getAllByRole("article")).toHaveLength(12);
    expect(calls[0]).toEqual({ skip: "0", limit: "12" });
    await waitFor(() => expect(screen.getByLabelText("Domain")).toHaveTextContent("Web Development"));
    expect(screen.getByLabelText("Location")).toHaveTextContent("Pune");
  });

  it("applies keyword, skill, domain, location and work-mode filters, then clears them", async () => {
    const calls = catalogue([make(1)]);
    renderAt("/internships");
    const user = userEvent.setup();
    await screen.findByText("Showing 1–1 of 1 internship");

    await user.type(screen.getByLabelText("Keyword"), " analyst ");
    await user.type(screen.getByLabelText("Skill"), "Python");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(calls.at(-1)).toMatchObject({ q: "analyst", skill: "Python" }));

    await user.selectOptions(screen.getByLabelText("Domain"), "Data Science");
    await user.selectOptions(screen.getByLabelText("Location"), "Pune");
    await user.click(screen.getByRole("button", { name: "Remote" }));
    await waitFor(() =>
      expect(calls.at(-1)).toEqual({ q: "analyst", skill: "Python", domain: "Data Science", location: "Pune", work_mode: "Remote", skip: "0", limit: "12" }),
    );
    expect(screen.getByRole("button", { name: "Remote" })).toHaveAttribute("aria-pressed", "true");
    expect(location()).toContain("mode=Remote");

    await user.click(screen.getByRole("button", { name: "Clear all filters (5)" }));
    await waitFor(() => expect(calls.at(-1)).toEqual({ skip: "0", limit: "12" }));
    expect(screen.getByLabelText("Keyword")).toHaveValue("");
    expect(location()).toBe("/internships");
  });

  it("pages through results", async () => {
    const calls = catalogue(Array.from({ length: 30 }, (_, i) => make(i + 1)));
    renderAt("/internships");
    const user = userEvent.setup();
    await screen.findByText("Showing 1–12 of 30 internships");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Showing 13–24 of 30 internships")).toBeInTheDocument();
    expect(calls.at(-1)).toEqual({ skip: "12", limit: "12" });
    expect(location()).toBe("/internships?page=2");
    expect(screen.getByText("Page 2 of 3 (30 total)")).toBeInTheDocument();
  });

  it("sorts across every matching internship, not just one page", async () => {
    // 130 internships: stipend rises with id, so the highest stipends are on the *last* backend page.
    const calls = catalogue(Array.from({ length: 130 }, (_, i) => make(i + 1)));
    renderAt("/internships");
    const user = userEvent.setup();
    await screen.findByText("Showing 1–12 of 130 internships");
    await user.selectOptions(screen.getByLabelText("Sort by"), "stipend");

    expect(await screen.findByText(/sorted by stipend \(highest first\)/)).toBeInTheDocument();
    const fetched = calls.filter((c) => c.limit === "100");
    expect(fetched.map((c) => c.skip)).toEqual(["0", "100"]);
    const titles = within(screen.getByRole("list", { name: "Internships" })).getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles.slice(0, 3)).toEqual(["Intern 130", "Intern 129", "Intern 128"]);

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Internships" })).getAllByRole("heading", { level: 3 })[0]).toHaveTextContent("Intern 118"));
    expect(calls.filter((c) => c.limit === "100")).toHaveLength(2); // client-side paging, no refetch
  });

  it("shows an empty state with a way out", async () => {
    catalogue([]);
    renderAt("/internships?domain=Finance");
    expect(await screen.findByText("No internships match these filters")).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("region", { name: "Internship results" })).getByRole("button", { name: "Clear all filters" }));
    await waitFor(() => expect(location()).toBe("/internships"));
  });

  it("shows an error with retry, and still works if filter options fail", async () => {
    let calls = 0;
    server.use(
      http.get("/api/internships/filters", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
      http.get("/api/internships/", () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: "boom" }, { status: 500 }) : HttpResponse.json({ total: 1, skip: 0, limit: 12, items: [make(1)] });
      }),
    );
    renderAt("/internships");
    const results = await screen.findByRole("region", { name: "Internship results" });
    await userEvent.click(await within(results).findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Intern 1")).toBeInTheDocument();
    expect(screen.getByText("Filter options couldn't load.")).toBeInTheDocument();
  });

  it("sends the student to sign in when the session has expired", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    server.use(
      http.get("/api/internships/filters", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })),
      http.get("/api/internships/", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })),
      http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })),
    );
    renderAt("/internships");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/login?next=%2Finternships"));
  });
});

// ================================================================================================
describe("AI semantic search", () => {
  const searchHandler = (respond) => {
    const calls = [];
    server.use(http.get("/api/internships/search", ({ request }) => {
      const params = Object.fromEntries(new URL(request.url).searchParams);
      calls.push(params);
      return respond(params);
    }));
    return calls;
  };

  it("runs an example query and shows real results with similarity", async () => {
    const calls = searchHandler(({ q }) => HttpResponse.json({
      query: q, index_built_at: "2026-11-16T09:28:51+00:00",
      results: [{ similarity: 0.4657, internship: make(99, { title: "Machine Learning Intern" }) }, { similarity: 0.43, internship: make(40) }],
    }));
    renderAt("/internships?view=search");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Machine learning internships" }));

    const results = await screen.findByRole("list", { name: "Search results" });
    expect(calls).toEqual([{ q: "Machine learning internships", k: "10" }]);
    expect(within(results).getAllByRole("article")).toHaveLength(2);
    expect(within(results).getByText("Machine Learning Intern")).toBeInTheDocument();
    expect(within(results).getByText("47%")).toBeInTheDocument();
    expect(screen.getByText(/ranked by relevance/)).toHaveTextContent("index updated");
    expect(location()).toContain("query=Machine+learning+internships");
  });

  it("shows what was understood, why each result matched, and the backend's message", async () => {
    searchHandler(({ q }) => HttpResponse.json({
      query: q, index_built_at: null, mode: "hybrid", message: "CareerNova's catalogue lists internships only, so these are internships that match your search.",
      interpretation: { skills: [], roles: ["ai/ml"], keywords: [], location: "Hyderabad", work_mode: null, opportunity: "job", experience_level: "fresher / entry level" },
      results: [{ similarity: 0.53, score: 0.81, reasons: ["role: ai/ml", "in Hyderabad"], internship: make(7, { title: "Machine Learning Intern" }) }],
    }));
    renderAt("/internships?view=search&query=Entry-level%20AI%2FML%20jobs%20in%20Hyderabad");
    expect(await screen.findByLabelText("How your search was understood")).toHaveTextContent("role: ai/ml · location: Hyderabad · level: fresher / entry level");
    expect(screen.getByText(/catalogue lists internships only/)).toBeInTheDocument();
    const results = screen.getByRole("list", { name: "Search results" });
    expect(within(results).getByText("81%")).toBeInTheDocument();
    expect(within(results).getByText(/role: ai\/ml · in Hyderabad/)).toBeInTheDocument();
  });

  it("shows the backend's explanation when nothing matches", async () => {
    searchHandler(({ q }) => HttpResponse.json({ query: q, index_built_at: null, mode: "hybrid", interpretation: { skills: [], roles: [], keywords: ["pizza"] },
      message: "No internships in the catalogue match this search. Try a role (e.g. \"data analyst\").", results: [] }));
    renderAt("/internships?view=search&query=pizza%20delivery");
    expect(await screen.findByText("No internships found")).toBeInTheDocument();
    expect(screen.getByText(/No internships in the catalogue match this search/)).toBeInTheDocument();
  });

  it("validates the query length before searching", async () => {
    const calls = searchHandler(() => HttpResponse.json({ query: "", index_built_at: null, results: [] }));
    renderAt("/internships?view=search");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Describe the internship you want"), "a");
    await user.click(screen.getByRole("button", { name: "AI search" }));
    expect(screen.getByText("Enter at least 2 characters.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("explains when the search index is unavailable (503)", async () => {
    searchHandler(() => HttpResponse.json({ detail: "Search index has not been built yet" }, { status: 503 }));
    renderAt("/internships?view=search&query=python%20internships");
    expect(await screen.findByText("AI search is unavailable right now")).toBeInTheDocument();
  });

  it("shows when nothing matches", async () => {
    searchHandler(({ q }) => HttpResponse.json({ query: q, index_built_at: null, results: [] }));
    renderAt("/internships?view=search&query=underwater%20basket%20weaving");
    expect(await screen.findByText("No internships found")).toBeInTheDocument();
  });

  it("switches discovery modes with the keyboard", async () => {
    catalogue([make(1)]);
    renderAt("/internships");
    const browse = await screen.findByRole("tab", { name: "Browse & filter" });
    expect(browse).toHaveAttribute("aria-selected", "true");
    browse.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(await screen.findByRole("tab", { name: "AI search" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Describe the internship you want")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Internship details", () => {
  const RESUME_OK = { resume_id: 11, filename: "Asha_Rao_Resume.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-10T00:00:00Z" };
  const MATCH = {
    rank: null, score: 74.6, label: "Strong match", algorithm_version: "m1", score_before_caps: 74.6, data_completeness: 0.9,
    required_skill_coverage: 0.5,
    components: [
      { name: "skills", score: 0.6, weight: 0.5, weighted: 30, status: "assessed", detail: "1 of 2 required skills matched." },
      { name: "semantic", score: 0.71, weight: 0.3, weighted: 21.3, status: "assessed", detail: "Resume text is similar to the posting." },
    ],
    matched_required_skills: ["Python"], missing_required_skills: ["SQL"], matched_preferred_skills: [], missing_preferred_skills: ["Docker"],
    missing_information: [], caps_applied: [], explanation: ["Strong Python background."], internship: make(5),
  };
  const DETAIL = make(5, {
    title: "Data Analyst Intern", company: "Example Analytics", description: "Analyse product data.\nBuild dashboards.",
    eligibility: "Final-year students.", duration_weeks: 12, stipend_per_month: 15000, deadline: "2099-01-15T00:00:00Z",
    application_url: "https://careers.example.com/data-analyst",
  });

  function detailBackend(extra = {}) {
    server.use(
      http.get("/api/internships/5", () => HttpResponse.json({ ...DETAIL, ...extra })),
      http.get("/api/applications/bookmarks/5", () => HttpResponse.json({ saved: false, bookmark: null })),
    );
  }

  it("shows every available field from the backend", async () => {
    detailBackend();
    renderAt("/internships/5");
    expect(await screen.findByRole("heading", { level: 1, name: "Data Analyst Intern" })).toBeInTheDocument();
    expect(screen.getByText("Example Analytics")).toBeInTheDocument();
    expect(screen.getByText(/Analyse product data\./)).toBeInTheDocument();
    expect(screen.getByText("Final-year students.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Required skills" })).toHaveTextContent("PythonSQL");
    expect(screen.getByRole("list", { name: "Preferred skills" })).toHaveTextContent("Docker");
    expect(screen.getByText("3 months")).toBeInTheDocument();
    expect(screen.getByText("₹15,000/month")).toBeInTheDocument();
    expect(screen.getByText("Bachelor's degree")).toBeInTheDocument();
    expect(screen.getByText(/Apply by/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Apply on company site/ })).toHaveAttribute("href", "https://careers.example.com/data-analyst");
  });

  it("never renders a non-http application link", async () => {
    detailBackend({ application_url: "javascript:alert(1)" });
    renderAt("/internships/5");
    await screen.findByRole("heading", { level: 1, name: "Data Analyst Intern" });
    expect(screen.queryByRole("link", { name: /Apply on company site/ })).not.toBeInTheDocument();
  });

  it("explains an internship that is closed or missing", async () => {
    server.use(http.get("/api/internships/404", () => HttpResponse.json({ detail: "Internship not found" }, { status: 404 })));
    renderAt("/internships/404");
    expect(await screen.findByText("Internship not found")).toBeInTheDocument();
  });

  it("saves and unsaves the internship", async () => {
    detailBackend();
    const calls = [];
    server.use(
      http.post("/api/applications/bookmarks/5", () => {
        calls.push("POST");
        return HttpResponse.json({ bookmark_id: 1, internship_id: 5, created_at: "2026-11-16T00:00:00Z", internship: {}, application_id: null }, { status: 201 });
      }),
      http.delete("/api/applications/bookmarks/5", () => {
        calls.push("DELETE");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt("/internships/5");
    const user = userEvent.setup();
    const save = await screen.findByRole("button", { name: "Save for later" });
    await waitFor(() => expect(save).toBeEnabled());
    await user.click(save);
    const saved = await screen.findByRole("button", { name: "Saved" });
    expect(saved).toHaveAttribute("aria-pressed", "true");
    await user.click(saved);
    expect(await screen.findByRole("button", { name: "Save for later" })).toHaveAttribute("aria-pressed", "false");
    expect(calls).toEqual(["POST", "DELETE"]);
  });

  it("tracks the application, and explains when it is already tracked", async () => {
    detailBackend();
    const bodies = [];
    server.use(http.post("/api/applications", async ({ request }) => {
      bodies.push(await request.json());
      return bodies.length === 1
        ? HttpResponse.json({ application_id: 21 }, { status: 201 })
        : HttpResponse.json({ detail: { message: "You already have an application for this opening.", application_id: 21 } }, { status: 409 });
    }));
    renderAt("/internships/5");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Mark as applied" }));
    expect(await screen.findByText(/Added to your applications as Applied\./)).toBeInTheDocument();
    expect(bodies[0]).toEqual({ internship_id: 5, status: "APPLIED" }); // backend sets applied_at itself
    await user.click(screen.getByRole("button", { name: "Mark as applied" }));
    expect(await screen.findByText(/You already have an application for this opening\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View applications" })).toHaveAttribute("href", "/applications");
  });

  it("checks the match against the latest parsed resume and explains the score", async () => {
    detailBackend();
    const scored = [];
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([{ ...RESUME_OK, resume_id: 30, status: "failed" }, RESUME_OK])),
      http.get("/api/matches/resumes/:rid/internships/:iid", ({ params }) => {
        scored.push(`${params.rid}/${params.iid}`);
        return HttpResponse.json(MATCH);
      }),
    );
    renderAt("/internships/5");
    await userEvent.click(await screen.findByRole("button", { name: "Check my match" }));
    const panel = screen.getByRole("region", { name: "Your match" });
    expect(await within(panel).findByText("Strong match")).toBeInTheDocument();
    expect(scored).toEqual(["11/5"]);
    expect(within(panel).getByText("75%")).toBeInTheDocument();
    const components = within(panel).getByRole("list", { name: "Score components" });
    expect(components).toHaveTextContent("Skills");
    expect(components).toHaveTextContent("1 of 2 required skills matched.");
    expect(within(panel).getByRole("list", { name: "Required skills missing" })).toHaveTextContent("SQL");
    expect(within(panel).getByText("Strong Python background.")).toBeInTheDocument();
  });

  it("explains why a match could not be calculated, or asks for a resume", async () => {
    detailBackend();
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([RESUME_OK])),
      http.get("/api/matches/resumes/11/internships/5", () => HttpResponse.json({ detail: "The resume has no recognised skills to match against." }, { status: 422 })),
    );
    const { unmount } = renderAt("/internships/5");
    await userEvent.click(await screen.findByRole("button", { name: "Check my match" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The resume has no recognised skills to match against.");
    unmount();

    server.use(http.get("/api/resumes/", () => HttpResponse.json([])));
    renderAt("/internships/5");
    expect(await screen.findByText("Upload a resume to check your match")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Internship helpers", () => {
  it("sorts with missing values last and keeps ties stable", () => {
    const items = [make(1, { stipend_per_month: null }), make(2, { stipend_per_month: 5000 }), make(3, { stipend_per_month: 9000 }), make(4, { stipend_per_month: 5000 })];
    expect(sortInternships(items, "stipend").map((i) => i.internship_id)).toEqual([3, 2, 4, 1]);
    expect(sortInternships(items, "").map((i) => i.internship_id)).toEqual([1, 2, 3, 4]);
    const dated = [make(1, { deadline: null }), make(2, { deadline: "2027-02-01T00:00:00Z" }), make(3, { deadline: "2027-01-01T00:00:00Z" })];
    expect(sortInternships(dated, "deadline").map((i) => i.internship_id)).toEqual([3, 2, 1]);
  });

  it("formats stipend, duration and deadline", () => {
    expect(formatStipend(15000, "INR")).toBe("₹15,000/month");
    expect(formatStipend(0)).toBe("Unpaid");
    expect(formatStipend(null)).toBeNull();
    expect(formatDuration(12)).toBe("3 months");
    expect(formatDuration(6)).toBe("6 weeks");
    const now = new Date("2026-11-16T00:00:00Z");
    expect(deadlineInfo("2026-11-10T00:00:00Z", now)).toMatchObject({ label: "Deadline passed", tone: "danger" });
    expect(deadlineInfo("2026-11-19T00:00:00Z", now)).toMatchObject({ label: "Closes in 3 days", tone: "warning" });
    expect(deadlineInfo(null, now)).toBeNull();
  });

  it("shows similarity as a bounded percentage", () => {
    expect(similarityPercent(0.4657)).toBe(47);
    expect(similarityPercent(-0.2)).toBe(0);
    expect(similarityPercent(1.3)).toBe(100);
  });
});
