import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { internshipBody, parseSkills, validateInternship } from "./AdminInternshipFormPage";
import { ACTION_LABEL, describeDetails } from "./AdminAuditPage";

// Fictional fixtures shaped like backend/schemas (test-only data). No real admin operation runs.
const admin = { user_id: 1, first_name: "Ada", last_name: "Admin", role: "admin", email: "ada@example.com", is_verified: true };
const superAdmin = { user_id: 9, first_name: "Sam", last_name: "Super", role: "super_admin", email: "sam@example.com", is_verified: true };
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const userRow = (id, extra = {}) => ({
  user_id: id, user_uuid: `00000000-0000-4000-8000-${String(id).padStart(12, "0")}`, first_name: `User${id}`, last_name: "Test",
  phone_number: "+910000000000", email: `user${id}@example.com`, role: "student", is_verified: true, created_at: "2026-11-01T09:00:00Z",
  is_active: true, last_login_at: null, ...extra,
});
const USERS = [userRow(1, { first_name: "Ada", last_name: "Admin", email: "ada@example.com", role: "admin" }), userRow(2), userRow(3, { is_verified: false }), userRow(4)];
const internship = (id, extra = {}) => ({
  internship_id: id, external_id: null, title: `Role ${id}`, company: `Company ${id}`, description: "Build things.", eligibility: null, location: "Pune",
  application_url: "https://example.com/apply", deadline: null, domain: "Data Science", work_mode: "Hybrid", duration_weeks: 12, stipend_per_month: 10000,
  stipend_currency: "INR", min_education: null, source: "dataset", is_active: true, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
  required_skills: ["Python", "SQL"], preferred_skills: ["Docker"], skills: [], ...extra,
});
const INDEX = {
  built: true, built_at: "2026-11-16T09:28:51+00:00", model_name: "all-MiniLM-L6-v2", model_revision: "abc123", dimension: 384, indexed_vectors: 118,
  configured_model: "all-MiniLM-L6-v2", model_matches_configuration: true, active_internships: 120, document_status_counts: { indexed: 118, pending: 2 }, stale: true,
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}
function renderAt(path, user = admin) {
  if (user) setAccessToken("access-token");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={{ initialUser: user, restoreSession: false }} />
      <LocationProbe />
    </MemoryRouter>,
  );
}
const location = () => screen.getByTestId("location").textContent;

// Records every request so tests can prove which calls were (and were not) made.
function backend({ users = USERS, items = [internship(11), internship(12, { is_active: false, title: "Old role" })], index = INDEX } = {}) {
  const calls = [];
  const log = async (request) => {
    let body = null;
    try {
      body = await request.clone().json();
    } catch {
      body = null;
    }
    const url = new URL(request.url);
    calls.push({ method: request.method, path: url.pathname, search: url.search, body });
  };
  server.use(
    http.get("/api/admin/users", async ({ request }) => {
      await log(request);
      const p = new URL(request.url).searchParams;
      const skip = Number(p.get("skip"));
      const q = (p.get("q") || "").toLowerCase();
      const matching = users.filter(
        (u) =>
          (!q || `${u.first_name} ${u.last_name} ${u.email}`.toLowerCase().includes(q)) &&
          (!p.get("role") || u.role === p.get("role")) &&
          (!p.get("is_active") || String(u.is_active !== false) === p.get("is_active")),
      );
      return HttpResponse.json(matching.slice(skip, skip + Number(p.get("limit"))));
    }),
    http.get("/api/admin/index/status", async ({ request }) => {
      await log(request);
      return HttpResponse.json(index);
    }),
    http.get("/api/internships/filters", () => HttpResponse.json({ domains: ["Data Science", "Web Development"], work_modes: ["Hybrid"], locations: ["Pune"] })),
    http.get("/api/internships/", async ({ request }) => {
      await log(request);
      const p = new URL(request.url).searchParams;
      const all = p.get("include_inactive") === "true";
      const domain = p.get("domain");
      const visible = items.filter((i) => (all || i.is_active) && (!domain || i.domain === domain));
      const total = domain === "Web Development" ? 3 : visible.length;
      return HttpResponse.json({ total, skip: Number(p.get("skip") || 0), limit: Number(p.get("limit") || 20), items: visible });
    }),
    http.get("/api/internships/:id", ({ params }) => {
      const found = items.find((i) => String(i.internship_id) === params.id);
      return found ? HttpResponse.json(found) : HttpResponse.json({ detail: "Internship not found" }, { status: 404 });
    }),
  );
  return calls;
}
const mutations = (calls) => calls.filter((c) => c.method !== "GET");

