import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { formatDate } from "../../utils/dates";
import { server } from "../../test/server";
import { nextApplicationStep } from "../dashboard/components/ApplicationsCard";
import { correctionTarget, eventLabel } from "./applicationFormat";
import { validateReminder } from "./components/ApplicationReminders";
import { validateRound } from "./components/InterviewRounds";
import { validateNewApplication } from "./components/NewApplicationForm";

// Fictional fixtures shaped like backend/schemas/application_schema.py (test-only data).
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const FUTURE = new Date(Date.now() + 3 * 24 * 3600 * 1000).toISOString();
const app = (id, extra = {}) => ({
  application_id: id, source: "internal", internship_id: 99, company_name: "Example Labs", title: "Machine Learning Intern",
  application_url: null, external_reference: null, domain: "Data Science", location: "Pune", work_mode: "Hybrid", status: "APPLIED",
  applied_at: "2026-11-10T09:00:00Z", status_changed_at: "2026-11-10T09:00:00Z", notes: null, contact_name: null, contact_email: null,
  resume_document_id: null, cover_letter_document_id: null, internship_active: true, deadline_passed: false, interview_count: 0,
  next_interview: null, pending_reminders: 0, next_reminder: null, deleted_at: null, created_at: "2026-11-10T09:00:00Z",
  updated_at: "2026-11-12T09:00:00Z", possible_duplicates: [], related: null, ...extra,
});
const DETAIL = app(21, {
  notes: "Referred by a senior.",
  related: {
    latest_match: { match_id: 3, run_id: null, score: 81.6, label: "Strong match", created_at: "2026-11-09T09:00:00Z" },
    documents: [{ document_id: 31, document_type: "resume", title: "Resume - Machine Learning Intern at Example Labs", current_version: 2 }],
    practice_sessions: [{ session_id: 41, title: "Practice interview - Machine Learning Intern at Example Labs", mode: "practice", status: "completed", score: 64.2, started_at: "2026-11-11T09:00:00Z" }],
    prepare_with: { method: "POST", endpoint: "/interviews/sessions", body: { internship_id: 99 } },
  },
});
const HISTORY = {
  application_id: 21,
  status_history: [{ history_id: 1, from_status: null, to_status: "APPLIED", change_type: "created", changed_at: "2026-11-10T09:00:00Z" }],
  activity: [{ activity_id: 1, event_type: "application_created", details: { source: "internal", status: "APPLIED" }, created_at: "2026-11-10T09:00:00Z" }],
};
const ROUND = {
  interview_id: 5, application_id: 21, round_number: 1, interview_type: "technical", mode: "online", scheduled_at: FUTURE, duration_minutes: 45,
  meeting_url: "https://meet.example.com/abc", location: null, preparation_notes: "Revise SQL joins.", feedback: null, outcome: "pending",
  interview_session_id: null, created_at: "2026-11-12T09:00:00Z", updated_at: "2026-11-12T09:00:00Z",
};
const REMINDER = {
  reminder_id: 8, application_id: 21, application_title: "Machine Learning Intern", company_name: "Example Labs", title: "Follow up with HR",
  description: "Ask about the timeline.", remind_at: FUTURE, is_completed: false, completed_at: null, overdue: false, due_within_24h: false,
  delivery: "not_sent", created_at: "2026-11-12T09:00:00Z", updated_at: "2026-11-12T09:00:00Z",
};
const SUMMARY = {
  generated_at: "2026-11-16T09:00:00Z", saved_internships: 4, total_applications: 3,
  by_status: { SAVED: 0, APPLIED: 2, SHORTLISTED: 0, INTERVIEW_SCHEDULED: 1, SELECTED: 0, REJECTED: 0, WITHDRAWN: 0 },
  submitted_applications: 3, selected: 0, rejected: 0, interviews_scheduled: 1, upcoming_interviews: 1,
  next_interviews: [{ interview_id: 5, application_id: 22, company_name: "Cobalt Cloud", title: "Data Analyst Intern", round_number: 1, interview_type: "hr", mode: "online", scheduled_at: FUTURE }],
  pending_reminders: 2, overdue_reminders: 1, completed_reminders: 0, success_rate: null, decision_rate: null, interview_rate: 33.3,
  formulas: { success_rate: "SELECTED / submitted x 100", decision_rate: "SELECTED / (SELECTED + REJECTED) x 100", interview_rate: "submitted with a round / submitted x 100" },
  recent_activity: [{ activity_id: 9, application_id: 21, company_name: "Example Labs", title: "Machine Learning Intern", event_type: "status_changed", details: { from_status: "SAVED", to_status: "APPLIED" }, created_at: "2026-11-12T09:00:00Z" }],
};
const page = (items, extra = {}) => ({ total: items.length, skip: 0, limit: 20, items, ...extra });
const BOOKMARK = (id, extra = {}) => ({
  bookmark_id: id, internship_id: 90 + id, created_at: "2026-11-08T09:00:00Z", application_id: null,
  internship: { internship_id: 90 + id, title: `Saved role ${id}`, company: `Company ${id}`, location: "Remote", work_mode: "Remote", domain: "Data", deadline: null, is_active: true, deadline_passed: false },
  ...extra,
});

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

