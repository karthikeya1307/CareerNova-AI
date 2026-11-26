import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { changedFields, completeness, toApiValues, validateProfile } from "./profileForm";

// Fictional fixtures shaped like the backend schemas (UserResponse, ProfileResponse, ResumeDetailResponse).
const student = {
  user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true,
  phone_number: "+919876543210", created_at: "2026-11-01T09:00:00Z",
};
const PROFILE = { profile_id: 3, user_id: 7, college: "Example Institute of Technology", degree: "B.Tech Computer Science", graduation_year: 2027, location: null };
const RESUME = { resume_id: 12, filename: "Asha_Rao_Resume.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-15T09:00:00Z" };
const DETAIL = {
  ...RESUME,
  extracted_data: {
    full_name: "Asha Rao", email: "asha.rao@example.org", phone: "+91 98765 43210", address: "Bengaluru, Karnataka",
    education: [{ details: "B.Tech Computer Science\nExample Institute of Technology\n2023 - 2027" }],
  },
  normalized_skills: [],
};

function renderProfile() {
  setAccessToken("access-token");
  return render(
    <MemoryRouter initialEntries={["/profile"]}>
      <App authProps={{ initialUser: student, restoreSession: false }} />
    </MemoryRouter>,
  );
}

function withResume() {
  server.use(
    http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
    http.get("/api/resumes/12", () => HttpResponse.json(DETAIL)),
  );
}

const academic = () => screen.getByRole("region", { name: "Academic profile" });
const extracted = () => screen.getByRole("region", { name: "Extracted from your resume" });