// ================================================================================================
describe("Admin access", () => {
  it("keeps students out of every admin page, including forms", async () => {
    backend();
    for (const path of ["/admin", "/admin/internships/new", "/admin/index"]) {
      const view = renderAt(path, student);
      expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Admin overview" })).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("sends signed-out visitors to sign in", async () => {
    renderAt("/admin/users", null);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/login?next=%2Fadmin%2Fusers"));
  });

  it("shows the backend's 403 clearly when the server refuses admin access", async () => {
    backend();
    server.use(http.get("/api/admin/users", () => HttpResponse.json({ detail: "Admin access required" }, { status: 403 })));
    renderAt("/admin/users");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The server refused access to the user list.");
    expect(alert).toHaveTextContent("Admin access required");
    expect(within(alert).queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("shows the admin section in the mobile navigation for administrators", async () => {
    backend();
    renderAt("/admin");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open navigation" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation" });
    expect(within(drawer).getByRole("link", { name: /Admin overview/ })).toHaveAttribute("href", "/admin");
    expect(within(drawer).getByRole("link", { name: /Manage internships/ })).toHaveAttribute("href", "/admin/internships");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
  });

  it("adds an admin shortcut to the dashboard for administrators only", async () => {
    backend();
    const view = renderAt("/");
    expect(await within(screen.getByRole("main")).findByRole("link", { name: "Admin overview" })).toHaveAttribute("href", "/admin");
    view.unmount();
    renderAt("/", student);
    await screen.findByRole("heading", { level: 1 });
    expect(within(screen.getByRole("main")).queryByRole("link", { name: "Admin overview" })).not.toBeInTheDocument();
  });
});

// ================================================================================================
describe("Admin overview", () => {
  it("computes counts from the backend's data and shows the index status, without changing anything", async () => {
    const calls = backend({ items: [internship(11), internship(12, { is_active: false }), internship(13, { domain: "Web Development" })] });
    renderAt("/admin");
    const users = (await screen.findByRole("heading", { name: "Users" })).closest("section");
    expect(await within(users).findByText("Registered users")).toBeInTheDocument();
    const stat = (section, label) => within(section).getByText(label).closest("div");
    expect(stat(users, "Registered users")).toHaveTextContent("4");
    expect(stat(users, "Students")).toHaveTextContent("3");
    expect(stat(users, "Admins")).toHaveTextContent("1");
    expect(stat(users, "Email verified")).toHaveTextContent("31 not verified");
    expect(within(users).getByText("All accounts are active.")).toBeInTheDocument(); // from is_active, not assumed

    const internships = screen.getByRole("heading", { name: "Internships" }).closest("section");
    await waitFor(() => expect(stat(internships, "All internships")).toHaveTextContent("3"));
    expect(stat(internships, "Active")).toHaveTextContent("2");
    expect(stat(internships, "Deactivated")).toHaveTextContent("1");
    const domains = await within(internships).findByRole("list", { name: "Active internships by domain" });
    expect(within(domains).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Web Development3", "Data Science1"]);

    const index = screen.getByRole("heading", { name: "Search index" }).closest("section");
    expect(await within(index).findByText("Built")).toBeInTheDocument();
    expect(within(index).getByText("Out of date")).toBeInTheDocument();
    expect(screen.getByText(/Skill management and skill counts/)).toBeInTheDocument();
    expect(mutations(calls)).toEqual([]);
  });

  it("retries a failed section", async () => {
    backend();
    let fail = true;
    server.use(http.get("/api/admin/index/status", () => {
      if (fail) {
        fail = false;
        return HttpResponse.json({ detail: "Service unavailable" }, { status: 503 });
      }
      return HttpResponse.json(INDEX);
    }));
    renderAt("/admin");
    const user = userEvent.setup();
    const index = (await screen.findByRole("heading", { name: "Search index" })).closest("section");
    await user.click(await within(index).findByRole("button", { name: "Try again" }));
    expect(await within(index).findByText("Built")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Admin users", () => {
  it("lists users without phone numbers, searches on the server and pages through results", async () => {
    const many = [USERS[0], ...Array.from({ length: 59 }, (_, i) => userRow(i + 2))];
    const calls = backend({ users: many });
    renderAt("/admin/users");
    const user = userEvent.setup();
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(51); // header + 50
    expect(within(table).queryByText("+910000000000")).not.toBeInTheDocument();
    expect(within(table).getByText("(you)")).toBeInTheDocument();
    expect(within(table).getByText("You can't change your own account")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Search by name or email"), "user12@");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(location()).toBe("/admin/users?q=user12%40"));
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2));
    await user.clear(screen.getByLabelText("Search by name or email"));
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(location()).toBe("/admin/users"));
    await user.selectOptions(screen.getByLabelText("Role"), "admin");
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2));
    await user.selectOptions(screen.getByLabelText("Role"), "");

    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(location()).toBe("/admin/users?skip=50"));
    expect(await screen.findByText("Users 51–60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    const searches = calls.filter((c) => c.path === "/api/admin/users").map((c) => c.search);
    expect(searches).toContain("?skip=0&limit=50&q=user12%40");
    expect(searches).toContain("?skip=0&limit=50&role=admin");
    expect(searches.at(-1)).toBe("?skip=50&limit=50");
  });

  it("lets only the super admin change roles, after confirmation, and shows the backend's errors", async () => {
    const calls = backend({ users: [userRow(9, { ...superAdmin }), ...USERS] });
    let fail = true;
    server.use(http.patch("/api/admin/users/:id/role", async ({ params, request }) => {
      const body = await request.json();
      calls.push({ method: "PATCH", path: `/api/admin/users/${params.id}/role`, body });
      if (fail) {
        fail = false;
        return HttpResponse.json({ detail: "User not found" }, { status: 404 });
      }
      return HttpResponse.json(userRow(Number(params.id), { role: body.role }));
    }));
    renderAt("/admin/users", superAdmin);
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: "Make User2 Test an admin" });
    await user.click(button);
    expect(screen.getByRole("dialog")).toHaveTextContent("Administrators can see every user");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(mutations(calls)).toEqual([]);

    await user.click(button);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Make admin" }));
    expect(await screen.findByText("User not found")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getAllByText("Student").length).toBe(3);

    await user.click(button);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Make admin" }));
    expect(await screen.findByRole("button", { name: "Make User2 Test a student" })).toBeInTheDocument();
    expect(mutations(calls).map((c) => c.body)).toEqual([{ role: "admin" }, { role: "admin" }]);
    // The super admin's own row is protected.
    const own = within(screen.getByRole("table")).getByText("Sam Super").closest("tr");
    expect(within(own).getByText("Protected account")).toBeInTheDocument();
    expect(within(own).queryByRole("button")).not.toBeInTheDocument();
  });

  it("gives admins no role changes and no control over other admins or the super admin", async () => {
    backend({ users: [USERS[0], userRow(5, { role: "admin", first_name: "Other" }), userRow(9, { ...superAdmin }), userRow(2)] });
    renderAt("/admin/users");
    const table = await screen.findByRole("table");
    expect(within(table).queryByRole("button", { name: /Make .* an admin/ })).not.toBeInTheDocument();
    const otherAdmin = within(table).getByText("Other Test").closest("tr");
    expect(within(otherAdmin).getByText("Only the super admin manages administrators")).toBeInTheDocument();
    expect(within(otherAdmin).queryByRole("button")).not.toBeInTheDocument();
    const superRow = within(table).getByText("Sam Super").closest("tr");
    expect(within(superRow).getByText("Protected")).toBeInTheDocument();
    expect(within(superRow).queryByRole("button")).not.toBeInTheDocument();
    expect(within(table).getByRole("button", { name: "Deactivate User2 Test" })).toBeInTheDocument();
  });

  it("deactivates and reactivates a student only after confirmation", async () => {
    const calls = backend();
    server.use(
      http.post("/api/admin/users/:id/deactivate", ({ params }) => {
        calls.push({ method: "POST", path: `/api/admin/users/${params.id}/deactivate` });
        return HttpResponse.json(userRow(Number(params.id), { is_active: false }));
      }),
      http.post("/api/admin/users/:id/reactivate", ({ params }) => {
        calls.push({ method: "POST", path: `/api/admin/users/${params.id}/reactivate` });
        return HttpResponse.json(userRow(Number(params.id), { is_active: true }));
      }),
    );
    renderAt("/admin/users");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Deactivate User2 Test" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("signed out everywhere");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(mutations(calls)).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Deactivate User2 Test" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate" }));
    const row = (await screen.findByRole("button", { name: "Reactivate User2 Test" })).closest("tr");
    expect(within(row).getByText("Deactivated")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Reactivate User2 Test" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reactivate" }));
    expect(await screen.findByRole("button", { name: "Deactivate User2 Test" })).toBeInTheDocument();
    expect(mutations(calls).map((c) => c.path)).toEqual(["/api/admin/users/2/deactivate", "/api/admin/users/2/reactivate"]);
    expect(within(screen.getByRole("table")).getByText("User3 Test").closest("tr")).toHaveTextContent("Pending activation");
  });

  it("adds a pending account without any password field and shows the backend's errors", async () => {
    const calls = backend();
    let conflict = true;
    server.use(http.post("/api/admin/users", async ({ request }) => {
      const body = await request.json();
      calls.push({ method: "POST", path: "/api/admin/users", body });
      if (conflict) {
        conflict = false;
        return HttpResponse.json({ detail: "An account with this email already exists" }, { status: 409 });
      }
      return HttpResponse.json(userRow(50, { ...body, is_verified: false }), { status: 201 });
    }));
    renderAt("/admin/users");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add user" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Role")).not.toBeInTheDocument(); // admins add students only
    await user.click(within(dialog).getByRole("button", { name: "Create account" }));
    expect(within(dialog).getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(mutations(calls)).toEqual([]);

    await user.type(within(dialog).getByLabelText("First name"), "Anu");
    await user.type(within(dialog).getByLabelText("Last name"), "Menon");
    await user.type(within(dialog).getByLabelText("Email"), "anu@example.com");
    await user.click(within(dialog).getByRole("button", { name: "Create account" }));
    expect(await within(dialog).findByText("An account with this email already exists")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mutations(calls).map((c) => c.body)).toEqual([
      { first_name: "Anu", last_name: "Menon", email: "anu@example.com", role: "student" },
      { first_name: "Anu", last_name: "Menon", email: "anu@example.com", role: "student" },
    ]);
  });

  it("lets the super admin choose the admin role when adding a user", async () => {
    backend({ users: [userRow(9, { ...superAdmin })] });
    renderAt("/admin/users", superAdmin);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add user" }));
    expect(within(screen.getByRole("dialog")).getByLabelText("Role")).toHaveValue("student");
  });
});

