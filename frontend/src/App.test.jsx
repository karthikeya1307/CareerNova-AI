import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "./App";
import { ConfirmProvider, useConfirm } from "./context/ConfirmContext";
import { server } from "./test/server";

const student = { user_id: 1, first_name: "Test", last_name: "Student", role: "student", email: "s@example.com" };
const admin = { ...student, user_id: 2, first_name: "Ada", role: "admin" };

function renderAt(path, authProps = { restoreSession: false }) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={authProps} />
    </MemoryRouter>,
  );
}

describe("routing smoke test", () => {
  it("shows the backend health through the API layer", async () => {
    renderAt("/health");
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("Database connection successful")).toBeInTheDocument();
  });

  it("shows a friendly error when the backend is unreachable", async () => {
    server.use(http.get("/api/health", () => HttpResponse.error()));
    renderAt("/health");
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });

  it("redirects signed-out users to /login and remembers where they were going", async () => {
    renderAt("/resumes?tab=skills");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText(/return to \/resumes\?tab=skills/)).toBeInTheDocument();
  });

  it("shows protected pages to signed-in users", async () => {
    renderAt("/resumes", { initialUser: student });
    expect(await screen.findByRole("heading", { name: "Resumes" })).toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  });

  it("keeps students out of admin pages", async () => {
    renderAt("/admin/users", { initialUser: student });
    expect(await screen.findByText("You don't have access to this page")).toBeInTheDocument();
  });

  it("lets administrators open admin pages and shows the admin menu", async () => {
    renderAt("/admin/index", { initialUser: admin });
    expect(await screen.findByRole("heading", { name: "Search index" })).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("restores a session from a stored refresh token", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "stored");
    server.use(
      http.post("/api/auth/refresh", async ({ request }) => {
        const body = await request.json();
        return body.refresh_token === "stored"
          ? HttpResponse.json({ access_token: "a1", refresh_token: "rotated", token_type: "bearer", expires_in: 900, refresh_expires_in: 1 })
          : HttpResponse.json({ detail: "Invalid refresh token" }, { status: 401 });
      }),
      http.get("/api/auth/me", ({ request }) =>
        request.headers.get("authorization") === "Bearer a1" ? HttpResponse.json(student) : HttpResponse.json({}, { status: 401 }),
      ),
    );
    renderAt("/matches", {});
    expect(await screen.findByRole("heading", { name: "Matches" })).toBeInTheDocument();
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBe("rotated"); // rotation saved
  });

  describe("session restore when the refresh fails", () => {
    it("HTTP 401: clears the stored token and sends the user to sign in", async () => {
      window.localStorage.setItem("acc.refresh_token", "revoked");
      server.use(http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Invalid refresh token" }, { status: 401 })));
      renderAt("/matches", {});
      expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
      expect(window.localStorage.getItem("acc.refresh_token")).toBeNull();
    });

    it.each([
      ["network failure", () => HttpResponse.error(), "Cannot reach the server"],
      ["HTTP 5xx", () => HttpResponse.json({ detail: "Service temporarily unavailable" }, { status: 503 }), "Service temporarily unavailable"],
    ])("%s: keeps the stored token, shows the error and can try again", async (_name, failure, message) => {
      window.localStorage.setItem("acc.refresh_token", "valid");
      let refreshCalls = 0;
      let serverUp = false;
      server.use(
        http.post("/api/auth/refresh", () => {
          refreshCalls += 1;
          return serverUp
            ? HttpResponse.json({ access_token: "a1", refresh_token: "rotated", token_type: "bearer", expires_in: 900, refresh_expires_in: 1 })
            : failure();
        }),
        http.get("/api/auth/me", () => HttpResponse.json(student)),
      );
      renderAt("/matches", {});

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument(); // not signed out
      expect(window.localStorage.getItem("acc.refresh_token")).toBe("valid");
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(refreshCalls).toBe(1); // no automatic retry loop

      serverUp = true;
      await userEvent.click(screen.getByRole("button", { name: "Try again" }));
      expect(await screen.findByRole("heading", { name: "Matches" })).toBeInTheDocument();
      expect(refreshCalls).toBe(2);
      expect(window.localStorage.getItem("acc.refresh_token")).toBe("rotated"); // Remember me kept
    });
  });

  it("signs out: revokes the session and clears the stored token", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "r1");
    let revoked = null;
    server.use(
      http.post("/api/auth/logout", async ({ request }) => {
        revoked = (await request.json()).refresh_token;
        return HttpResponse.json({ message: "Logged out" });
      }),
    );
    renderAt("/profile", { initialUser: student, restoreSession: false });
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(revoked).toBe("r1");
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
  });

  it("shows a 404 page for unknown routes", () => {
    renderAt("/does-not-exist");
    expect(screen.getByText("Page not found")).toBeInTheDocument();
  });
});

describe("confirmation dialog", () => {
  function Demo({ onResult }) {
    const confirm = useConfirm();
    return (
      <button type="button" onClick={async () => onResult(await confirm({ title: "Rebuild index?", confirmLabel: "Rebuild", requireText: "REBUILD" }))}>
        open
      </button>
    );
  }

  it("requires the typed word before confirming", async () => {
    const results = [];
    render(
      <ConfirmProvider>
        <Demo onResult={(r) => results.push(r)} />
      </ConfirmProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByText("open"));
    const rebuild = screen.getByRole("button", { name: "Rebuild" });
    expect(rebuild).toBeDisabled();
    await user.type(screen.getByLabelText("Type REBUILD to confirm"), "REBUILD");
    expect(rebuild).toBeEnabled();
    await user.click(rebuild);
    await waitFor(() => expect(results).toEqual([true]));
  });

  it("resolves false on cancel or Escape", async () => {
    const results = [];
    render(
      <ConfirmProvider>
        <Demo onResult={(r) => results.push(r)} />
      </ConfirmProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByText("open"));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(results).toEqual([false]));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("answers a pending dialog with false when a second one replaces it", async () => {
    let confirm;
    function Capture() {
      confirm = useConfirm();
      return null;
    }
    render(
      <ConfirmProvider>
        <Capture />
      </ConfirmProvider>,
    );
    const user = userEvent.setup();

    let first;
    act(() => {
      first = confirm({ title: "Rebuild index?", confirmLabel: "Rebuild", requireText: "REBUILD" });
    });
    await user.type(screen.getByLabelText("Type REBUILD to confirm"), "REBUILD");

    let second;
    act(() => {
      second = confirm({ title: "Delete everything?", confirmLabel: "Delete", requireText: "REBUILD" });
    });
    await expect(first).resolves.toBe(false); // the first caller is not left waiting

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Delete everything?");
    expect(screen.getByLabelText("Type REBUILD to confirm")).toHaveValue(""); // fresh state
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();

    await user.type(screen.getByLabelText("Type REBUILD to confirm"), "REBUILD");
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await expect(second).resolves.toBe(true);
  });
});
