import { StrictMode } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { server } from "../../test/server";

// Every request is answered by MSW; an unhandled request fails the test (src/test/setup.js).
// No test reaches a real backend, database or mail server.

const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const REFRESH = "refresh-token-".padEnd(48, "x");
const TOKENS = { access_token: "access-1", refresh_token: REFRESH, token_type: "bearer", expires_in: 900, refresh_expires_in: 2592000 };
const VERIFY_TOKEN = "v".repeat(43);
const RESET_TOKEN = "r".repeat(43);

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderAt(path, authProps = { restoreSession: false }, { strict = false } = {}) {
  const tree = (
    <MemoryRouter initialEntries={[path]}>
      <App authProps={authProps} />
      <LocationProbe />
    </MemoryRouter>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

const location = () => screen.getByTestId("location").textContent;

// The dashboard's h1 is a time-of-day greeting for the signed-in student.
const findDashboard = () => screen.findByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening), Asha$/ });

// Records request bodies so tests can assert exactly what was sent.
function capture(method, path, respond) {
  const calls = [];
  server.use(
    http[method](path, async ({ request }) => {
      const url = new URL(request.url);
      const body = method === "get" ? Object.fromEntries(url.searchParams) : await request.json();
      calls.push(body);
      return respond(body, calls.length);
    }),
  );
  return calls;
}

function signedInBackend() {
  const login = capture("post", "/api/auth/login", () => HttpResponse.json(TOKENS));
  server.use(
    http.get("/api/auth/me", ({ request }) =>
      request.headers.get("authorization") === "Bearer access-1"
        ? HttpResponse.json(student)
        : HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 }),
    ),
  );
  return login;
}

async function fillLogin(user, email = "asha@example.com", password = "Career2026") {
  await user.type(screen.getByLabelText("Email address"), email);
  await user.type(screen.getByLabelText("Password"), password);
}