// ================================================================================================
describe("Profile: new student", () => {
  it("creates a profile with cleaned values", async () => {
    const created = [];
    server.use(http.post("/api/profiles/", async ({ request }) => {
      const body = await request.json();
      created.push(body);
      return HttpResponse.json({ profile_id: 9, user_id: 7, ...body }, { status: 201 });
    }));
    renderProfile();
    const user = userEvent.setup();
    expect(await within(await screen.findByRole("region", { name: "Academic profile" })).findByText("You haven't created a profile yet.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("College or university"), "  Example Institute of Technology ");
    await user.type(screen.getByLabelText("Graduation year"), "2027");
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(await screen.findByText("Profile created.")).toBeInTheDocument();
    expect(created).toEqual([{ college: "Example Institute of Technology", degree: null, graduation_year: 2027, location: null }]);
    expect(await within(academic()).findByText("All changes saved.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("does not create an empty profile", async () => {
    const created = [];
    server.use(http.post("/api/profiles/", async ({ request }) => {
      created.push(await request.json());
      return HttpResponse.json({}, { status: 201 });
    }));
    renderProfile();
    await userEvent.click(await screen.findByRole("button", { name: "Create profile" }));
    expect(await within(academic()).findByRole("alert")).toHaveTextContent("Fill in at least one field to create your profile.");
    expect(created).toHaveLength(0);
  });

  it("reloads the profile if one already exists (409)", async () => {
    let gets = 0;
    server.use(
      http.get("/api/profiles/me", () => {
        gets += 1;
        return gets === 1 ? HttpResponse.json({ detail: "User profile not found" }, { status: 404 }) : HttpResponse.json(PROFILE);
      }),
      http.post("/api/profiles/", () => HttpResponse.json({ detail: "User profile already exists" }, { status: 409 })),
    );
    renderProfile();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Degree"), "MSc");
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    expect(await screen.findByDisplayValue("Example Institute of Technology")).toBeInTheDocument();
    expect(gets).toBe(2);
  });
});

// ================================================================================================
describe("Profile: existing profile", () => {
  it("shows saved values and sends only the changed fields", async () => {
    const patches = [];
    server.use(
      http.get("/api/profiles/me", () => HttpResponse.json(PROFILE)),
      http.patch("/api/profiles/me", async ({ request }) => {
        const body = await request.json();
        patches.push(body);
        return HttpResponse.json({ ...PROFILE, ...body });
      }),
    );
    renderProfile();
    const user = userEvent.setup();
    const degree = await screen.findByDisplayValue("B.Tech Computer Science");
    expect(screen.getByLabelText("Graduation year")).toHaveValue("2027");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await user.type(screen.getByLabelText("Location"), "Bengaluru");
    await user.clear(degree); // clearing a field sends null
    expect(within(academic()).getByText("You have unsaved changes.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
    expect(patches).toEqual([{ degree: null, location: "Bengaluru" }]);
    expect(within(academic()).getByText("All changes saved.")).toBeInTheDocument();
  });

  it("discards unsaved changes", async () => {
    server.use(http.get("/api/profiles/me", () => HttpResponse.json(PROFILE)));
    renderProfile();
    const user = userEvent.setup();
    const college = await screen.findByDisplayValue("Example Institute of Technology");
    await user.clear(college);
    await user.type(college, "Other College");
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(college).toHaveValue("Example Institute of Technology");
  });

  it("validates fields like the backend before saving", async () => {
    const patches = [];
    server.use(
      http.get("/api/profiles/me", () => HttpResponse.json(PROFILE)),
      http.patch("/api/profiles/me", async ({ request }) => {
        patches.push(await request.json());
        return HttpResponse.json(PROFILE);
      }),
    );
    renderProfile();
    const user = userEvent.setup();
    const year = await screen.findByLabelText("Graduation year");
    await user.clear(year);
    await user.type(year, "1850");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText("Enter a year between 1900 and 2100.")).toBeInTheDocument();
    await waitFor(() => expect(year).toHaveFocus());
    await user.clear(year);
    await user.type(year, "20x7");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText("Enter a four-digit year, for example 2027.")).toBeInTheDocument();
    expect(patches).toHaveLength(0);
  });

  it("maps backend validation errors to fields", async () => {
    server.use(
      http.get("/api/profiles/me", () => HttpResponse.json(PROFILE)),
      http.patch("/api/profiles/me", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "location"], msg: "String should have at most 150 characters", type: "string_too_long" }] }, { status: 422 })),
    );
    renderProfile();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Location"), "Somewhere");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("String should have at most 150 characters")).toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows an error with retry when the profile cannot load", async () => {
    let calls = 0;
    server.use(http.get("/api/profiles/me", () => {
      calls += 1;
      return calls === 1 ? HttpResponse.json({ detail: "boom" }, { status: 500 }) : HttpResponse.json(PROFILE);
    }));
    renderProfile();
    const region = await screen.findByRole("region", { name: "Academic profile" });
    await userEvent.click(await within(region).findByRole("button", { name: "Try again" }));
    expect(await screen.findByDisplayValue("Example Institute of Technology")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Profile: account, completeness and extracted information", () => {
  it("shows account details read-only and completeness from real data", async () => {
    withResume();
    server.use(http.get("/api/profiles/me", () => HttpResponse.json(PROFILE)));
    renderProfile();
    const account = await screen.findByRole("region", { name: "Account details" });
    expect(within(account).getByText("asha@example.com")).toBeInTheDocument();
    expect(within(account).getByText("Verified")).toBeInTheDocument();
    expect(within(account).queryByRole("textbox")).not.toBeInTheDocument();

    const checklist = await screen.findByRole("list", { name: "Completeness checklist" });
    // name, email, phone, college, degree, year, resume = 7 of 8 (location missing)
    expect(within(checklist).getByText(/Location/)).toHaveTextContent("(missing)");
    expect(within(checklist).getByText(/Parsed resume/)).toHaveTextContent("(complete)");
    expect(screen.getByRole("region", { name: "Profile completeness" })).toHaveTextContent("88%");
  });

  it("keeps extracted information separate and only fills the form when asked", async () => {
    withResume();
    const patches = [];
    server.use(
      http.get("/api/profiles/me", () => HttpResponse.json(PROFILE)),
      http.patch("/api/profiles/me", async ({ request }) => {
        patches.push(await request.json());
        return HttpResponse.json({ ...PROFILE, location: "Bengaluru, Karnataka" });
      }),
    );
    renderProfile();
    const user = userEvent.setup();
    await screen.findByDisplayValue("Example Institute of Technology");
    const panel = extracted();
    expect(await within(panel).findByText("Bengaluru, Karnataka")).toBeInTheDocument();
    expect(within(panel).getByText(/Read from Asha_Rao_Resume.pdf/)).toBeInTheDocument();
    expect(within(panel).getByText("B.Tech Computer Science")).toBeInTheDocument();
    expect(within(panel).getByText(/differs from your account email/)).toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toHaveValue(""); // nothing copied automatically

    await user.click(within(panel).getByRole("button", { name: "Use resume address as location" }));
    expect(screen.getByLabelText("Location")).toHaveValue("Bengaluru, Karnataka");
    expect(patches).toHaveLength(0); // filling the form does not save
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(patches).toEqual([{ location: "Bengaluru, Karnataka" }]));
  });

  it("explains when there is no parsed resume", async () => {
    renderProfile();
    expect(await within(await screen.findByRole("region", { name: "Extracted from your resume" })).findByText("No parsed resume yet")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Profile form helpers", () => {
  it("validates lengths and years", () => {
    expect(validateProfile({ college: "x".repeat(201), degree: "", graduation_year: "", location: "" })).toEqual({ college: "College must be 200 characters or fewer." });
    expect(validateProfile({ college: "", degree: "x".repeat(151), graduation_year: "2101", location: "x".repeat(151) })).toEqual({
      degree: "Degree must be 150 characters or fewer.",
      graduation_year: "Enter a year between 1900 and 2100.",
      location: "Location must be 150 characters or fewer.",
    });
    expect(validateProfile({ college: "", degree: "", graduation_year: "2026", location: "" })).toEqual({});
  });

  it("maps form values to API values and finds changes", () => {
    expect(toApiValues({ college: " A ", degree: "", graduation_year: "2027", location: "  " })).toEqual({ college: "A", degree: null, graduation_year: 2027, location: null });
    expect(changedFields({ college: "Example Institute of Technology", degree: "", graduation_year: "2027", location: "" }, PROFILE)).toEqual({ degree: null });
  });

  it("computes completeness only from the data it is given", () => {
    expect(completeness({ user: null, profile: null, hasParsedResume: false }).percent).toBe(0);
    const full = completeness({ user: student, profile: { ...PROFILE, location: "Pune" }, hasParsedResume: true });
    expect(full).toMatchObject({ done: 8, total: 8, percent: 100 });
  });
});