describe("Admin audit log", () => {
  it("lists audit events newest first with readable details and filters by action", async () => {
    const calls = backend();
    const events = [
      { event_id: 3, actor_user_id: 9, actor_role: "super_admin", action: "user.role_change", target_user_id: 2, target_label: "User2 Test <user2@example.com>",
        details: { from: "student", to: "admin" }, ip_address: "127.0.0.1", created_at: "2026-11-19T10:00:00Z" },
      { event_id: 2, actor_user_id: null, actor_role: null, action: "auth.login_locked", target_user_id: null, target_label: "unknown account",
        details: { limit: 5, window_minutes: 15 }, ip_address: "127.0.0.1", created_at: "2026-11-19T09:00:00Z" },
      { event_id: 1, actor_user_id: 1, actor_role: "admin", action: "user.deactivate", target_user_id: 3, target_label: "User3 Test <user3@example.com>",
        details: { signed_out_devices: 2 }, ip_address: "127.0.0.1", created_at: "2026-11-19T08:00:00Z" },
    ];
    server.use(http.get("/api/admin/audit-events", ({ request }) => {
      const url = new URL(request.url);
      calls.push({ method: "GET", path: url.pathname, search: url.search });
      const action = url.searchParams.get("action");
      const items = events.filter((e) => !action || e.action === action);
      return HttpResponse.json({ total: items.length, skip: 0, limit: 50, items });
    }));
    renderAt("/admin/audit");
    const user = userEvent.setup();
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[1].textContent)).toEqual(["Role changed", "Sign-in locked", "User deactivated"]);
    expect(rows[0]).toHaveTextContent("student → admin");
    expect(rows[0]).toHaveTextContent("User #9 (super_admin)");
    expect(rows[1]).toHaveTextContent("5 failed attempts within 15 minutes");
    expect(rows[1]).toHaveTextContent("System");
    expect(rows[2]).toHaveTextContent("Signed out of 2 device(s)");
    expect(screen.getByText("3 events")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Action"), "user.deactivate");
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2));
    expect(calls.filter((c) => c.path === "/api/admin/audit-events").at(-1).search).toBe("?skip=0&limit=50&action=user.deactivate");
  });

  it("labels every backend audit action", () => {
    // backend/services/audit.ACTIONS
    const backendActions = ["superadmin.bootstrap", "user.create", "user.role_change", "user.deactivate", "user.reactivate", "user.invite",
      "user.invite_revoke", "user.activate", "auth.login_locked", "index.rebuild", "internship.create", "internship.update",
      "internship.deactivate", "internship.verify"];
    expect(Object.keys(ACTION_LABEL).sort()).toEqual([...backendActions].sort());
    expect(describeDetails({ action: "user.activate", details: { via: "invitation" } })).toBe("Set own password via invitation");
    expect(describeDetails({ action: "user.invite", details: { resend: true } })).toBe("New link sent (earlier link revoked)");
  });

  it("keeps students out of the audit log", async () => {
    backend();
    renderAt("/admin/audit", student);
    expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });
});