// List-page backend; records the query strings of GET /applications.
function listBackend({ items = [app(21), app(22, { title: "Data Analyst Intern", company_name: "Cobalt Cloud", status: "INTERVIEW_SCHEDULED", interview_count: 1, notes: "Second round soon." })], summary = SUMMARY } = {}) {
  const queries = [];
  server.use(
    http.get("/api/applications/dashboard", () => HttpResponse.json(summary)),
    http.get("/api/applications", ({ request }) => {
      queries.push(new URL(request.url).search);
      return HttpResponse.json(page(items));
    }),
  );
  return queries;
}

// Detail-page backend with mutable state.
function detailBackend({ application = DETAIL, history = HISTORY, rounds = [], reminders = [] } = {}) {
  const state = { application: structuredClone(application), history: structuredClone(history), rounds: structuredClone(rounds), reminders: structuredClone(reminders), requests: [] };
  const record = async (request, extra = {}) => {
    let body = null;
    try {
      body = await request.clone().json();
    } catch {
      body = null;
    }
    state.requests.push({ method: request.method, url: new URL(request.url).pathname + new URL(request.url).search, body, ...extra });
    return body;
  };
  server.use(
    http.get("/api/applications/21", () => HttpResponse.json(state.application)),
    http.get("/api/applications/21/history", () => HttpResponse.json(state.history)),
    http.get("/api/applications/21/interviews", () => HttpResponse.json(state.rounds)),
    http.get("/api/applications/reminders", () => HttpResponse.json(page(state.reminders, { limit: 100 }))),
    http.get("/api/documents", () => HttpResponse.json([])),
    http.patch("/api/applications/21/status", async ({ request }) => {
      const body = await record(request);
      const from = state.application.status;
      state.application = { ...state.application, status: body.status };
      state.history.status_history.push({ history_id: state.history.status_history.length + 1, from_status: from, to_status: body.status, change_type: body.correction ? "correction" : "manual", changed_at: "2026-11-16T09:00:00Z" });
      return HttpResponse.json({ changed: true, from_status: from, to_status: body.status, application: { ...state.application, related: null }, warnings: [] });
    }),
  );
  return state;
}

