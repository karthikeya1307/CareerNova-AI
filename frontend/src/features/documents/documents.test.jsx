import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { validateDraft } from "./components/DocumentEditor";
import { validateOptions } from "./components/CreateDocumentForm";
import { factCheckWarnings, generationLabel, problemLabel } from "./documentFormat";

// Fictional fixtures shaped like backend/schemas/document_schema.py (test-only data).
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const LATEST = { resume_id: 12, filename: "Asha_Resume_2026.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-15T00:00:00Z" };
const OLDER = { resume_id: 5, filename: "Asha_Resume_2025.docx", file_type: "docx", status: "completed", uploaded_at: "2026-08-01T00:00:00Z" };
const FAILED = { resume_id: 20, filename: "broken.pdf", file_type: "pdf", status: "failed", uploaded_at: "2026-11-16T00:00:00Z" };
const INTERNSHIP = {
  internship_id: 99, external_id: null, title: "Machine Learning Intern", company: "Example Labs", description: "x", eligibility: null,
  location: "Pune", application_url: null, deadline: null, domain: "Data Science", work_mode: "Hybrid", duration_weeks: 12,
  stipend_per_month: 10000, stipend_currency: "INR", min_education: null, source: "dataset", is_active: true,
  created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", required_skills: ["Python"], preferred_skills: [], skills: [],
};
const REF = { internship_id: 99, title: "Machine Learning Intern", company: "Example Labs", is_active: true };
const FACT_CHECK = {
  checked_statements: 9,
  warnings: [{ code: "llm_unavailable", detail: "AI writing failed; the fact-based text was used." }],
  rejected_statements: [{ location: "summary", text: "Led a team of 50 engineers.", problems: [{ code: "unsupported_number", detail: "50 is not on your resume." }] }],
  llm: { used: true, accepted: 3, rejected: 1 },
};
const RESUME_DOC = {
  document_id: 31, document_type: "resume", title: "Resume - Machine Learning Intern at Example Labs", resume_id: 12, internship: REF,
  generation_method: "llm", llm_provider: "groq", llm_model: "llama-3.3-70b-versatile", current_version: 1, content: "plain text",
  content_json: {
    type: "resume", header: { name: "Asha Rao", email: "asha@example.com", target: "Machine Learning Intern" },
    sections: [
      { key: "skills", title: "Skills", items: [{ heading: null, lines: ["Python, SQL, Pandas"], fact_ids: ["skills"] }] },
      { key: "projects", title: "Projects", items: [{ heading: "Movie Recommender", lines: ["Built a recommender in Python."], fact_ids: ["project-1"] }] },
    ],
  },
  fact_check: FACT_CHECK,
  ats_report: { required_coverage: { present: 1, total: 1 }, preferred_coverage: { present: 0, total: 0 }, checks: [{ check: "summary", passed: true, detail: "ok" }], suggestions: ["Add Docker only if you genuinely have this skill."] },
  options: {}, created_at: "2026-11-16T10:00:00Z", updated_at: "2026-11-16T10:00:00Z",
};
const LETTER_DOC = {
  ...RESUME_DOC, document_id: 32, document_type: "cover_letter", title: "Cover letter - Machine Learning Intern at Example Labs",
  generation_method: "deterministic", llm_provider: null, llm_model: null, ats_report: null,
  fact_check: { checked_statements: 4, warnings: [], rejected_statements: [], llm: { used: false, accepted: 0, rejected: 0 } },
  content_json: {
    type: "cover_letter", header: { name: "Asha Rao" }, recipient: { company: "Example Labs", title: "Machine Learning Intern" },
    paragraphs: [
      { key: "greeting", text: "Dear Hiring Team at Example Labs,", fact_ids: [] },
      { key: "fit", text: "I have built projects in Python.", fact_ids: ["project-1"] },
    ],
    signoff: "Sincerely,", signature: "Asha Rao",
  },
};
const LLM_OFF = { available: false, provider: null, model: null, disclosure: null };
const LLM_ON = { available: true, provider: "groq", model: "llama-3.3-70b-versatile", disclosure: "Relevant resume content is sent to groq. Your contact details are removed first." };

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

