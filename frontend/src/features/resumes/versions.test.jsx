import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { validateAvatarFile } from "../../api/profile";
import { server } from "../../test/server";
import { latestParsed } from "./resumeData";

// HR feedback: profile picture + bio, resume versions and comparison (fictional fixtures).
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const V1 = { resume_id: 11, filename: "cv_v1.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-01T09:00:00Z", version: 1, label: "Original", is_preferred: false };
const V2 = { resume_id: 12, filename: "cv_v2.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-20T09:00:00Z", version: 2, label: null, is_preferred: false };
const DETAIL = (r) => ({ resume_id: r.resume_id, filename: r.filename, file_type: "pdf", status: "completed", uploaded_at: r.uploaded_at,
  corrected: false, extracted_data: { full_name: "Asha Rao", skills: ["SQL"] }, normalized_skills: [] });
const COMPARE = {
  algorithm: "compare-v1",
  a: { resume_id: 11, filename: "cv_v1.pdf", label: "Original" }, b: { resume_id: 12, filename: "cv_v2.pdf", label: null },
  contact: [{ field: "linkedin", label: "LinkedIn", a: null, b: "linkedin.com/in/x", status: "added" }], summary: "added",
  skills: { technical: { added: ["Power BI"], removed: ["Excel"], kept: ["SQL"] }, soft: { added: [], removed: [], kept: [] }, count: { a: 3, b: 3 } },
  sections: { project: { label: "Projects", added: ["Churn Analysis"], removed: [], modified: [{ title: "Sales Report", lines_added: ["Built a Power BI report."], lines_removed: ["Built an Excel report."] }], unchanged: [] } },
  keywords: { added: ["Power BI"], removed: ["Excel"], now_backed_by_evidence: [], lost_evidence: [] },
  metrics: { readiness: { algorithm: "readiness-v1", a: 52, b: 71, change: 19, categories: [{ key: "skills", label: "Skills", max: 20, a: 8, b: 14, change: 6 }] },
    role: { slug: "data-analyst", title: "Data Analyst", algorithm: "roles-v1", a: 40, b: 65, change: 25, missing_a: ["Tableau"], missing_b: ["Tableau"] } },
  verdict: { stronger: "b", headline: "Version B is stronger by the measured scores.", reasons: ["Skills: 14/20 vs 8/20"], basis: "readiness-v1 (and role fit / ATS report when chosen), calculated the same way for both versions" },
  improvements_in_b: ["New skill: Power BI."], weaknesses_introduced_in_b: ["Skill \"Excel\" was removed in version B."],
  recommendations_for_weaker: ["Add a professional summary."], role_advice: [], notes: ["Section entries are matched by their first line."],
};

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

describe("Resume versions", () => {
  it("lists versions with names, sets one as preferred and renames it", async () => {
    let list = [V2, V1];
    const patches = [];
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json(list)),
      http.get("/api/resumes/:id", ({ params }) => HttpResponse.json(DETAIL(list.find((r) => r.resume_id === Number(params.id))))),
      http.patch("/api/resumes/:id", async ({ params, request }) => {
        const body = await request.json();
        patches.push({ id: Number(params.id), ...body });
        list = list.map((r) => (r.resume_id === Number(params.id) ? { ...r, ...body } : body.is_preferred ? { ...r, is_preferred: false } : r));
        return HttpResponse.json(list.find((r) => r.resume_id === Number(params.id)));
      }),
    );
    renderAt("/resumes/11");
    const user = userEvent.setup();
    const versions = await screen.findByRole("list", { name: "Your resumes" });
    expect(within(versions).getByText("Original")).toBeInTheDocument();
    expect(within(versions).getByText("cv_v2.pdf")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "V1 · Original" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Set as preferred" }));
    await waitFor(() => expect(patches).toEqual([{ id: 11, is_preferred: true }]));
    expect(await within(versions).findByText("Preferred")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rename version" }));
    const input = screen.getByRole("textbox", { name: "Version name" });
    await user.clear(input);
    await user.type(input, "Internship-focused");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches.at(-1)).toEqual({ id: 11, label: "Internship-focused" }));
    expect(await screen.findByRole("heading", { level: 2, name: "V1 · Internship-focused" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Compare with another version/ })).toHaveAttribute("href", "/resumes/compare?a=12&b=11");
  });

  it("uses the preferred parsed version for matching, else the newest parsed one", () => {
    expect(latestParsed([V2, V1]).resume_id).toBe(12);
    expect(latestParsed([V2, { ...V1, is_preferred: true }]).resume_id).toBe(11);
    expect(latestParsed([{ ...V2, status: "failed", is_preferred: true }, V1]).resume_id).toBe(11);
  });
});