// ================================================================================================
describe("Admin internships", () => {
  it("lists active and deactivated internships with the backend's filters", async () => {
    const calls = backend();
    renderAt("/admin/internships");
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Internships" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Deactivated")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/internships/").search).toBe("?include_inactive=true&skip=0&limit=20");

    await user.click(screen.getByLabelText("Include deactivated"));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Internships" })).getAllByRole("listitem")).toHaveLength(1));
    await user.type(screen.getByLabelText("Search by title, company or description"), "role");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.selectOptions(await screen.findByLabelText("Domain"), "Data Science");
    await waitFor(() => expect(location()).toBe("/admin/internships?q=role&domain=Data+Science&inactive=0"));
    expect(calls.at(-1).search).toBe("?q=role&domain=Data+Science&skip=0&limit=20");
  });

  it("deactivates and reactivates only after confirmation", async () => {
    const calls = backend();
    server.use(
      http.delete("/api/internships/:id", ({ params }) => {
        calls.push({ method: "DELETE", path: `/api/internships/${params.id}` });
        return new HttpResponse(null, { status: 204 });
      }),
      http.patch("/api/internships/:id", async ({ params, request }) => {
        calls.push({ method: "PATCH", path: `/api/internships/${params.id}`, body: await request.json() });
        return HttpResponse.json(internship(Number(params.id)));
      }),
    );
    renderAt("/admin/internships");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Deactivate Role 11 at Company 11" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Nothing is deleted: you can reactivate it later.");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(mutations(calls)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Deactivate Role 11 at Company 11" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(mutations(calls)).toEqual([{ method: "DELETE", path: "/api/internships/11" }]));

    await user.click(screen.getByRole("button", { name: "Reactivate Old role at Company 12" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reactivate" }));
    await waitFor(() => expect(mutations(calls)[1]).toEqual({ method: "PATCH", path: "/api/internships/12", body: { is_active: true } }));
  });

  it("validates and creates an internship", async () => {
    const calls = backend();
    server.use(http.post("/api/internships/", async ({ request }) => {
      const body = await request.json();
      calls.push({ method: "POST", path: "/api/internships/", body });
      return HttpResponse.json(internship(50, body), { status: 201 });
    }));
    renderAt("/admin/internships/new");
    const user = userEvent.setup();
    const form = await screen.findByRole("form", { name: "Add internship" });
    await user.type(within(form).getByLabelText("Application link"), "example.com");
    await user.clear(within(form).getByLabelText("Currency"));
    await user.type(within(form).getByLabelText("Currency"), "rs");
    await user.click(within(form).getByRole("button", { name: "Add internship" }));
    expect(within(form).getByText("Enter the title.")).toBeInTheDocument();
    expect(within(form).getByText("Enter the company.")).toBeInTheDocument();
    expect(within(form).getByText("Start the link with http:// or https://.")).toBeInTheDocument();
    expect(within(form).getByText("Use a 3-letter code such as INR.")).toBeInTheDocument();
    expect(mutations(calls)).toEqual([]);

    await user.type(within(form).getByLabelText("Title"), "  ML Intern ");
    await user.type(within(form).getByLabelText("Company"), "Nimbus");
    await user.clear(within(form).getByLabelText("Application link"));
    await user.type(within(form).getByLabelText("Application link"), "https://nimbus.example/jobs/1");
    await user.clear(within(form).getByLabelText("Currency"));
    await user.type(within(form).getByLabelText("Currency"), "inr");
    await user.selectOptions(within(form).getByLabelText("Work mode"), "Remote");
    await user.type(within(form).getByLabelText(/^Required skills/), "Python, SQL, python");
    await user.click(within(form).getByRole("button", { name: "Add internship" }));
    await waitFor(() => expect(location()).toBe("/admin/internships"));
    expect(mutations(calls)).toEqual([{
      method: "POST", path: "/api/internships/",
      body: { title: "ML Intern", company: "Nimbus", application_url: "https://nimbus.example/jobs/1", work_mode: "Remote", stipend_currency: "INR", required_skills: ["Python", "SQL"] },
    }]);
  });

  it("edits only the changed fields and reports when nothing changed", async () => {
    const calls = backend();
    server.use(http.patch("/api/internships/:id", async ({ params, request }) => {
      const body = await request.json();
      calls.push({ method: "PATCH", path: `/api/internships/${params.id}`, body });
      return HttpResponse.json(internship(11, body));
    }));
    renderAt("/admin/internships/11/edit");
    const user = userEvent.setup();
    const form = await screen.findByRole("form", { name: "Edit internship" });
    expect(within(form).getByLabelText("Title")).toHaveValue("Role 11");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Nothing has changed.")).toBeInTheDocument();
    expect(mutations(calls)).toEqual([]);

    await user.clear(within(form).getByLabelText("Title"));
    await user.type(within(form).getByLabelText("Title"), "Senior Role 11");
    await user.clear(within(form).getByLabelText("Location"));
    await user.clear(within(form).getByLabelText(/^Preferred skills/));
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mutations(calls)).toEqual([{ method: "PATCH", path: "/api/internships/11", body: { title: "Senior Role 11", location: null, preferred_skills: [] } }]));
  });

  it("shows the backend's validation errors and a not-found state", async () => {
    backend();
    server.use(http.post("/api/internships/", () => HttpResponse.json({ detail: [{ loc: ["body", "title"], msg: "Value error, must not be blank", type: "value_error" }] }, { status: 422 })));
    const view = renderAt("/admin/internships/new");
    const user = userEvent.setup();
    const form = await screen.findByRole("form", { name: "Add internship" });
    await user.type(within(form).getByLabelText("Title"), "A");
    await user.type(within(form).getByLabelText("Company"), "B");
    await user.click(within(form).getByRole("button", { name: "Add internship" }));
    expect(await within(form).findByText("The internship couldn't be saved")).toBeInTheDocument();
    view.unmount();
    renderAt("/admin/internships/999/edit");
    expect(await screen.findByText("Internship not found")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Admin search index", () => {
  it("shows the index status read-only", async () => {
    const calls = backend();
    renderAt("/admin/index");
    expect(await screen.findByText("Out of date")).toBeInTheDocument();
    expect(screen.getByText("Model matches configuration")).toBeInTheDocument();
    expect(screen.getByText("Indexed vectors").nextSibling).toHaveTextContent("118");
    expect(screen.getByText("Index model").nextSibling).toHaveTextContent("all-MiniLM-L6-v2 (abc123)");
    expect(within(screen.getByRole("list", { name: "Documents by status" })).getByText("Pending: 2")).toBeInTheDocument();
    expect(mutations(calls)).toEqual([]);
  });

  it("rebuilds only after typing REBUILD, and can be cancelled", async () => {
    const calls = backend();
    server.use(http.post("/api/admin/index/rebuild", () => {
      calls.push({ method: "POST", path: "/api/admin/index/rebuild" });
      return HttpResponse.json({ indexed: 120, deactivated_documents: 3, built_at: "2026-11-17T10:00:00+00:00", model_name: "all-MiniLM-L6-v2", dimension: 384 });
    }));
    renderAt("/admin/index");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Rebuild search index" }));
    let dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("It can take several minutes");
    expect(within(dialog).getByRole("button", { name: "Rebuild index" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(mutations(calls)).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Rebuild search index" }));
    dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Type REBUILD to confirm"), "REBUILD");
    await user.click(within(dialog).getByRole("button", { name: "Rebuild index" }));
    expect(await screen.findByText(/120 internships indexed, 3 deactivated documents removed/)).toBeInTheDocument();
    expect(mutations(calls)).toEqual([{ method: "POST", path: "/api/admin/index/rebuild" }]);
  });

  it.each([
    [409, "A search index rebuild is already running.", "A rebuild is already running."],
    [503, "The embedding model could not be loaded.", "Embeddings are unavailable."],
  ])("explains a %s from the rebuild", async (status, detail, title) => {
    backend();
    server.use(http.post("/api/admin/index/rebuild", () => HttpResponse.json({ detail }, { status })));
    renderAt("/admin/index");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Rebuild search index" }));
    await user.type(screen.getByLabelText("Type REBUILD to confirm"), "REBUILD");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Rebuild index" }));
    const alert = await screen.findByText(title);
    expect(alert.closest("[role=alert]")).toHaveTextContent(detail);
  });

  it("sends a single rebuild request while one is running", async () => {
    const calls = backend();
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    server.use(http.post("/api/admin/index/rebuild", async () => {
      calls.push({ method: "POST" });
      await held;
      return HttpResponse.json({ indexed: 1, deactivated_documents: 0, built_at: "2026-11-17T10:00:00+00:00", model_name: "m", dimension: 3 });
    }));
    renderAt("/admin/index");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Rebuild search index" }));
    await user.type(screen.getByLabelText("Type REBUILD to confirm"), "REBUILD");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Rebuild index" }));
    const running = await screen.findByRole("button", { name: /Rebuilding/ });
    expect(running).toBeDisabled();
    expect(screen.getByText(/The server is rebuilding the index/)).toBeInTheDocument();
    release();
    expect(await screen.findByText(/1 internships indexed/)).toBeInTheDocument();
    expect(mutations(calls)).toHaveLength(1);
  });
});

describe("Admin helpers", () => {
  it("parses skills and builds request bodies like the backend expects", () => {
    expect(parseSkills("Python, SQL\npython,  , Docker")).toEqual(["Python", "SQL", "Docker"]);
    const blank = { title: "", company: "", description: "", eligibility: "", location: "", application_url: "", deadline: "", domain: "", work_mode: "",
      duration_weeks: "0", stipend_per_month: "-5", stipend_currency: "INR", min_education: "", required_skills: Array.from({ length: 31 }, (_, i) => `s${i}`).join(","), preferred_skills: "x".repeat(61) };
    expect(validateInternship(blank)).toEqual({
      title: "Enter the title.", company: "Enter the company.", duration_weeks: "Enter 1–104 weeks.", stipend_per_month: "Enter a whole number from 0 to 1,000,000.",
      required_skills: "Use at most 30 skills.", preferred_skills: "Each skill can have at most 60 characters.",
    });
    const original = internship(11);
    const form = { ...blank, title: "Role 11", company: "Company 11", description: "Build things.", location: "Pune", application_url: "https://example.com/apply",
      domain: "Data Science", work_mode: "Hybrid", duration_weeks: "12", stipend_per_month: "10000", required_skills: "Python, SQL", preferred_skills: "Docker" };
    expect(internshipBody(form, original)).toEqual({});
    expect(internshipBody({ ...form, stipend_per_month: "" }, original)).toEqual({ stipend_per_month: null });
  });
});

// ================================================================================================
describe("Admin invitations", () => {
  const invitation = (extra = {}) => ({
    invitation_id: 4, status: "pending", delivery_status: "sent", delivery_error: null,
    created_at: "2026-11-19T09:00:00Z", expires_at: "2026-11-22T09:00:00Z", ...extra,
  });

  it("shows each pending account's invitation and email status", async () => {
    backend({ users: [USERS[0], userRow(3, { is_verified: false, invitation: invitation() }),
      userRow(4, { is_verified: false, invitation: invitation({ delivery_status: "failed", delivery_error: "auth_failed" }) }),
      userRow(5, { is_verified: false, invitation: invitation({ status: "expired", delivery_status: "outboxed" }) }),
      userRow(6, { is_verified: false, invitation: null })] });
    renderAt("/admin/users");
    const table = await screen.findByRole("table");
    const row = (name) => within(table).getByText(name).closest("tr");
    expect(row("User3 Test")).toHaveTextContent("Invitation sent · email sent");
    expect(row("User4 Test")).toHaveTextContent("Invitation sent · email failed");
    expect(row("User5 Test")).toHaveTextContent("Invitation expired");
    expect(row("User6 Test")).toHaveTextContent("No invitation sent");
    expect(within(row("User3 Test")).getByRole("button", { name: "Resend invitation to User3 Test" })).toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: "Resend invitation to Ada Admin" })).not.toBeInTheDocument();
  });

  it("re-sends an invitation only after confirmation and reports the rate limit", async () => {
    const calls = backend({ users: [USERS[0], userRow(3, { is_verified: false, invitation: invitation({ delivery_status: "failed" }) })] });
    let limited = true;
    server.use(http.post("/api/admin/users/:id/invitation", ({ params }) => {
      calls.push({ method: "POST", path: `/api/admin/users/${params.id}/invitation` });
      if (limited) {
        limited = false;
        return HttpResponse.json({ detail: { code: "cooldown", message: "An invitation was just sent. Try again in 42 seconds." } },
          { status: 429, headers: { "Retry-After": "42" } });
      }
      return HttpResponse.json(userRow(3, { is_verified: false, invitation: invitation({ invitation_id: 5 }) }));
    }));
    renderAt("/admin/users");
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: "Resend invitation to User3 Test" });
    await user.click(button);
    expect(screen.getByRole("dialog")).toHaveTextContent("Any earlier link stops working");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(mutations(calls)).toEqual([]);

    await user.click(button);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("An invitation was just sent. Try again in 42 seconds.")).toBeInTheDocument();
    await user.click(button);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send invitation" }));
    await waitFor(() => expect(within(screen.getByRole("table")).getByText("User3 Test").closest("tr")).toHaveTextContent("Invitation sent · email sent"));
    expect(mutations(calls).map((c) => c.path)).toEqual(["/api/admin/users/3/invitation", "/api/admin/users/3/invitation"]);
  });
});

describe("Admin overview: account status", () => {
  it("counts deactivated accounts from is_active", async () => {
    backend({ users: [...USERS.slice(0, 3), userRow(4, { is_active: false })] });
    renderAt("/admin");
    const users = (await screen.findByRole("heading", { name: "Users" })).closest("section");
    expect(await within(users).findByText("1 deactivated account.")).toBeInTheDocument();
  });
});