function backend({ llm = LLM_OFF, resumes = [FAILED, LATEST, OLDER], docs = [] } = {}) {
  server.use(
    http.get("/api/resumes/", () => HttpResponse.json(resumes)),
    http.get("/api/resumes/:id/skills", ({ params }) => HttpResponse.json({ resume_id: Number(params.id), skills: [
      { skill_id: 1, name: "Python", category: null, source: "skills" }, { skill_id: 2, name: "SQL", category: null, source: "skills" }] })),
    http.get("/api/documents/llm-status", () => HttpResponse.json(llm)),
    http.get("/api/documents", () => HttpResponse.json(docs)),
    http.get("/api/internships/", () => HttpResponse.json({ total: 1, skip: 0, limit: 8, items: [INTERNSHIP] })),
    http.get("/api/internships/99", () => HttpResponse.json(INTERNSHIP)),
    http.get("/api/documents/31", () => HttpResponse.json(RESUME_DOC)),
    http.get("/api/documents/32", () => HttpResponse.json(LETTER_DOC)),
    http.get("/api/documents/:id/versions", () => HttpResponse.json([{ version: 1, source: "generated", warning_count: 2, created_at: "2026-11-16T10:00:00Z" }])),
  );
}
function capturePost(path, response) {
  const bodies = [];
  server.use(http.post(path, async ({ request }) => {
    bodies.push(await request.json());
    return typeof response === "function" ? response() : HttpResponse.json(response, { status: 201 });
  }));
  return bodies;
}
const form = () => screen.getByRole("form", { name: "Create a document" });
async function pickInternship(user) {
  await user.type(screen.getByLabelText(/Search internships/), "machine");
  await user.click(screen.getByRole("button", { name: "Find internships" }));
  await user.click(await within(screen.getByRole("list", { name: "Internship search results" })).findByRole("button", { name: /Machine Learning Intern/ }));
}