describe("Resume comparison", () => {
  it("compares two versions and shows measured differences and the verdict", async () => {
    const asked = [];
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([V2, V1])),
      http.get("/api/resumes/compare", ({ request }) => {
        asked.push(Object.fromEntries(new URL(request.url).searchParams));
        return HttpResponse.json(COMPARE);
      }),
    );
    renderAt("/resumes/compare");
    const user = userEvent.setup();
    const form = await screen.findByRole("form", { name: "Compare two versions" });
    await waitFor(() => expect(within(form).getByRole("combobox", { name: "Version A (earlier)" })).toHaveValue("11"));
    expect(within(form).getByRole("combobox", { name: "Version B (later)" })).toHaveValue("12");
    await user.selectOptions(within(form).getByRole("combobox", { name: "For a role (optional)" }), "data-analyst");
    await user.click(within(form).getByRole("button", { name: "Compare" }));
    await waitFor(() => expect(asked).toEqual([{ a: "11", b: "12", role: "data-analyst" }]));

    expect(await screen.findByRole("heading", { name: /Version B is stronger by the measured scores/ })).toBeInTheDocument();
    expect(screen.getByText("Skills: 14/20 vs 8/20")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Technical added" })).toHaveTextContent("Power BI");
    expect(screen.getByRole("list", { name: "Technical removed" })).toHaveTextContent("Excel");
    expect(screen.getByRole("list", { name: "Projects changes" })).toHaveTextContent("Churn Analysis");
    expect(screen.getByRole("list", { name: "Projects changes" })).toHaveTextContent("+ Built a Power BI report.");
    expect(screen.getByText("Data Analyst fit (roles-v1)")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Weaknesses introduced" })).toHaveTextContent("Excel");
    expect(screen.getByRole("list", { name: "Recommendations" })).toHaveTextContent("Add a professional summary.");
  });

  it("needs two parsed versions", async () => {
    server.use(http.get("/api/resumes/", () => HttpResponse.json([V1])));
    renderAt("/resumes/compare");
    expect(await screen.findByText("Upload at least two resumes")).toBeInTheDocument();
  });
});

describe("Profile picture and bio", () => {
  it("uploads a picture, shows it in the header and saves the bio", async () => {
    let profile = { profile_id: 1, user_id: 7, college: null, degree: null, graduation_year: null, location: null, bio: null, has_avatar: false, avatar_updated_at: null };
    const calls = [];
    globalThis.URL.createObjectURL = () => "blob:avatar";
    globalThis.URL.revokeObjectURL = () => {};
    server.use(
      http.get("/api/profiles/me", () => HttpResponse.json(profile)),
      http.get("/api/profiles/me/avatar", () => (profile.has_avatar
        ? new HttpResponse(new Uint8Array([137, 80, 78, 71]), { headers: { "Content-Type": "image/png" } })
        : HttpResponse.json({ detail: "No profile picture" }, { status: 404 }))),
      http.post("/api/profiles/me/avatar", () => {
        calls.push("upload");
        profile = { ...profile, has_avatar: true, avatar_updated_at: "2026-11-25T08:00:00Z" };
        return HttpResponse.json(profile);
      }),
      http.patch("/api/profiles/me", async ({ request }) => {
        const body = await request.json();
        calls.push(body);
        profile = { ...profile, ...body };
        return HttpResponse.json(profile);
      }),
    );
    renderAt("/profile");
    const user = userEvent.setup();
    const photo = (await screen.findByRole("heading", { name: "Profile picture" })).closest("section");
    expect(within(photo).getByText(/No picture yet/)).toBeInTheDocument();
    await user.upload(photo.querySelector('input[type="file"]'), new File([new Uint8Array([137, 80, 78, 71])], "me.png", { type: "image/png" }));
    await waitFor(() => expect(calls).toContain("upload"));
    await waitFor(() => expect(document.querySelector('header img[src="blob:avatar"]')).toBeInTheDocument());
    expect(within(photo).getByRole("button", { name: "Remove" })).toBeInTheDocument();

    const bio = screen.getByRole("textbox", { name: "Short professional introduction" });
    await user.type(bio, "Aspiring data analyst.");
    await user.click(screen.getByRole("button", { name: "Save bio" }));
    await waitFor(() => expect(calls).toContainEqual({ bio: "Aspiring data analyst." }));
    expect(await screen.findByText("Aspiring data analyst.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit bio" })).toBeInTheDocument();
  });

  it("checks picture files before uploading", () => {
    expect(validateAvatarFile(new File(["x"], "a.png", { type: "image/png" }))).toBeNull();
    expect(validateAvatarFile(new File(["x"], "a.svg", { type: "image/svg+xml" }))).toBe("Use a PNG, JPEG or WebP picture.");
    expect(validateAvatarFile(new File([], "a.png", { type: "image/png" }))).toBe("The file is empty.");
  });
});