// ================================================================================================
describe("Applications overview and list", () => {
  it("shows the backend's totals, status counts, upcoming interviews, rates and recent activity", async () => {
    listBackend();
    renderAt("/applications");
    const overview = (await screen.findByRole("heading", { name: "Overview" })).closest("section");
    expect(await within(overview).findByText("Saved internships")).toBeInTheDocument();
    const byStatus = within(overview).getByRole("list", { name: "Applications by status" });
    expect(within(byStatus).getByRole("button", { name: "Applied: 2. Show these applications" })).toBeInTheDocument();
    expect(within(byStatus).getAllByRole("button")).toHaveLength(7);
    const upcoming = within(overview).getByRole("list", { name: "Upcoming interviews" });
    expect(within(upcoming).getByRole("link", { name: /Cobalt Cloud — Data Analyst Intern/ })).toHaveAttribute("href", "/applications/22");
    expect(within(overview).getByText(/Interview rate:/)).toHaveTextContent("33.3%");
    expect(within(overview).getByText("submitted with a round / submitted x 100")).toBeInTheDocument();
    expect(within(overview).getByText("1 overdue")).toBeInTheDocument();
    expect(within(within(overview).getByRole("list", { name: "Recent activity" })).getByText(/Status changed: Saved → Applied/)).toBeInTheDocument();
  });

  it("lists applications with status, dates, interviews and notes", async () => {
    listBackend();
    renderAt("/applications");
    const list = await screen.findByRole("list", { name: "Applications" });
    const links = within(list).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/applications/21", "/applications/22"]);
    expect(within(links[0]).getByText("Applied")).toBeInTheDocument();
    expect(within(links[0]).getByText(new RegExp(`Applied ${formatDate("2026-11-10T09:00:00Z")}`))).toBeInTheDocument();
    expect(within(links[1]).getByText("Interview scheduled")).toBeInTheDocument();
    expect(within(links[1]).getByText("1 interview")).toBeInTheDocument();
    expect(within(links[1]).getByText("Second round soon.")).toBeInTheDocument();
  });

  it("filters by backend statuses, searches and sorts through the API", async () => {
    const queries = listBackend();
    renderAt("/applications");
    const user = userEvent.setup();
    await screen.findByRole("list", { name: "Applications" });
    const filters = screen.getByRole("group", { name: "Filter by status" });
    expect(within(filters).getAllByRole("button").map((b) => b.textContent)).toEqual(["Saved", "Applied", "Shortlisted", "Interview scheduled", "Selected", "Rejected", "Withdrawn"]);
    await user.click(within(filters).getByRole("button", { name: "Applied" }));
    await user.click(within(filters).getByRole("button", { name: "Shortlisted" }));
    await waitFor(() => expect(location()).toBe("/applications?status=APPLIED&status=SHORTLISTED"));
    await user.type(screen.getByLabelText(/Search applications/), "labs");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.selectOptions(screen.getByLabelText("Sort by"), "company_name");
    await user.selectOptions(screen.getByLabelText("Order"), "asc");
    await waitFor(() => expect(queries.at(-1)).toBe("?status=APPLIED&status=SHORTLISTED&q=labs&sort=company_name&order=asc&skip=0&limit=20"));
    expect(queries[0]).toBe("?sort=updated_at&order=desc&skip=0&limit=20");
  });

  it("filters from the status counts in the overview", async () => {
    const queries = listBackend();
    renderAt("/applications");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Interview scheduled: 1. Show these applications" }));
    await waitFor(() => expect(queries.at(-1)).toContain("status=INTERVIEW_SCHEDULED"));
  });

  it("shows empty, filtered-empty and error states with retry", async () => {
    listBackend({ items: [] });
    let fail = true;
    server.use(http.get("/api/applications", ({ request }) => {
      if (fail) {
        fail = false;
        return HttpResponse.json({ detail: "Service unavailable" }, { status: 503 });
      }
      return HttpResponse.json(page([]), { headers: { "x-q": new URL(request.url).search } });
    }));
    renderAt("/applications");
    const user = userEvent.setup();
    const panel = screen.getByRole("tabpanel");
    await user.click(await within(panel).findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Selected" }));
    expect(await screen.findByText("No matching applications")).toBeInTheDocument();
  });

  it("pages through results with skip", async () => {
    const queries = [];
    server.use(
      http.get("/api/applications/dashboard", () => HttpResponse.json(SUMMARY)),
      http.get("/api/applications", ({ request }) => {
        const url = new URL(request.url);
        queries.push(url.searchParams.get("skip"));
        return HttpResponse.json({ total: 25, skip: Number(url.searchParams.get("skip")), limit: 20, items: [app(21)] });
      }),
    );
    renderAt("/applications");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(queries).toEqual(["0", "20"]));
    expect(location()).toBe("/applications?skip=20");
  });
});

// ================================================================================================
describe("Adding an application", () => {
  it("validates, then creates an external application and opens it", async () => {
    listBackend();
    const bodies = [];
    server.use(http.post("/api/applications", async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(app(30, { source: "external", company_name: "Nimbus", title: "Data Intern" }), { status: 201 });
    }));
    detailBackend({ application: app(30, { source: "external", company_name: "Nimbus", title: "Data Intern" }) });
    server.use(
      http.get("/api/applications/30", () => HttpResponse.json(app(30, { source: "external", company_name: "Nimbus", title: "Data Intern" }))),
      http.get("/api/applications/30/history", () => HttpResponse.json({ ...HISTORY, application_id: 30 })),
      http.get("/api/applications/30/interviews", () => HttpResponse.json([])),
    );
    renderAt("/applications");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add an application" }));
    const form = screen.getByRole("form", { name: "Add an application" });
    await user.type(within(form).getByLabelText("Application link (optional)"), "not a url");
    await user.click(within(form).getByRole("button", { name: "Add application" }));
    expect(within(form).getByText("Enter the company.")).toBeInTheDocument();
    expect(within(form).getByText("Enter the role.")).toBeInTheDocument();
    expect(within(form).getByText("Enter a full http:// or https:// URL.")).toBeInTheDocument();
    expect(bodies).toHaveLength(0);

    await user.type(within(form).getByLabelText("Company"), " Nimbus ");
    await user.type(within(form).getByLabelText("Role"), "Data Intern");
    await user.clear(within(form).getByLabelText("Application link (optional)"));
    await user.type(within(form).getByLabelText("Application link (optional)"), "https://jobs.example.com/1");
    await user.selectOptions(within(form).getByLabelText("Work mode (optional)"), "Remote");
    await user.type(within(form).getByLabelText("Notes (optional)"), "Applied via careers page");
    await user.click(within(form).getByRole("button", { name: "Add application" }));
    await waitFor(() => expect(location()).toBe("/applications/30"));
    expect(bodies).toEqual([{ company_name: "Nimbus", title: "Data Intern", status: "APPLIED", application_url: "https://jobs.example.com/1", work_mode: "Remote", notes: "Applied via careers page" }]);
    expect(await screen.findByText(/Application added. Update its status/)).toBeInTheDocument();
  });

  it("explains a duplicate (409) and links to the existing application", async () => {
    listBackend();
    server.use(http.post("/api/applications", () => HttpResponse.json({ detail: { message: "You already have an application for this opening.", application_id: 21 } }, { status: 409 })));
    renderAt("/applications");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add an application" }));
    const form = screen.getByRole("form", { name: "Add an application" });
    await user.type(within(form).getByLabelText("Company"), "Example Labs");
    await user.type(within(form).getByLabelText("Role"), "Machine Learning Intern");
    await user.click(within(form).getByRole("button", { name: "Add application" }));
    expect(await within(form).findByText("You already have an application for this opening.")).toBeInTheDocument();
    expect(within(form).getByRole("link", { name: "Open the existing application" })).toHaveAttribute("href", "/applications/21");
    expect(within(form).getByLabelText("Company")).toHaveValue("Example Labs");
  });
});