// ================================================================================================
describe("Sign in", () => {
  it("validates before calling the API and focuses the first problem", async () => {
    const login = capture("post", "/api/auth/login", () => HttpResponse.json(TOKENS));
    renderAt("/login");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Email address")).toHaveFocus());
    expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-invalid", "true");
    expect(login).toHaveLength(0);
  });

  it("signs in, keeps the refresh token in sessionStorage and shows no admin menu", async () => {
    const login = signedInBackend();
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user, "  asha@example.com  ");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await findDashboard()).toBeInTheDocument();
    expect(location()).toBe("/");
    expect(login).toEqual([{ email: "asha@example.com", password: "Career2026" }]);
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBe(REFRESH);
    expect(window.localStorage.getItem("acc.refresh_token")).toBeNull();
    expect(screen.getByRole("button", { name: /^Asha Rao\s*, account menu$/ })).toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Search index" })).not.toBeInTheDocument();
  });

  it("uses localStorage only when Remember me is ticked", async () => {
    signedInBackend();
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByLabelText("Remember me"));
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await findDashboard();
    expect(window.localStorage.getItem("acc.refresh_token")).toBe(REFRESH);
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
  });

  it("returns to a safe ?next= page after signing in", async () => {
    signedInBackend();
    renderAt(`/login?next=${encodeURIComponent("/applications?status=APPLIED")}`);
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Applications" })).toBeInTheDocument();
    expect(location()).toBe("/applications?status=APPLIED");
  });

  it.each(["//evil.example", "https://evil.example", "/\\evil.example", "javascript:alert(1)"])(
    "ignores an unsafe ?next= (%s) and goes to the dashboard",
    async (next) => {
      signedInBackend();
      renderAt(`/login?next=${encodeURIComponent(next)}`);
      const user = userEvent.setup();
      await fillLogin(user);
      await user.click(screen.getByRole("button", { name: "Sign in" }));
      expect(await findDashboard()).toBeInTheDocument();
      expect(location()).toBe("/");
    },
  );

  it("shows a clear message for wrong credentials and clears the password", async () => {
    capture("post", "/api/auth/login", () => HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 }));
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user, "asha@example.com", "wrong-pass-1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Sign-in failed");
    expect(alert).toHaveTextContent("The email or password is incorrect");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(location()).toBe("/login");
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
  });

  it("explains a deactivated account without offering to resend verification", async () => {
    capture("post", "/api/auth/login", () =>
      HttpResponse.json({ detail: "This account has been deactivated. Contact an administrator." }, { status: 403 }),
    );
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user, "asha@example.com", "Correct-pass-1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This account has been deactivated");
    expect(screen.queryByRole("button", { name: "Resend verification email" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
  });

  it("shows the backend's message when too many sign-in attempts failed", async () => {
    capture("post", "/api/auth/login", () =>
      HttpResponse.json({ detail: "Too many failed sign-in attempts. Try again in 15 minute(s)." }, { status: 429, headers: { "Retry-After": "900" } }),
    );
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user, "asha@example.com", "wrong-pass-1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Too many failed sign-in attempts. Try again in 15 minute(s).");
    expect(location()).toBe("/login");
  });

  it("explains an unverified email and can resend the verification link", async () => {
    const login = capture("post", "/api/auth/login", () =>
      HttpResponse.json({ detail: "Please verify your email before logging in." }, { status: 403 }),
    );
    const resend = capture("post", "/api/auth/resend-verification", () =>
      HttpResponse.json({ message: "If an unverified account exists with this email, a new verification link will be sent." }),
    );
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Verify your email to sign in.")).toBeInTheDocument();
    const resendButton = screen.getByRole("button", { name: "Resend verification email" });
    expect(resendButton.closest("form").parentElement.closest("form")).toBeNull(); // forms never nest
    await user.click(resendButton);
    expect(await screen.findByText(/a new verification link will be sent/)).toBeInTheDocument();
    expect(resend).toEqual([{ email: "asha@example.com" }]);
    expect(login).toHaveLength(1); // resending did not re-submit the sign-in form
    expect(screen.getByRole("button", { name: /Resend available in \d+s/ })).toBeDisabled();
  });

  it("reports a connection failure", async () => {
    server.use(http.post("/api/auth/login", () => HttpResponse.error()));
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });

  it("does not keep tokens if the profile cannot be loaded after sign-in", async () => {
    capture("post", "/api/auth/login", () => HttpResponse.json(TOKENS));
    server.use(http.get("/api/auth/me", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    const logout = capture("post", "/api/auth/logout", () => HttpResponse.json({ message: "Logged out" }));
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in failed");
    await waitFor(() => expect(logout).toEqual([{ refresh_token: REFRESH }]));
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
    expect(location()).toBe("/login");
  });

  it("revokes the newest refresh token if the session cannot start after a token rotation", async () => {
    // /auth/me answers 401 twice: the client refreshes once (rotating the token) and retries.
    const ROTATED = "rotated-token-".padEnd(48, "y");
    capture("post", "/api/auth/login", () => HttpResponse.json(TOKENS));
    capture("post", "/api/auth/refresh", () => HttpResponse.json({ ...TOKENS, access_token: "access-2", refresh_token: ROTATED }));
    server.use(http.get("/api/auth/me", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })));
    const logout = capture("post", "/api/auth/logout", () => HttpResponse.json({ message: "Logged out" }));
    renderAt("/login");
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in failed");
    await waitFor(() => expect(logout).toEqual([{ refresh_token: ROTATED }]));
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
  });

  it("toggles password visibility accessibly", async () => {
    renderAt("/login");
    const user = userEvent.setup();
    const password = await screen.findByLabelText("Password");
    await user.type(password, "Career2026");
    expect(password).toHaveAttribute("type", "password");
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle);
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });

  it("sends signed-in users away from the sign-in page", async () => {
    renderAt(`/login?next=${encodeURIComponent("/matches")}`, { initialUser: student, restoreSession: false });
    expect(await screen.findByRole("heading", { name: "Matches" })).toBeInTheDocument();
    expect(location()).toBe("/matches");
  });

  it("starts the page with its own h1 and limits passwords to the backend's 128 characters", async () => {
    renderAt("/login");
    await screen.findByRole("heading", { name: "Sign in" });
    const firstHeading = document.querySelector("h1, h2, h3, h4, h5, h6");
    expect(firstHeading.tagName).toBe("H1");
    expect(firstHeading).toHaveTextContent("Sign in");
    expect(screen.getByLabelText("Password")).toHaveAttribute("maxlength", "128");
  });

  it("links to registration and password recovery", async () => {
    renderAt("/login");
    expect(await screen.findByRole("link", { name: "Create a student account" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute("href", "/forgot-password");
  });
});

// ================================================================================================
describe("Registration", () => {
  async function fillRegistration(user, overrides = {}) {
    const values = {
      "First name": " Asha ",
      "Last name": "Rao",
      "Email address": "Asha@Example.com",
      "Phone number": "+91 98765-43210",
      Password: "Career2026",
      "Confirm password": "Career2026",
      ...overrides,
    };
    for (const [label, value] of Object.entries(values)) {
      if (value) await user.type(screen.getByLabelText(label), value);
    }
  }

  it("validates every field before calling the API", async () => {
    const register = capture("post", "/api/auth/register", () => HttpResponse.json(student, { status: 201 }));
    renderAt("/register");
    const user = userEvent.setup();
    await fillRegistration(user, {
      "First name": "",
      "Email address": "asha@",
      "Phone number": "12345",
      Password: "short",
      "Confirm password": "different",
    });
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Enter your first name.")).toBeInTheDocument();
    expect(screen.getByText(/Enter a valid email address/)).toBeInTheDocument();
    expect(screen.getByText("Enter a valid phone number with 7 to 15 digits.")).toBeInTheDocument();
    expect(screen.getByText(/Password needs: 8 to 128 characters/)).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("First name")).toHaveFocus());
    expect(register).toHaveLength(0);
  });

  it("shows live password requirements", async () => {
    renderAt("/register");
    const user = userEvent.setup();
    const rules = await screen.findByRole("list", { name: "Password requirements" });
    expect(within(rules).getAllByText(/\(not met yet\)/)).toHaveLength(3);
    await user.type(screen.getByLabelText("Password"), "Career2026");
    expect(within(rules).getAllByText(/\(met\)/)).toHaveLength(3);
  });

  it("creates the account with clean data and shows the pending-verification state", async () => {
    const register = capture("post", "/api/auth/register", () => HttpResponse.json(student, { status: 201 }));
    renderAt("/register");
    const user = userEvent.setup();
    await fillRegistration(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText("asha@example.com")).toBeInTheDocument();
    expect(register).toEqual([
      { first_name: "Asha", last_name: "Rao", phone_number: "+919876543210", email: "asha@example.com", password: "Career2026" },
    ]);
    // A link was just issued; the backend ignores resends for 60 s, so the button starts cooling down.
    expect(screen.getByRole("button", { name: /Resend available in \d+s/ })).toBeDisabled();
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull(); // registration never signs in
  });

  it("flags an email that is already registered", async () => {
    capture("post", "/api/auth/register", () => HttpResponse.json({ detail: "Email is already registered" }, { status: 409 }));
    renderAt("/register");
    const user = userEvent.setup();
    await fillRegistration(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/An account with this email already exists/)).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("explains when the account was created but the email could not be sent", async () => {
    capture("post", "/api/auth/register", () =>
      HttpResponse.json({ detail: "Account created, but verification email could not be sent. Please try again later." }, { status: 503 }),
    );
    renderAt("/register");
    const user = userEvent.setup();
    await fillRegistration(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Account created — email not sent" })).toBeInTheDocument();
    expect(screen.getByText(/couldn't send the verification email/)).toBeInTheDocument();
  });

  it("maps backend validation errors onto the right field", async () => {
    capture("post", "/api/auth/register", () =>
      HttpResponse.json(
        { detail: [{ loc: ["body", "phone_number"], msg: "Value error, Enter a valid phone number with 7 to 15 digits.", type: "value_error" }] },
        { status: 422 },
      ),
    );
    renderAt("/register");
    const user = userEvent.setup();
    await fillRegistration(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Enter a valid phone number with 7 to 15 digits.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Phone number")).toHaveFocus());
  });
});

// ================================================================================================
describe("Email verification", () => {
  it("verifies once (even under StrictMode) and removes the token from the URL", async () => {
    const calls = capture("get", "/api/auth/verify-email", () =>
      HttpResponse.json({ message: "Email verified successfully. You can now log in." }),
    );
    renderAt(`/auth/verify-email?token=${VERIFY_TOKEN}`, { restoreSession: false }, { strict: true });
    expect(await screen.findByRole("heading", { name: "Email verified" })).toBeInTheDocument();
    expect(calls).toEqual([{ token: VERIFY_TOKEN }]);
    expect(location()).toBe("/auth/verify-email");
    expect(screen.getByRole("link", { name: "Continue to sign in" })).toHaveAttribute("href", "/login");
  });

  it.each([
    ["Verification link has expired", "Verification link expired"],
    ["This verification link has already been used", "Link already used"],
    ["Invalid verification link", "Invalid verification link"],
  ])("handles %j", async (detail, heading) => {
    const token = `${heading.replace(/\W/g, "")}`.padEnd(40, "z");
    capture("get", "/api/auth/verify-email", () => HttpResponse.json({ detail }, { status: 400 }));
    renderAt(`/auth/verify-email?token=${token}`);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("offers a new link when the old one expired", async () => {
    capture("get", "/api/auth/verify-email", () => HttpResponse.json({ detail: "Verification link has expired" }, { status: 400 }));
    const resend = capture("post", "/api/auth/resend-verification", () =>
      HttpResponse.json({ message: "If an unverified account exists with this email, a new verification link will be sent." }),
    );
    renderAt(`/auth/verify-email?token=${"e".repeat(40)}`);
    await screen.findByRole("heading", { name: "Verification link expired" });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email address"), "asha@example.com");
    await user.click(screen.getByRole("button", { name: "Resend verification email" }));
    expect(await screen.findByText(/a new verification link will be sent/)).toBeInTheDocument();
    expect(resend).toEqual([{ email: "asha@example.com" }]);
  });

  it("treats a missing or malformed token as invalid without calling the API", async () => {
    const calls = capture("get", "/api/auth/verify-email", () => HttpResponse.json({ message: "ok" }));
    renderAt("/auth/verify-email?token=short");
    expect(await screen.findByRole("heading", { name: "Invalid verification link" })).toBeInTheDocument();
    expect(calls).toHaveLength(0);
    await waitFor(() => expect(location()).toBe("/auth/verify-email"));
  });

  it("lets the user retry when the server is unavailable", async () => {
    const calls = capture("get", "/api/auth/verify-email", (_body, n) =>
      n === 1 ? HttpResponse.json({ detail: "boom" }, { status: 500 }) : HttpResponse.json({ message: "Email verified successfully." }),
    );
    renderAt(`/auth/verify-email?token=${"u".repeat(40)}`);
    expect(await screen.findByRole("heading", { name: "We couldn't verify your email right now" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Email verified" })).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });
});

// ================================================================================================
describe("Forgot password", () => {
  it("validates the email first", async () => {
    const calls = capture("post", "/api/auth/forgot-password", () => HttpResponse.json({ message: "ok" }));
    renderAt("/forgot-password");
    await userEvent.click(await screen.findByRole("button", { name: "Send reset instructions" }));
    expect(screen.getByText("Enter your email address.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("shows the same generic confirmation whether or not the account exists", async () => {
    const calls = capture("post", "/api/auth/forgot-password", () =>
      HttpResponse.json({ message: "If an account exists with this email, password reset instructions will be sent." }),
    );
    renderAt("/forgot-password");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email address"), "maybe@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset instructions" }));
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText(/If an account exists for/)).toBeInTheDocument();
    expect(calls).toEqual([{ email: "maybe@example.com" }]);
    expect(screen.getByRole("link", { name: "I have a reset code" })).toHaveAttribute("href", "/reset-password");
  });

  it("reports a server failure instead of claiming success", async () => {
    server.use(http.post("/api/auth/forgot-password", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderAt("/forgot-password");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email address"), "asha@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset instructions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't send reset instructions");
    expect(screen.queryByRole("heading", { name: "Check your email" })).not.toBeInTheDocument();
  });
});

// ================================================================================================
describe("Reset password", () => {
  async function fillPasswords(user, password = "NewCareer2026", confirm = password) {
    await user.type(screen.getByLabelText("New password"), password);
    await user.type(screen.getByLabelText("Confirm new password"), confirm);
  }

  it("uses a token from the link, removes it from the URL and resets the password", async () => {
    const calls = capture("post", "/api/auth/reset-password", () =>
      HttpResponse.json({ message: "Password reset successful. Please log in using your new password." }),
    );
    renderAt(`/reset-password?token=${RESET_TOKEN}`);
    expect(await screen.findByText("Reset code received from your link.")).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/reset-password"));
    const user = userEvent.setup();
    await fillPasswords(user);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    expect(calls).toEqual([{ token: RESET_TOKEN, new_password: "NewCareer2026" }]);
  });

  it("accepts a pasted reset code and validates the new password", async () => {
    const calls = capture("post", "/api/auth/reset-password", () => HttpResponse.json({ message: "ok" }));
    renderAt("/reset-password");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Update password" }));
    expect(screen.getByText("Enter the reset code from your email.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Reset code"), `  ${RESET_TOKEN}  `);
    await fillPasswords(user, "onlyletters", "onlyletters");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(screen.getByText(/Password needs: at least one number/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);

    await user.clear(screen.getByLabelText("New password"));
    await user.clear(screen.getByLabelText("Confirm new password"));
    await fillPasswords(user, "NewCareer2026", "NewCareer2025");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Confirm new password"));
    await user.type(screen.getByLabelText("Confirm new password"), "NewCareer2026");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    expect(calls).toEqual([{ token: RESET_TOKEN, new_password: "NewCareer2026" }]);
  });

  it.each([
    ["Password reset token has expired", "This reset code has expired.", "Reset codes expire after 30 minutes."],
    ["Invalid or already used password reset token", "This reset code is invalid or has already been used.", "Reset codes work once"],
  ])("handles %j", async (detail, fieldMessage, help) => {
    capture("post", "/api/auth/reset-password", () => HttpResponse.json({ detail }, { status: 400 }));
    renderAt("/reset-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Reset code"), RESET_TOKEN);
    await fillPasswords(user);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByText(fieldMessage)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(help))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new code" })).toHaveAttribute("href", "/forgot-password");
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("lets the user correct a malformed code that arrived in the link", async () => {
    const calls = capture("post", "/api/auth/reset-password", () => HttpResponse.json({ message: "ok" }));
    renderAt("/reset-password?token=short");
    const user = userEvent.setup();
    await fillPasswords(user);
    await user.click(await screen.findByRole("button", { name: "Update password" }));
    expect(calls).toHaveLength(0);
    const code = screen.getByLabelText("Reset code");
    await waitFor(() => expect(code).toHaveFocus());
    await user.clear(code);
    await user.type(code, RESET_TOKEN);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    expect(calls).toEqual([{ token: RESET_TOKEN, new_password: "NewCareer2026" }]);
  });

  it("lets the user paste a new code after the link's code is rejected", async () => {
    capture("post", "/api/auth/reset-password", (body) =>
      body.token === RESET_TOKEN
        ? HttpResponse.json({ detail: "Password reset token has expired" }, { status: 400 })
        : HttpResponse.json({ message: "ok" }),
    );
    renderAt(`/reset-password?token=${RESET_TOKEN}`);
    const user = userEvent.setup();
    await fillPasswords(user);
    await user.click(await screen.findByRole("button", { name: "Update password" }));
    expect(await screen.findByText("This reset code has expired.")).toBeInTheDocument();
    const code = screen.getByLabelText("Reset code");
    await user.clear(code);
    await user.type(code, "n".repeat(43));
    await fillPasswords(user);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
  });

  it("signs this browser out after a reset, because the backend revokes every session", async () => {
    window.sessionStorage.setItem("acc.refresh_token", REFRESH);
    capture("post", "/api/auth/reset-password", () => HttpResponse.json({ message: "ok" }));
    const logout = capture("post", "/api/auth/logout", () => HttpResponse.json({ message: "Logged out" }));
    renderAt(`/reset-password?token=${RESET_TOKEN}`, { initialUser: student, restoreSession: false });
    const user = userEvent.setup();
    await fillPasswords(user);
    await user.click(await screen.findByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    expect(logout).toEqual([{ refresh_token: REFRESH }]);
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
  });
});

// ================================================================================================
describe("Account activation (invitation)", () => {
  const INVITE_TOKEN = "i".repeat(43);
  const INVITE = { email: "anu@example.com", first_name: "Anu", last_name: "Menon", expires_at: "2026-11-22T10:00:00Z" };

  it("checks the link, removes the token from the address bar and activates with the person's own password", async () => {
    const checks = capture("post", "/api/auth/invitation/check", () => HttpResponse.json(INVITE));
    const accepts = capture("post", "/api/auth/invitation/accept", () => HttpResponse.json({ message: "ok", email: INVITE.email }));
    renderAt(`/accept-invitation?token=${INVITE_TOKEN}`);
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Activate your account" })).toBeInTheDocument();
    expect(screen.getByText(/Welcome, Anu\. Choose a password for anu@example\.com/)).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/accept-invitation"));
    expect(checks).toEqual([{ token: INVITE_TOKEN }]);

    await user.type(screen.getByLabelText("Password"), "short");
    await user.type(screen.getByLabelText("Confirm password"), "short");
    await user.click(screen.getByRole("button", { name: "Activate account" }));
    expect(accepts).toEqual([]);

    await user.clear(screen.getByLabelText("Password"));
    await user.clear(screen.getByLabelText("Confirm password"));
    await user.type(screen.getByLabelText("Password"), "Activ8-Mine");
    await user.type(screen.getByLabelText("Confirm password"), "Activ8-Mine");
    await user.click(screen.getByRole("button", { name: "Activate account" }));
    expect(await screen.findByRole("heading", { name: "Your account is active" })).toBeInTheDocument();
    expect(accepts).toEqual([{ token: INVITE_TOKEN, password: "Activ8-Mine" }]);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it.each([
    [410, "expired", "This invitation has expired"],
    [410, "used", "This invitation was already used"],
    [410, "revoked", "This invitation was replaced"],
    [400, "invalid", "This invitation link isn't valid"],
  ])("explains a %s %s link without showing the password form", async (status, code, title) => {
    capture("post", "/api/auth/invitation/check", () => HttpResponse.json({ detail: { code, message: "x" } }, { status }));
    renderAt(`/accept-invitation?token=${INVITE_TOKEN}`);
    expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("handles a link without a token", async () => {
    renderAt("/accept-invitation");
    expect(await screen.findByRole("heading", { name: "This invitation link isn't valid" })).toBeInTheDocument();
  });

  it("shows the reason when the invitation stops working before submitting", async () => {
    capture("post", "/api/auth/invitation/check", () => HttpResponse.json(INVITE));
    capture("post", "/api/auth/invitation/accept", () => HttpResponse.json({ detail: { code: "revoked", message: "x" } }, { status: 410 }));
    renderAt(`/accept-invitation?token=${INVITE_TOKEN}`);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Password"), "Activ8-Mine");
    await user.type(screen.getByLabelText("Confirm password"), "Activ8-Mine");
    await user.click(screen.getByRole("button", { name: "Activate account" }));
    expect(await screen.findByRole("heading", { name: "This invitation was replaced" })).toBeInTheDocument();
  });
});