// ================================================================================================
describe("Create documents", () => {
  it("defaults to the latest parsed resume, ignores failed ones and generates a tailored resume for review", async () => {
    backend();
    const bodies = capturePost("/api/documents/resume", RESUME_DOC);
    renderAt("/documents");
    const user = userEvent.setup();
    const resumeSelect = await screen.findByLabelText("Resume to use");
    expect(within(resumeSelect).getAllByRole("option").map((o) => o.textContent)).toEqual([
      expect.stringContaining("Asha_Resume_2026.pdf"),
      expect.stringContaining("Asha_Resume_2025.docx"),
    ]);
    expect(resumeSelect).toHaveValue("12");
    expect(await screen.findByText(/deterministic, fact-based method/)).toBeInTheDocument();

    await pickInternship(user);
    expect(within(form()).getByText("Target internship")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Skills to include"));
    await user.type(screen.getByLabelText("Skills to include"), "10");
    await user.click(screen.getByRole("button", { name: "Generate tailored resume" }));

    await waitFor(() => expect(location()).toBe("/documents/31"));
    expect(bodies).toEqual([{ resume_id: 12, internship_id: 99, options: { max_skills: 10, max_projects: 3, max_experience: 4, max_bullets: 4 }, use_llm: false, llm_consent: false }]);
    expect(await screen.findByText(/Draft ready\./)).toBeInTheDocument();
  });

  it("uses the resume and internship passed in the link and writes a cover letter with chosen options", async () => {
    backend();
    const bodies = capturePost("/api/documents/cover-letter", LETTER_DOC);
    renderAt("/documents?type=cover_letter&internship=99&resume=5");
    const user = userEvent.setup();
    expect(await screen.findByText("Target internship")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Cover letter/ })).toHaveAttribute("aria-checked", "true");
    await waitFor(() => expect(screen.getByLabelText("Resume to use")).toHaveValue("5"));
    await user.selectOptions(screen.getByLabelText("Tone"), "concise");
    await user.click(await screen.findByRole("button", { name: "Python" }));
    expect(screen.getByRole("button", { name: "Python" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Generate cover letter" }));
    await waitFor(() => expect(location()).toBe("/documents/32"));
    expect(bodies).toEqual([{ resume_id: 5, internship_id: 99, tone: "concise", emphasize_skills: ["Python"], use_llm: false, llm_consent: false }]);
  });

  it("validates the internship and layout options before sending", async () => {
    backend();
    const bodies = capturePost("/api/documents/resume", RESUME_DOC);
    renderAt("/documents");
    const user = userEvent.setup();
    await screen.findByLabelText("Resume to use");
    await user.clear(screen.getByLabelText("Bullet points per entry"));
    await user.type(screen.getByLabelText("Bullet points per entry"), "9");
    await user.click(screen.getByRole("button", { name: "Generate tailored resume" }));
    expect(screen.getByText("Choose the internship you're applying to.")).toBeInTheDocument();
    expect(screen.getByText("Enter a whole number from 1 to 6.")).toBeInTheDocument();
    expect(bodies).toHaveLength(0);
  });

  it("keeps AI writing off by default and requires consent to the backend's disclosure", async () => {
    backend({ llm: LLM_ON });
    const bodies = capturePost("/api/documents/resume", RESUME_DOC);
    renderAt("/documents?internship=99");
    const user = userEvent.setup();
    const ai = await screen.findByRole("checkbox", { name: /Use AI-assisted writing \(groq, llama-3.3-70b-versatile\)/ });
    expect(ai).not.toBeChecked();
    expect(screen.queryByText(LLM_ON.disclosure)).not.toBeInTheDocument();
    await screen.findByText("Target internship");

    await user.click(ai);
    expect(screen.getByText(LLM_ON.disclosure)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate tailored resume" }));
    expect(screen.getByText(/Accept the disclosure to use AI-assisted writing/)).toBeInTheDocument();
    expect(bodies).toHaveLength(0);

    await user.click(screen.getByRole("checkbox", { name: /I have read this and agree/ }));
    await user.click(screen.getByRole("button", { name: "Generate tailored resume" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ use_llm: true, llm_consent: true });
  });

  it("never sends AI fields when the student turns AI back off", async () => {
    backend({ llm: LLM_ON });
    const bodies = capturePost("/api/documents/resume", RESUME_DOC);
    renderAt("/documents?internship=99");
    const user = userEvent.setup();
    const ai = await screen.findByRole("checkbox", { name: /Use AI-assisted writing/ });
    await screen.findByText("Target internship");
    await user.click(ai);
    await user.click(screen.getByRole("checkbox", { name: /I have read this and agree/ }));
    await user.click(ai); // off again: consent is cleared too
    await user.click(screen.getByRole("button", { name: "Generate tailored resume" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ use_llm: false, llm_consent: false });
  });

  it.each([
    [404, "Internship not found"],
    [422, "No completed extraction for this resume."],
    [503, "AI-assisted writing is not configured on this server."],
  ])("shows the backend's reason for a %i", async (code, detail) => {
    backend();
    capturePost("/api/documents/resume", () => HttpResponse.json({ detail }, { status: code }));
    renderAt("/documents?internship=99");
    const user = userEvent.setup();
    await screen.findByText("Target internship");
    await user.click(screen.getByRole("button", { name: "Generate tailored resume" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The document couldn't be created");
    expect(alert).toHaveTextContent(detail);
    expect(location()).toBe("/documents?internship=99");
  });

  it("reports network failures", async () => {
    backend();
    server.use(http.post("/api/documents/cover-letter", () => HttpResponse.error()));
    renderAt("/documents?type=cover_letter&internship=99");
    const user = userEvent.setup();
    await screen.findByText("Target internship");
    await user.click(screen.getByRole("button", { name: "Generate cover letter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });

  it("sends only one request when Generate is clicked repeatedly", async () => {
    backend();
    let posts = 0;
    server.use(http.post("/api/documents/resume", async () => {
      posts += 1;
      await delay(150);
      return HttpResponse.json(RESUME_DOC, { status: 201 });
    }));
    renderAt("/documents?internship=99");
    const user = userEvent.setup();
    await screen.findByText("Target internship");
    const button = screen.getByRole("button", { name: "Generate tailored resume" });
    await user.click(button);
    await user.click(button);
    await waitFor(() => expect(location()).toBe("/documents/31"));
    expect(posts).toBe(1);
  });

  it("asks for a resume when none has been parsed", async () => {
    backend({ resumes: [FAILED] });
    renderAt("/documents");
    expect(await screen.findByText("Upload a resume first")).toBeInTheDocument();
  });

  it("explains an internship link that is no longer available", async () => {
    backend();
    server.use(http.get("/api/internships/404", () => HttpResponse.json({ detail: "Internship not found" }, { status: 404 })));
    renderAt("/documents?internship=404");
    expect(await screen.findByText(/The internship from your link isn't available/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Search internships/)).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Review a document", () => {
  let downloads;
  beforeEach(() => {
    downloads = [];
    URL.createObjectURL = vi.fn(() => "blob:doc");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      downloads.push(this.download);
    });
  });
  afterEach(() => {
    delete URL.createObjectURL;
    delete URL.revokeObjectURL;
  });

  it("shows provenance, the fact check, the ATS report and how it was generated", async () => {
    backend();
    renderAt("/documents/31");
    expect(await screen.findByRole("heading", { level: 1, name: RESUME_DOC.title })).toBeInTheDocument();
    expect(screen.getByText("AI-assisted (groq, llama-3.3-70b-versatile)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "your original resume" })).toHaveAttribute("href", "/resumes/12");
    expect(screen.getByText(/Review the 2 fact-check items below before you use this document\./)).toHaveAttribute("role", "status");
    const preview = screen.getByRole("article", { name: "Resume preview" });
    expect(within(preview).getAllByText("From your resume")).toHaveLength(2);
    expect(within(screen.getByRole("list", { name: "Fact-check warnings" })).getByText(/the fact-based text was used/)).toBeInTheDocument();
    const rejected = screen.getByRole("list", { name: "Rejected statements" });
    expect(rejected).toHaveTextContent("Led a team of 50 engineers.");
    expect(rejected).toHaveTextContent("Number not on your resume: 50 is not on your resume.");
    expect(screen.getByText(/AI suggestions: 3 accepted, 1 rejected/)).toBeInTheDocument();
    expect(screen.getByText("Add Docker only if you genuinely have this skill.")).toBeInTheDocument();
  });

  it("labels deterministic documents and shows no problems when there are none", async () => {
    backend();
    renderAt("/documents/32");
    expect(await screen.findByText("Fact-based (no AI)")).toBeInTheDocument();
    expect(screen.getByText(/Generated with the fact-based method; no AI was used\./)).toBeInTheDocument();
    expect(screen.getByText("No problems found")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "ATS check" })).not.toBeInTheDocument();
  });

  it("downloads DOCX and TXT from the backend, and explains failures", async () => {
    backend();
    const formats = [];
    server.use(http.get("/api/documents/31/download", ({ request }) => {
      const format = new URL(request.url).searchParams.get("format");
      formats.push(format);
      if (format === "txt") return HttpResponse.json({ detail: "Document not found" }, { status: 404 });
      return new HttpResponse(new Uint8Array([80, 75]), { headers: { "Content-Type": "application/octet-stream", "Content-Disposition": 'attachment; filename="Resume_Example_Labs.docx"' } });
    }));
    renderAt("/documents/31");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Download DOCX" }));
    await waitFor(() => expect(downloads).toEqual(["Resume_Example_Labs.docx"]));
    await user.click(screen.getByRole("button", { name: "Download TXT" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Document not found");
    expect(formats).toEqual(["docx", "txt"]);
  });

  it("saves edited wording as a new version and shows the backend's fresh fact check", async () => {
    backend();
    const patches = [];
    server.use(http.patch("/api/documents/32", async ({ request }) => {
      const body = await request.json();
      patches.push(body);
      return HttpResponse.json({ ...LETTER_DOC, current_version: 2, content_json: body.content,
        fact_check: { checked_statements: 2, rejected_statements: [], warnings: [{ code: "unsupported_skill", detail: "paragraph 'fit': Kubernetes is not on your resume." }], llm: { used: false, accepted: 0, rejected: 0 } } });
    }));
    renderAt("/documents/32");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit wording" }));
    const fit = screen.getByLabelText("Paragraph 2 (fit)");
    await user.clear(fit);
    await user.type(fit, "I have built projects in Python and Kubernetes.");
    await user.click(screen.getByRole("button", { name: "Save as new version" }));
    expect(await screen.findByText("Version 2")).toBeInTheDocument();
    expect(patches[0].content.paragraphs[1]).toEqual({ key: "fit", text: "I have built projects in Python and Kubernetes.", fact_ids: ["project-1"] });
    expect(patches[0].content.type).toBe("cover_letter");
    expect(screen.getByRole("list", { name: "Fact-check warnings" })).toHaveTextContent("Skill not on your resume. paragraph 'fit': Kubernetes is not on your resume.");
  });

  it("does not save an empty paragraph", async () => {
    backend();
    const patches = [];
    server.use(http.patch("/api/documents/32", async ({ request }) => {
      patches.push(await request.json());
      return HttpResponse.json(LETTER_DOC);
    }));
    renderAt("/documents/32");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit wording" }));
    await user.clear(screen.getByLabelText("Paragraph 1 (greeting)"));
    await user.click(screen.getByRole("button", { name: "Save as new version" }));
    expect(screen.getByText("A paragraph can't be empty.")).toBeInTheDocument();
    expect(patches).toHaveLength(0);
  });

  it("restores an earlier version after confirmation", async () => {
    backend();
    server.use(
      http.get("/api/documents/31", () => HttpResponse.json({ ...RESUME_DOC, current_version: 2 })),
      http.get("/api/documents/31/versions", () => HttpResponse.json([
        { version: 1, source: "generated", warning_count: 2, created_at: "2026-11-16T10:00:00Z" },
        { version: 2, source: "edited", warning_count: 0, created_at: "2026-11-16T11:00:00Z" },
      ])),
    );
    const restored = [];
    server.use(http.post("/api/documents/31/versions/:v/restore", ({ params }) => {
      restored.push(params.v);
      return HttpResponse.json({ ...RESUME_DOC, current_version: 3 });
    }));
    renderAt("/documents/31");
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Document versions" });
    expect(within(list).getByText("Edited by you", { exact: false })).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Restore version 1" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Restore" }));
    expect(await screen.findByText("Version 3")).toBeInTheDocument();
    expect(restored).toEqual(["1"]);
  });

  it("deletes only after confirmation", async () => {
    backend();
    const deleted = [];
    server.use(http.delete("/api/documents/31", () => {
      deleted.push(31);
      return new HttpResponse(null, { status: 204 });
    }));
    renderAt("/documents/31");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(deleted).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete document" }));
    await waitFor(() => expect(location()).toBe("/documents"));
    expect(deleted).toEqual([31]);
  });

  it("explains a document that does not exist or is not the student's", async () => {
    backend();
    server.use(http.get("/api/documents/77", () => HttpResponse.json({ detail: "Document not found" }, { status: 404 })));
    renderAt("/documents/77");
    expect(await screen.findByText("Document not found")).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Document history and integration", () => {
  const ITEM = (id, type, method, warnings) => ({ document_id: id, document_type: type, title: `${type} ${id}`, resume_id: 12, internship: REF,
    generation_method: method, current_version: 1, warning_count: warnings, created_at: "2026-11-16T10:00:00Z", updated_at: "2026-11-16T10:00:00Z" });

  it("lists generated documents and filters by type", async () => {
    const queries = [];
    backend();
    server.use(http.get("/api/documents", ({ request }) => {
      const type = new URL(request.url).searchParams.get("type");
      queries.push(type);
      return HttpResponse.json(type === "cover_letter" ? [ITEM(32, "cover_letter", "deterministic", 0)] : [ITEM(31, "resume", "llm", 2), ITEM(32, "cover_letter", "deterministic", 0)]);
    }));
    renderAt("/documents");
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Generated documents" });
    expect(within(list).getAllByRole("link")).toHaveLength(2);
    expect(within(list).getByText("2 to review")).toBeInTheDocument();
    expect(within(list).getByText("No warnings")).toBeInTheDocument();
    expect(within(list).getAllByRole("link")[0]).toHaveAttribute("href", "/documents/31");
    await user.click(screen.getByRole("button", { name: "Cover letters" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Generated documents" })).getAllByRole("link")).toHaveLength(1));
    expect(queries).toEqual([null, "cover_letter"]);
    expect(location()).toBe("/documents?show=cover_letter");
  });

  it("shows an empty history", async () => {
    backend();
    renderAt("/documents");
    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
  });

  it("is linked from internship details, the dashboard and the Resumes page", async () => {
    backend();
    server.use(http.get("/api/applications/bookmarks/99", () => HttpResponse.json({ saved: false, bookmark: null })));
    const { unmount } = renderAt("/internships/99");
    expect(await screen.findByRole("link", { name: "Tailor my resume" })).toHaveAttribute("href", "/documents?type=resume&internship=99");
    expect(screen.getByRole("link", { name: "Write a cover letter" })).toHaveAttribute("href", "/documents?type=cover_letter&internship=99");
    unmount();

    server.use(http.get("/api/resumes/12", () => HttpResponse.json({ ...LATEST, extracted_data: {}, normalized_skills: [] })));
    renderAt("/resumes/12");
    expect(await screen.findByRole("link", { name: "Tailor this resume" })).toHaveAttribute("href", "/documents?resume=12");
  });

  it("sends the student to sign in when the session has expired", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })),
      http.get("/api/documents", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })),
      http.get("/api/documents/llm-status", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })),
      http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })),
    );
    renderAt("/documents");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/login?next=%2Fdocuments"));
  });
});

// ================================================================================================
describe("Document helpers", () => {
  it("labels methods and problems, and counts warnings like the backend", () => {
    expect(generationLabel("deterministic")).toBe("Fact-based (no AI)");
    expect(generationLabel("llm", "groq", "m")).toBe("AI-assisted (groq, m)");
    expect(problemLabel("unsupported_skill")).toBe("Skill not on your resume");
    expect(problemLabel("something_new")).toBe("something_new");
    expect(factCheckWarnings(FACT_CHECK)).toBe(2);
    expect(factCheckWarnings(null)).toBe(0);
  });

  it("validates options and edits against backend limits", () => {
    expect(validateOptions({ max_skills: "15", max_projects: "3", max_experience: "4", max_bullets: "4" })).toEqual({});
    expect(validateOptions({ max_skills: "4", max_projects: "7", max_experience: "x", max_bullets: "4" })).toEqual({
      max_skills: "Enter a whole number from 5 to 30.", max_projects: "Enter a whole number from 0 to 6.", max_experience: "Enter a whole number from 0 to 8.",
    });
    expect(validateDraft(LETTER_DOC.content_json, { paragraphs: ["Hi", "x".repeat(2001)] })).toEqual({ p1: "Keep each paragraph under 2000 characters." });
    expect(validateDraft(RESUME_DOC.content_json, { items: [["ok"], [Array.from({ length: 21 }, () => "line").join("\n")]] })).toEqual({ s1i0: "Use at most 20 lines." });
  });
});

// ================================================================================================
describe("Selected internship details (cover letter assignment)", () => {
  it("shows the responsibilities, required skills and education the letter is built from", async () => {
    backend();
    server.use(http.get("/api/internships/99", () => HttpResponse.json({
      ...INTERNSHIP, description: "Train and evaluate ranking models for our search product.", required_skills: ["Python", "SQL"],
      min_education: "Pursuing B.Tech/B.E.",
    })));
    renderAt("/documents?type=cover_letter&internship=99");
    const panel = await screen.findByLabelText("Internship details used");
    expect(within(panel).getByText("Train and evaluate ranking models for our search product.")).toBeInTheDocument();
    expect(within(panel).getByText("Python, SQL")).toBeInTheDocument();
    expect(within(panel).getByText("Pursuing B.Tech/B.E.")).toBeInTheDocument();
  });
});