// ================================================================================================
describe("Saved internships, reminders and trash", () => {
  it("lists saved internships, tracks one as applied and removes another after confirmation", async () => {
    listBackend();
    let bookmarks = [BOOKMARK(1), BOOKMARK(2, { application_id: 21 })];
    const posts = [];
    const deletes = [];
    server.use(
      http.get("/api/applications/bookmarks", () => HttpResponse.json(page(bookmarks))),
      http.delete("/api/applications/bookmarks/:iid", ({ params }) => {
        deletes.push(params.iid);
        bookmarks = bookmarks.filter((b) => String(b.internship_id) !== params.iid);
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("/api/applications", async ({ request }) => {
        posts.push(await request.json());
        return HttpResponse.json(app(40), { status: 201 });
      }),
      http.get("/api/applications/40", () => HttpResponse.json(app(40))),
      http.get("/api/applications/40/history", () => HttpResponse.json({ ...HISTORY, application_id: 40 })),
      http.get("/api/applications/40/interviews", () => HttpResponse.json([])),
      http.get("/api/applications/reminders", () => HttpResponse.json(page([]))),
    );
    renderAt("/applications?tab=saved");
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Saved internships" });
    expect(within(list).getByRole("link", { name: "Saved role 1" })).toHaveAttribute("href", "/internships/91");
    expect(within(list).getByRole("link", { name: "View application" })).toHaveAttribute("href", "/applications/21");

    await user.click(within(list).getByRole("button", { name: "Remove Saved role 2 at Company 2 from saved" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(deletes).toEqual([]);
    await user.click(within(list).getByRole("button", { name: "Remove Saved role 2 at Company 2 from saved" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Saved internships" })).queryByText("Saved role 2")).not.toBeInTheDocument());
    expect(deletes).toEqual(["92"]);

    await user.click(screen.getByRole("button", { name: "Mark Saved role 1 at Company 1 as applied" }));
    await waitFor(() => expect(location()).toBe("/applications/40"));
    expect(posts).toEqual([{ internship_id: 91, status: "APPLIED" }]);
  });

  it("shows an empty saved list", async () => {
    listBackend();
    server.use(http.get("/api/applications/bookmarks", () => HttpResponse.json(page([]))));
    renderAt("/applications?tab=saved");
    expect(await screen.findByText("No saved internships")).toBeInTheDocument();
  });

  it("shows stored reminders as not sent, completes and deletes them", async () => {
    listBackend();
    let reminders = [REMINDER, { ...REMINDER, reminder_id: 9, title: "Send portfolio", overdue: true }];
    const patches = [];
    const states = [];
    server.use(
      http.get("/api/applications/reminders", ({ request }) => {
        states.push(new URL(request.url).searchParams.get("status"));
        return HttpResponse.json(page(reminders, { limit: 100 }));
      }),
      http.patch("/api/applications/reminders/:id", async ({ params, request }) => {
        patches.push({ id: params.id, body: await request.json() });
        reminders = reminders.map((r) => (String(r.reminder_id) === params.id ? { ...r, is_completed: true } : r));
        return HttpResponse.json(reminders[0]);
      }),
      http.delete("/api/applications/reminders/:id", ({ params }) => {
        reminders = reminders.filter((r) => String(r.reminder_id) !== params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt("/applications?tab=reminders");
    const user = userEvent.setup();
    expect(await screen.findByText(/no email, SMS or push notification is sent/)).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Reminders" });
    expect(within(list).getAllByText(/Stored only, not sent/)).toHaveLength(2);
    expect(within(list).getByText("Overdue")).toBeInTheDocument();
    expect(within(list).getAllByRole("link", { name: "Example Labs — Machine Learning Intern" }).map((l) => l.getAttribute("href"))).toEqual(["/applications/21", "/applications/21"]);

    await user.click(within(list).getByRole("button", { name: "Mark as done: Follow up with HR" }));
    await waitFor(() => expect(patches).toEqual([{ id: "8", body: { is_completed: true } }]));
    await user.click(within(list).getByRole("button", { name: "Delete reminder Send portfolio" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete reminder" }));
    await waitFor(() => expect(screen.queryByText("Send portfolio")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(states.at(-1)).toBe("completed"));
  });

  it("restores from the trash and deletes permanently only after typing DELETE", async () => {
    listBackend();
    let trash = [app(50, { deleted_at: "2026-11-15T09:00:00Z", title: "Old role" }), app(51, { deleted_at: "2026-11-14T09:00:00Z", title: "Stale role" })];
    const calls = [];
    server.use(
      http.get("/api/applications/trash", () => HttpResponse.json(page(trash))),
      http.post("/api/applications/:id/restore", ({ params }) => {
        calls.push(`restore ${params.id}`);
        trash = trash.filter((a) => String(a.application_id) !== params.id);
        return HttpResponse.json(app(Number(params.id)));
      }),
      http.delete("/api/applications/:id/permanent", ({ params, request }) => {
        calls.push(`purge ${params.id} ${new URL(request.url).search}`);
        trash = trash.filter((a) => String(a.application_id) !== params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt("/applications?tab=trash");
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Applications in the trash" });
    await user.click(within(list).getByRole("button", { name: "Restore Old role at Example Labs" }));
    await waitFor(() => expect(screen.queryByText("Old role")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Delete Stale role at Example Labs permanently" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Delete permanently" })).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(within(dialog).getByRole("button", { name: "Delete permanently" }));
    expect(await screen.findByText("The trash is empty")).toBeInTheDocument();
    expect(calls).toEqual(["restore 50", "purge 51 ?confirm=true"]);
  });
});

// ================================================================================================
describe("Application detail", () => {
  it("shows internship details, status, history, interviews, reminders and related links", async () => {
    detailBackend({ rounds: [ROUND], reminders: [REMINDER] });
    renderAt("/applications/21");
    expect(await screen.findByRole("heading", { name: "Machine Learning Intern" })).toBeInTheDocument();
    expect(screen.getByText("From the internship catalogue")).toBeInTheDocument();
    expect(screen.getByText("Referred by a senior.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View internship" })).toHaveAttribute("href", "/internships/99");
    expect(await screen.findByRole("list", { name: "Status history" })).toHaveTextContent("Applied");
    const rounds = await screen.findByRole("list", { name: "Interview rounds" });
    expect(within(rounds).getByText(/Round 1: Technical · Online/)).toBeInTheDocument();
    expect(within(rounds).getByText("Pending")).toBeInTheDocument();
    expect(within(await screen.findByRole("list", { name: "Application reminders" })).getByText("Follow up with HR")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Linked documents" })).getByRole("link")).toHaveAttribute("href", "/documents/31");
    expect(within(screen.getByRole("list", { name: "Practice sessions" })).getByRole("link")).toHaveAttribute("href", "/interview-prep/sessions/41");
    expect(screen.getByRole("link", { name: "Practise interview questions" })).toHaveAttribute("href", "/interview-prep?internship=99");
    expect(screen.getByText(/Latest match:/)).toHaveTextContent("82% (Strong match)");
  });

  it("offers only the backend's transitions and updates the status with expected_status", async () => {
    const state = detailBackend();
    renderAt("/applications/21");
    const user = userEvent.setup();
    const select = await screen.findByLabelText("New status");
    expect(within(select).getAllByRole("option").map((o) => o.value)).toEqual(["", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"]);
    await user.click(screen.getByRole("button", { name: "Update status" }));
    expect(screen.getByText("Choose the new status.")).toBeInTheDocument();
    await user.selectOptions(select, "SHORTLISTED");
    await user.click(screen.getByRole("button", { name: "Update status" }));
    await waitFor(() => expect(state.requests).toEqual([{ method: "PATCH", url: "/api/applications/21/status", body: { status: "SHORTLISTED", correction: false, expected_status: "APPLIED" } }]));
    const statusSection = screen.getByRole("heading", { name: "Status" }).closest("section");
    expect(await within(statusSection).findByText("Shortlisted")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Undo last change (back to Applied)" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Status history" })).getByText("Applied → Shortlisted")).toBeInTheDocument();
  });

  it("confirms decisions such as Rejected before sending them", async () => {
    const state = detailBackend();
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("New status"), "REJECTED");
    await user.click(screen.getByRole("button", { name: "Update status" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(state.requests).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Update status" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark as Rejected" }));
    await waitFor(() => expect(state.requests).toHaveLength(1));
    expect(state.requests[0].body).toEqual({ status: "REJECTED", correction: false, expected_status: "APPLIED" });
    expect(await screen.findByText(/Rejected is final/)).toBeInTheDocument();
  });

  it("keeps the previous status and reloads when the backend reports a conflict", async () => {
    const state = detailBackend();
    let gets = 0;
    server.use(
      http.get("/api/applications/21", () => {
        gets += 1;
        return HttpResponse.json(state.application);
      }),
      http.patch("/api/applications/21/status", () => HttpResponse.json({ detail: "The application status is now SHORTLISTED. Reload and try again." }, { status: 409 })),
    );
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("New status"), "SHORTLISTED");
    await user.click(screen.getByRole("button", { name: "Update status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The application status is now SHORTLISTED. Reload and try again.");
    const statusSection = screen.getByRole("heading", { name: "Status" }).closest("section");
    expect(within(statusSection).getByText("Applied")).toBeInTheDocument();
    await waitFor(() => expect(gets).toBeGreaterThan(1));
  });

  it("sends one status change when Update is clicked repeatedly", async () => {
    const state = detailBackend();
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    server.use(http.patch("/api/applications/21/status", async ({ request }) => {
      state.requests.push(await request.json());
      await held;
      return HttpResponse.json({ changed: true, from_status: "APPLIED", to_status: "SHORTLISTED", application: { ...state.application, status: "SHORTLISTED" }, warnings: [] });
    }));
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("New status"), "SHORTLISTED");
    const button = screen.getByRole("button", { name: "Update status" });
    await user.click(button);
    await user.click(button);
    await waitFor(() => expect(state.requests).toHaveLength(1));
    release();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Status" }).closest("section")).toHaveTextContent("Shortlisted"));
    expect(state.requests).toHaveLength(1);
  });

  it("undoes the last change as a correction after confirmation", async () => {
    const history = { ...HISTORY, status_history: [...HISTORY.status_history, { history_id: 2, from_status: "APPLIED", to_status: "SHORTLISTED", change_type: "manual", changed_at: "2026-11-12T09:00:00Z" }] };
    const state = detailBackend({ application: { ...DETAIL, status: "SHORTLISTED" }, history });
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Undo last change (back to Applied)" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Undo change" }));
    await waitFor(() => expect(state.requests[0]?.body).toEqual({ status: "APPLIED", correction: true, expected_status: "SHORTLISTED" }));
  });

  it("adds an interview round and reports the automatic status change", async () => {
    const state = detailBackend();
    const posts = [];
    server.use(http.post("/api/applications/21/interviews", async ({ request }) => {
      const body = await request.json();
      posts.push(body);
      state.rounds = [{ ...ROUND, ...body }];
      state.application = { ...state.application, status: "INTERVIEW_SCHEDULED" };
      return HttpResponse.json({ ...ROUND, ...body, status_change: { from_status: "APPLIED", to_status: "INTERVIEW_SCHEDULED", reason: "interview_added" } }, { status: 201 });
    }));
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add interview round" }));
    const form = screen.getByRole("form", { name: "Add round" });
    await user.type(within(form).getByLabelText("Duration in minutes (optional)"), "2");
    await user.click(within(form).getByRole("button", { name: "Add round" }));
    expect(within(form).getByText("Choose the date and time.")).toBeInTheDocument();
    expect(within(form).getByText("Enter 5–600 minutes.")).toBeInTheDocument();
    expect(posts).toHaveLength(0);

    await user.selectOptions(within(form).getByLabelText("Interview type"), "hr");
    await user.type(within(form).getByLabelText("Date and time"), "2026-12-01T10:30");
    await user.clear(within(form).getByLabelText("Duration in minutes (optional)"));
    await user.type(within(form).getByLabelText("Duration in minutes (optional)"), "30");
    await user.type(within(form).getByLabelText("Meeting link (optional)"), "https://meet.example.com/x");
    await user.click(within(form).getByRole("button", { name: "Add round" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({
      interview_type: "hr", mode: "online", scheduled_at: new Date("2026-12-01T10:30").toISOString(), outcome: "pending",
      duration_minutes: 30, meeting_url: "https://meet.example.com/x",
    });
    expect(await screen.findByText("Status changed automatically: Applied → Interview scheduled.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Status" }).closest("section")).toHaveTextContent("Interview scheduled"));
  });

  it("does not offer interview rounds before the application is submitted", async () => {
    detailBackend({ application: { ...DETAIL, status: "SAVED", applied_at: null } });
    renderAt("/applications/21");
    expect(await screen.findByText(/Interview rounds can be added once the application is submitted/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add interview round" })).not.toBeInTheDocument();
  });

  it("edits a round's outcome and deletes a round after confirmation", async () => {
    const state = detailBackend({ application: { ...DETAIL, status: "INTERVIEW_SCHEDULED" }, rounds: [ROUND] });
    const calls = [];
    server.use(
      http.patch("/api/applications/interviews/5", async ({ request }) => {
        const body = await request.json();
        calls.push({ patch: body });
        state.rounds = [{ ...ROUND, ...body }];
        return HttpResponse.json({ ...ROUND, ...body, status_change: null });
      }),
      http.delete("/api/applications/interviews/5", () => {
        calls.push("delete");
        state.rounds = [];
        return HttpResponse.json({ deleted: true, status_change: { from_status: "INTERVIEW_SCHEDULED", to_status: "APPLIED", reason: "interview_cancelled" } });
      }),
    );
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit round 1" }));
    const form = screen.getByRole("form", { name: "Save round 1" });
    await user.selectOptions(within(form).getByLabelText("Outcome"), "passed");
    await user.type(within(form).getByLabelText(/^Feedback/), "Went well.");
    await user.click(within(form).getByRole("button", { name: "Save round 1" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].patch).toMatchObject({ interview_type: "technical", mode: "online", outcome: "passed", feedback: "Went well." });
    expect(await within(await screen.findByRole("list", { name: "Interview rounds" })).findByText("Passed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete round 1" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete round" }));
    expect(await screen.findByText("Status changed automatically: Interview scheduled → Applied.")).toBeInTheDocument();
    expect(calls).toEqual([expect.anything(), "delete"]);
  });

  it("adds a stored reminder with validation", async () => {
    const state = detailBackend();
    const posts = [];
    server.use(http.post("/api/applications/21/reminders", async ({ request }) => {
      const body = await request.json();
      posts.push(body);
      state.reminders = [{ ...REMINDER, ...body }];
      return HttpResponse.json({ ...REMINDER, ...body }, { status: 201 });
    }));
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add reminder" }));
    const form = screen.getByRole("form", { name: "Add reminder" });
    await user.type(within(form).getByLabelText("Remind me at"), "2020-01-01T10:00");
    await user.click(within(form).getByRole("button", { name: "Save reminder" }));
    expect(within(form).getByText("Enter a title.")).toBeInTheDocument();
    expect(within(form).getByText("Choose a time in the future.")).toBeInTheDocument();
    await user.type(within(form).getByLabelText("Title"), "Email the recruiter");
    await user.clear(within(form).getByLabelText("Remind me at"));
    await user.type(within(form).getByLabelText("Remind me at"), "2027-01-05T09:00");
    await user.click(within(form).getByRole("button", { name: "Save reminder" }));
    await waitFor(() => expect(posts).toEqual([{ title: "Email the recruiter", remind_at: new Date("2027-01-05T09:00").toISOString() }]));
    expect(await within(await screen.findByRole("list", { name: "Application reminders" })).findByText("Email the recruiter")).toBeInTheDocument();
  });

  it("saves only the changed details", async () => {
    const state = detailBackend();
    const patches = [];
    server.use(http.patch("/api/applications/21", async ({ request }) => {
      const body = await request.json();
      patches.push(body);
      state.application = { ...state.application, ...body };
      return HttpResponse.json(state.application);
    }));
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const form = screen.getByRole("form", { name: "Edit application details" });
    expect(within(form).queryByLabelText("Company")).not.toBeInTheDocument(); // catalogue details are not editable
    await user.type(within(form).getByLabelText("Contact email"), "not-an-email");
    await user.click(within(form).getByRole("button", { name: "Save details" }));
    expect(within(form).getByText("Enter a valid email address.")).toBeInTheDocument();
    await user.clear(within(form).getByLabelText("Contact email"));
    await user.type(within(form).getByLabelText("Contact email"), "hr@example.com");
    await user.clear(within(form).getByLabelText(/^Notes/));
    await user.click(within(form).getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(patches).toEqual([{ notes: null, contact_email: "hr@example.com" }]));
    expect(await screen.findByText("hr@example.com")).toBeInTheDocument();
  });

  it("moves the application to the trash after confirmation", async () => {
    detailBackend();
    const deletes = [];
    server.use(
      http.delete("/api/applications/21", ({ request }) => {
        deletes.push(new URL(request.url).search);
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("/api/applications/dashboard", () => HttpResponse.json(SUMMARY)),
      http.get("/api/applications/trash", () => HttpResponse.json(page([]))),
    );
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Move to trash" }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/change the status to Withdrawn instead/);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Move to trash" }));
    await waitFor(() => expect(location()).toBe("/applications?tab=trash"));
    expect(deletes).toEqual(["?confirm=true"]);
  });

  it("shows not found for a missing or another student's application, and retries other errors", async () => {
    server.use(
      http.get("/api/applications/77", () => HttpResponse.json({ detail: "Application not found" }, { status: 404 })),
      http.get("/api/applications/77/history", () => HttpResponse.json({ detail: "Application not found" }, { status: 404 })),
    );
    renderAt("/applications/77");
    expect(await screen.findByText("Application not found")).toBeInTheDocument();
  });

  it("retries after a failed load", async () => {
    const state = detailBackend();
    let calls = 0;
    server.use(http.get("/api/applications/21", () => {
      calls += 1;
      return calls === 1 ? HttpResponse.json({ detail: "Forbidden" }, { status: 403 }) : HttpResponse.json(state.application);
    }));
    renderAt("/applications/21");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Machine Learning Intern" })).toBeInTheDocument();
  });

  it("sends the student to sign in when the session has expired", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    const expired = () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 });
    server.use(
      http.get("/api/applications/dashboard", expired),
      http.get("/api/applications", expired),
      http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })),
    );
    renderAt("/applications");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/login?next=%2Fapplications"));
  });
});

// ================================================================================================
describe("Dashboard integration and helpers", () => {
  it("shows the next step and links applications on the dashboard", async () => {
    server.use(
      http.get("/api/applications/dashboard", () => HttpResponse.json(SUMMARY)),
      http.get("/api/applications", () => HttpResponse.json(page([app(21)]))),
    );
    renderAt("/");
    const card = (await screen.findByRole("heading", { name: "Applications", level: 2 })).closest("section");
    expect(await within(card).findByRole("link", { name: "Next step: 1 overdue reminder to review" })).toHaveAttribute("href", "/applications?tab=reminders");
    expect(within(card).getByRole("link", { name: /Next interview: Cobalt Cloud/ })).toHaveAttribute("href", "/applications/22");
    expect(within(within(card).getByRole("list", { name: "Recent applications" })).getByRole("link", { name: "Machine Learning Intern" })).toHaveAttribute("href", "/applications/21");
  });

  it("chooses next steps and validates forms like the backend", () => {
    expect(nextApplicationStep({ ...SUMMARY, overdue_reminders: 0 })).toEqual({ text: "Prepare for your interview with Cobalt Cloud", to: "/applications/22", tone: "warning" });
    expect(nextApplicationStep({ ...SUMMARY, overdue_reminders: 0, next_interviews: [], pending_reminders: 0, total_applications: 0 })).toEqual({ text: "Apply to the internships you saved", to: "/applications?tab=saved", tone: "info" });
    expect(nextApplicationStep({ ...SUMMARY, overdue_reminders: 0, next_interviews: [], pending_reminders: 0, saved_internships: 0 })).toBeNull();

    const history = { status_history: [
      { history_id: 1, from_status: null, to_status: "APPLIED" },
      { history_id: 3, from_status: "SHORTLISTED", to_status: "INTERVIEW_SCHEDULED" },
      { history_id: 2, from_status: "APPLIED", to_status: "SHORTLISTED" },
    ] };
    expect(correctionTarget(history, "INTERVIEW_SCHEDULED")).toBe("SHORTLISTED");
    expect(correctionTarget(history, "APPLIED")).toBeNull();
    expect(eventLabel({ event_type: "interview_added", details: { round_number: 2 } })).toBe("Interview round added (round 2)");

    const now = new Date("2026-11-16T09:00:00Z");
    expect(validateNewApplication({ company_name: "A", title: "B", application_url: "ftp://x", location: "", status: "APPLIED", applied_at: "2030-01-01T00:00", notes: "" }, now)).toEqual({
      application_url: "Enter a full http:// or https:// URL.", applied_at: "Choose a date between 2000 and now.",
    });
    expect(validateRound({ scheduled_at: "2030-01-01T00:00", duration_minutes: "601", meeting_url: "", location: "", preparation_notes: "", feedback: "" }, now)).toEqual({
      scheduled_at: "Choose a date within two years of today.", duration_minutes: "Enter 5–600 minutes.",
    });
    expect(validateReminder({ title: "x".repeat(151), description: "", remind_at: "2029-01-01T00:00" }, now)).toEqual({
      title: "Use at most 150 characters.", remind_at: "Choose a time within two years.",
    });
  });
});

// ================================================================================================
describe("Application links (F11 hardening)", () => {
  it("never renders stored non-http(s) links as clickable links", async () => {
    detailBackend({
      application: { ...DETAIL, application_url: "javascript:alert(1)" },
      rounds: [{ ...ROUND, meeting_url: "javascript:alert(2)" }],
    });
    renderAt("/applications/21");
    expect(await screen.findByText("javascript:alert(1)")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "javascript:alert(1)" })).not.toBeInTheDocument();
    await screen.findByRole("list", { name: "Interview rounds" });
    expect(screen.queryByRole("link", { name: "Meeting link" })).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it("keeps safe links clickable in a new tab without opener access", async () => {
    detailBackend({ application: { ...DETAIL, application_url: "https://jobs.example.com/1" }, rounds: [ROUND] });
    renderAt("/applications/21");
    const link = await screen.findByRole("link", { name: "https://jobs.example.com/1" });
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(await screen.findByRole("link", { name: "Meeting link" })).toHaveAttribute("href", "https://meet.example.com/abc");
  });
});
