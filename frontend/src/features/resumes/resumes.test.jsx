import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { filenameFromDisposition } from "../../api/resumes";
import { server } from "../../test/server";
import { entryLines, latestParsed, safeExternalUrl } from "./resumeData";
import { validateResumeFile } from "./resumeFile";
import { fromBlocks, fromCommaList, fromLines, toBlocks, toLines } from "./components/ResumeEditor";
import { SAMPLE_READINESS } from "../../test/handlers";

// Fictional fixtures shaped like backend/schemas/resume_schema.py (no real student data).
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const NEW = { resume_id: 12, filename: "Asha_Rao_Resume_2026.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-15T09:00:00Z" };
const OLD = { resume_id: 5, filename: "Asha_Rao_Resume_2025.docx", file_type: "docx", status: "completed", uploaded_at: "2026-08-01T09:00:00Z" };

const EXTRACTED = {
  full_name: "Asha Rao", email: "asha@example.com", phone: "+91 98765 43210", address: "Bengaluru, India",
  linkedin: "linkedin.com/in/asha-example", github: "javascript:alert(1)",
  professional_summary: "Final-year student interested in machine learning.",
  skills: ["Python", "SQL"], technical_skills: ["Python", "SQL"], soft_skills: ["Teamwork"],
  education: [{ details: "B.Tech Computer Science\nExample Institute of Technology\n2023 - 2027" }],
  work_experience: [],
  projects: [{ details: "Movie Recommender\nBuilt a collaborative-filtering recommender in Python." }],
  certifications: ["Example Cloud Practitioner"], internships: [], languages: [], achievements: [],
};
const detail = (resume, extra = {}) => ({
  ...resume,
  extracted_data: EXTRACTED,
  normalized_skills: [
    { skill_id: 1, name: "Python", category: "programming_language", source: "skills" },
    { skill_id: 2, name: "SQL", category: "database", source: "skills" },
  ],
  ...extra,
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderAt(path = "/resumes") {
  setAccessToken("access-token");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={{ initialUser: student, restoreSession: false }} />
      <LocationProbe />
    </MemoryRouter>,
  );
}

const location = () => screen.getByTestId("location").textContent;
const detailPanel = () => screen.getByRole("region", { name: "Resume details" });

function twoResumes() {
  server.use(
    http.get("/api/resumes/", () => HttpResponse.json([NEW, OLD])),
    http.get("/api/resumes/12", () => HttpResponse.json(detail(NEW))),
    http.get("/api/resumes/5", () => HttpResponse.json(detail(OLD, { extracted_data: { ...EXTRACTED, projects: [] } }))),
  );
}

// Three projects as the backend now groups them: title, a Technologies line, then every bullet.
const THREE_PROJECTS = [
  { details: "StudyBuddy – AI-Powered Study Assistant\nTechnologies: Python, RAG, Generative AI, LLMs\nDeveloped a RAG-based study assistant.\nImplemented document ingestion and retrieval.\nDesigned an interactive workspace." },
  { details: "Hospital Queue Optimization Using ML\nTechnologies: Python, Random Forest, XGBoost, Streamlit\nDeveloped a hybrid ML and reinforcement learning system.\nBuilt a Streamlit dashboard." },
  { details: "Fake Review Detection Application\nTechnologies: Python, Deep Learning, React.js\nBuilt an application for detecting fake product reviews." },
];

describe("Re-parse keeps the student's corrections unless they confirm", () => {
  it("asks before re-parsing a corrected resume and does nothing on cancel", async () => {
    let reparses = 0;
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([NEW])),
      http.get("/api/resumes/12", () => HttpResponse.json(detail(NEW, { corrected: true, parser_type: "user_corrected" }))),
      http.post("/api/resumes/12/reparse", () => {
        reparses += 1;
        return HttpResponse.json(detail(NEW));
      }),
    );
    renderAt();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    await userEvent.click(await within(panel).findByRole("button", { name: "Re-parse" }));
    const dialog = await screen.findByRole("dialog", { name: "Re-parse and replace your corrections?" });
    expect(dialog).toHaveTextContent("The original file is not changed.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(reparses).toBe(0);
    await userEvent.click(within(panel).getByRole("button", { name: "Re-parse" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Re-parse anyway" }));
    await waitFor(() => expect(reparses).toBe(1));
  });
});

describe("Resume details: grouped projects", () => {
  it("shows one card per project with its title, technologies and all of its bullets", async () => {
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([NEW])),
      http.get("/api/resumes/12", () => HttpResponse.json(detail(NEW, { extracted_data: { ...EXTRACTED, projects: THREE_PROJECTS } }))),
    );
    renderAt();
    const heading = await screen.findByRole("heading", { name: /^Projects/ });
    expect(heading).toHaveTextContent("3");
    const cards = within(heading.closest("section")).getAllByRole("listitem").filter((li) => li.parentElement.tagName === "OL");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]).getByText("StudyBuddy – AI-Powered Study Assistant")).toBeInTheDocument();
    expect(within(cards[0]).getByText("Technologies: Python, RAG, Generative AI, LLMs")).toBeInTheDocument();
    expect(within(cards[0]).getByText("Designed an interactive workspace.")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Built a Streamlit dashboard.")).toBeInTheDocument();
    expect(within(cards[2]).queryByText("Built a Streamlit dashboard.")).not.toBeInTheDocument();
  });
});

// ================================================================================================
describe("Resume list and details", () => {
  it("lists every resume, marks the latest and shows its extracted information", async () => {
    twoResumes();
    renderAt();
    const list = await screen.findByRole("list", { name: "Your resumes" });
    const items = within(list).getAllByRole("link");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Asha_Rao_Resume_2026.pdf");
    expect(items[0]).toHaveTextContent("Latest");
    expect(items[0]).toHaveTextContent("Used for matching");
    expect(items[0]).toHaveAttribute("aria-current", "page");
    expect(items[1]).not.toHaveTextContent("Latest");

    const panel = detailPanel();
    expect(await within(panel).findByText("Asha Rao")).toBeInTheDocument();
    expect(within(panel).getByText("+91 98765 43210")).toBeInTheDocument();
    expect(within(panel).getByText("Final-year student interested in machine learning.")).toBeInTheDocument();
    expect(within(panel).getByText("B.Tech Computer Science")).toBeInTheDocument();
    expect(within(panel).getByText("Example Institute of Technology")).toBeInTheDocument();
    expect(within(panel).getByText("Movie Recommender")).toBeInTheDocument();
    expect(within(panel).getByText("Example Cloud Practitioner")).toBeInTheDocument();
    expect(within(panel).getByText("No work experience found in this resume.")).toBeInTheDocument();
    expect(within(panel).getByText("Python")).toBeInTheDocument();
    expect(within(panel).getByText("Teamwork")).toBeInTheDocument();
    // Optional sections the parser found nothing for are not shown at all.
    expect(within(panel).queryByRole("heading", { name: /Achievements/ })).not.toBeInTheDocument();
    // Only http(s) links are rendered as links.
    expect(within(panel).getByRole("link", { name: "linkedin.com/in/asha-example" })).toHaveAttribute("href", "https://linkedin.com/in/asha-example");
    expect(within(panel).queryByRole("link", { name: "javascript:alert(1)" })).not.toBeInTheDocument();
    expect(within(panel).getByText("javascript:alert(1)")).toBeInTheDocument();
  });

  it("opens another resume from the list", async () => {
    twoResumes();
    renderAt();
    const list = await screen.findByRole("list", { name: "Your resumes" });
    await userEvent.click(within(list).getByRole("link", { name: /Asha_Rao_Resume_2025.docx/ }));
    await waitFor(() => expect(location()).toBe("/resumes/5"));
    expect(await within(detailPanel()).findByRole("heading", { name: "Asha_Rao_Resume_2025.docx" })).toBeInTheDocument();
    expect(await within(detailPanel()).findByText("No projects found in this resume.")).toBeInTheDocument();
  });

  it("shows an empty state when there are no resumes", async () => {
    renderAt();
    expect(await screen.findByText("No resumes yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browse files" })).toBeInTheDocument();
  });

  it("explains a resume id that is missing or not the student's", async () => {
    twoResumes();
    renderAt("/resumes/999");
    expect(await within(await screen.findByRole("region", { name: "Resume details" })).findByText("Resume not found")).toBeInTheDocument();
  });

  it("offers re-parsing when a resume has no successful extraction", async () => {
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([NEW])),
      http.get("/api/resumes/12", () => HttpResponse.json({ detail: "Parsed resume information not found" }, { status: 404 })),
      http.post("/api/resumes/12/reparse", () => HttpResponse.json(detail(NEW))),
    );
    renderAt();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    expect(await within(panel).findByText("No extracted information yet")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Re-parse" }));
    expect(await within(panel).findByText("Movie Recommender")).toBeInTheDocument();
    expect(await screen.findByText("Resume re-parsed. The extracted information is up to date.")).toBeInTheDocument();
  });

  it("keeps the earlier data and explains when re-parsing fails", async () => {
    twoResumes();
    server.use(http.post("/api/resumes/12/reparse", () => HttpResponse.json({ detail: "No readable text found in the resume." }, { status: 422 })));
    renderAt();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    await within(panel).findByText("Movie Recommender");
    await userEvent.click(within(panel).getByRole("button", { name: "Re-parse" }));
    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent("Re-parsing failed: No readable text found in the resume.");
    expect(alert).toHaveTextContent("previously extracted information is still in use");
    expect(within(panel).getByText("Movie Recommender")).toBeInTheDocument();
  });

  it("shows an error with retry when the list cannot load", async () => {
    let calls = 0;
    server.use(http.get("/api/resumes/", () => {
      calls += 1;
      return calls === 1 ? HttpResponse.json({ detail: "boom" }, { status: 500 }) : HttpResponse.json([NEW]);
    }), http.get("/api/resumes/12", () => HttpResponse.json(detail(NEW))));
    renderAt();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load your resumes.");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Your resumes" })).toBeInTheDocument();
  });

  it("sends the student to sign in when the session has expired", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 })),
      http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })),
    );
    renderAt("/resumes/12");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(location()).toBe("/login?next=%2Fresumes%2F12");
  });
});

// ================================================================================================
describe("Resume upload", () => {
  it("validates type, size and empty files before uploading", async () => {
    const posted = [];
    server.events.on("request:start", ({ request }) => request.method === "POST" && posted.push(request.url));
    renderAt();
    await screen.findByText("No resumes yet");
    const user = userEvent.setup({ applyAccept: false });
    const input = screen.getByTestId("resume-file-input");

    await user.upload(input, new File(["x"], "photo.png", { type: "image/png" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Upload a PDF, Word (.docx) or OpenDocument (.odt) file.");
    await user.upload(input, new File([], "empty.pdf", { type: "application/pdf" }));
    expect(screen.getByRole("alert")).toHaveTextContent("That file is empty.");
    const big = new File(["x"], "big.docx");
    Object.defineProperty(big, "size", { value: 6 * 1024 * 1024 });
    await user.upload(input, big);
    expect(screen.getByRole("alert")).toHaveTextContent("Resume files must be 5 MB or smaller.");
    expect(posted).toHaveLength(0);
    expect(screen.getByText("PDF, DOCX or ODT · up to 5 MB · one file at a time")).toBeInTheDocument();
  });

  it("uploads a dropped file once, shows progress, then opens the new resume", async () => {
    let uploads = 0;
    let listCalls = 0;
    server.use(
      http.get("/api/resumes/", () => {
        listCalls += 1;
        return HttpResponse.json(listCalls === 1 ? [OLD] : [NEW, OLD]);
      }),
      http.get("/api/resumes/5", () => HttpResponse.json(detail(OLD))),
      http.get("/api/resumes/12", () => HttpResponse.json(detail(NEW))),
      http.post("/api/resumes/upload", async () => {
        uploads += 1;
        await delay(150);
        return HttpResponse.json(detail(NEW), { status: 201 });
      }),
    );
    renderAt();
    await screen.findByRole("list", { name: "Your resumes" });
    const zone = screen.getByTestId("resume-dropzone");
    const file = new File(["%PDF-1.7"], "Asha_Rao_Resume_2026.pdf", { type: "application/pdf" });

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    expect(await screen.findByRole("progressbar", { name: "Upload progress" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browse files" })).toBeDisabled();
    fireEvent.drop(zone, { dataTransfer: { files: [file] } }); // ignored while uploading

    expect(await screen.findByText("Asha_Rao_Resume_2026.pdf was uploaded and parsed.")).toBeInTheDocument();
    expect(uploads).toBe(1);
    await waitFor(() => expect(location()).toBe("/resumes/12"));
    const list = await screen.findByRole("list", { name: "Your resumes" });
    await waitFor(() => expect(within(list).getAllByRole("link")).toHaveLength(2));
    expect(await within(detailPanel()).findByRole("heading", { name: "Asha_Rao_Resume_2026.pdf" })).toBeInTheDocument();
  });

  it("rejects dropping several files at once", async () => {
    renderAt();
    await screen.findByText("No resumes yet");
    fireEvent.drop(screen.getByTestId("resume-dropzone"), {
      dataTransfer: { files: [new File(["a"], "a.pdf"), new File(["b"], "b.pdf")] },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Drop one resume at a time.");
  });

  it.each([
    [422, "Unable to parse the uploaded resume."],
    [415, "Only PDF and DOCX files are supported."],
    [413, "Resume file must not exceed 5 MB."],
  ])("shows the backend's reason for a %i upload failure", async (statusCode, message) => {
    server.use(http.post("/api/resumes/upload", () => HttpResponse.json({ detail: message }, { status: statusCode })));
    renderAt();
    await screen.findByText("No resumes yet");
    await userEvent.upload(screen.getByTestId("resume-file-input"), new File(["%PDF"], "cv.pdf", { type: "application/pdf" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Upload failed.");
    expect(alert).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "Browse files" })).toBeEnabled();
  });
});

// ================================================================================================
describe("Download and delete", () => {
  let downloads;
  beforeEach(() => {
    downloads = [];
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      downloads.push({ href: this.href, download: this.download });
    });
  });
  afterEach(() => {
    delete URL.createObjectURL;
    delete URL.revokeObjectURL;
  });

  it("downloads the original file with its filename", async () => {
    twoResumes();
    server.use(http.get("/api/resumes/12/download", () =>
      new HttpResponse(new Uint8Array([37, 80, 68, 70]), {
        headers: { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="Asha_Rao_Resume_2026.pdf"' },
      })));
    renderAt();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    await userEvent.click(await within(panel).findByRole("button", { name: "Download" }));
    await waitFor(() => expect(downloads).toEqual([{ href: "blob:mock-url", download: "Asha_Rao_Resume_2026.pdf" }]));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("explains when the stored file is missing", async () => {
    twoResumes();
    server.use(http.get("/api/resumes/12/download", () => HttpResponse.json({ detail: "Stored resume file not found" }, { status: 404 })));
    renderAt();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    await userEvent.click(await within(panel).findByRole("button", { name: "Download" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("Stored resume file not found");
    expect(downloads).toHaveLength(0);
  });

  it("deletes only after the student types DELETE, then shows the remaining resume", async () => {
    const deleted = [];
    let listCalls = 0;
    server.use(
      http.get("/api/resumes/", () => {
        listCalls += 1;
        return HttpResponse.json(listCalls === 1 ? [NEW, OLD] : [OLD]);
      }),
      http.get("/api/resumes/12", () => HttpResponse.json(detail(NEW))),
      http.get("/api/resumes/5", () => HttpResponse.json(detail(OLD))),
      http.delete("/api/resumes/:id", ({ params }) => {
        deleted.push(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt("/resumes/12");
    const user = userEvent.setup();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    await within(panel).findByText("Movie Recommender");

    // Cancel first: nothing is deleted.
    await user.click(within(panel).getByRole("button", { name: "Delete" }));
    let dialog = screen.getByRole("dialog", { name: "Delete Asha_Rao_Resume_2026.pdf?" });
    expect(dialog).toHaveTextContent("This cannot be undone.");
    expect(dialog).toHaveTextContent("match results");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(deleted).toHaveLength(0);

    await user.click(within(panel).getByRole("button", { name: "Delete" }));
    dialog = screen.getByRole("dialog");
    const confirmButton = within(dialog).getByRole("button", { name: "Delete resume" });
    expect(confirmButton).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(confirmButton);

    expect(await screen.findByText("Asha_Rao_Resume_2026.pdf was deleted.")).toBeInTheDocument();
    expect(deleted).toEqual(["12"]);
    // React Router commits navigations as transitions, so the URL can update just after the toast.
    await waitFor(() => expect(location()).toBe("/resumes"));
    const list = await screen.findByRole("list", { name: "Your resumes" });
    await waitFor(() => expect(within(list).getAllByRole("link")).toHaveLength(1));
    expect(within(list).getByRole("link")).toHaveTextContent("Asha_Rao_Resume_2025.docx");
  });

  it("reports a failed deletion and keeps the resume", async () => {
    twoResumes();
    server.use(http.delete("/api/resumes/12", () => HttpResponse.json({ detail: "Unable to delete the resume." }, { status: 500 })));
    renderAt();
    const user = userEvent.setup();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    await within(panel).findByText("Movie Recommender");
    await user.click(within(panel).getByRole("button", { name: "Delete" }));
    await user.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(screen.getByRole("button", { name: "Delete resume" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("Unable to delete the resume.");
    expect(within(screen.getByRole("list", { name: "Your resumes" })).getAllByRole("link")).toHaveLength(2);
  });
});

// ================================================================================================
describe("Resume helpers", () => {
  it("picks the latest successfully parsed resume", () => {
    expect(latestParsed([{ resume_id: 3, status: "failed" }, { resume_id: 2, status: "completed" }]).resume_id).toBe(2);
    expect(latestParsed([{ resume_id: 3, status: "failed" }])).toBeNull();
    expect(latestParsed(null)).toBeNull();
  });

  it("splits parser entries without inventing structure", () => {
    expect(entryLines({ details: "B.Tech\n\nExample Institute\n 2027 " })).toEqual({ heading: "B.Tech", lines: ["Example Institute", "2027"] });
    expect(entryLines({ degree: "MSc", year: 2026 })).toEqual({ heading: "Degree: MSc", lines: ["Year: 2026"] });
    expect(entryLines("Plain text")).toEqual({ heading: "Plain text", lines: [] });
  });

  it("only allows http(s) profile links", () => {
    expect(safeExternalUrl("https://github.com/example")).toBe("https://github.com/example");
    expect(safeExternalUrl("github.com/example")).toBe("https://github.com/example");
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("example handle")).toBeNull();
  });

  it("reads filenames from Content-Disposition", () => {
    expect(filenameFromDisposition('attachment; filename="cv.pdf"')).toBe("cv.pdf");
    expect(filenameFromDisposition("attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf")).toBe("résumé.pdf");
    expect(filenameFromDisposition(null)).toBeNull();
  });

  it("validates files like the backend", () => {
    expect(validateResumeFile(new File(["x"], "CV.DOCX"))).toBeNull();
    expect(validateResumeFile(new File(["x"], "resume.odt"))).toBeNull();
    expect(validateResumeFile(new File(["x"], "cv.doc"))).toMatch(/PDF, Word .* or OpenDocument/);
  });
});

// ================================================================================================
describe("Resume readiness and corrections (P2)", () => {
  it("shows the general readiness score with categories, reasons, recommendations and parsing quality", async () => {
    twoResumes();
    renderAt();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    const readiness = await within(panel).findByRole("region", { name: "Resume readiness" });
    expect(within(readiness).getByLabelText("Readiness score 78 out of 100")).toBeInTheDocument();
    expect(within(readiness).getByText("Good")).toBeInTheDocument();
    const categories = within(readiness).getByRole("list", { name: "Score by category" });
    expect(within(categories).getAllByRole("button")).toHaveLength(8);
    await userEvent.click(within(categories).getByRole("button", { name: /Contact and profile/ }));
    expect(within(categories).getByText(/No LinkedIn or GitHub link/)).toBeInTheDocument();
    expect(within(readiness).getByRole("list", { name: "Recommended improvements" })).toHaveTextContent("List at least 8 relevant technical skills.");
    expect(within(readiness).getByText(/Parsing confidence:/)).toHaveTextContent("92%");
    expect(within(readiness).getByText(/not a prediction of any specific employer/)).toBeInTheDocument();
    // Which version was scored, and what the score is (and is not) based on.
    expect(within(readiness).getByText("Scored version: V2 · Asha_Rao_CV.pdf")).toBeInTheDocument();
    expect(within(readiness).getByLabelText("How this score is calculated")).toHaveTextContent(/profile details don.t change it/);
    expect(within(readiness).queryByText(/exactly the same extracted content/)).not.toBeInTheDocument();
  });

  it("explains that a version with identical content has the same score", async () => {
    twoResumes();
    server.use(http.get("/api/resumes/:id/readiness", () =>
      HttpResponse.json({ ...SAMPLE_READINESS, version_label: "Data focus", same_content_as: [{ resume_id: 9, version: 1 }, { resume_id: 10, version: 3 }] })));
    renderAt();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    const readiness = await within(panel).findByRole("region", { name: "Resume readiness" });
    expect(await within(readiness).findByText("Scored version: V2 · Data focus")).toBeInTheDocument();
    expect(within(readiness).getByText(/V1, V3 have exactly the same extracted content as this version/)).toBeInTheDocument();
    expect(within(readiness).getByText(/Uploading the same resume again doesn.t change the score/)).toBeInTheDocument();
  });

  it("lets the student correct the extracted details and refreshes readiness", async () => {
    twoResumes();
    let readinessCalls = 0;
    const saved = [];
    server.use(
      http.get("/api/resumes/12/readiness", () => {
        readinessCalls += 1;
        return HttpResponse.json({ ...SAMPLE_READINESS, score: readinessCalls > 1 ? 84 : 78 });
      }),
      http.put("/api/resumes/12/extracted-data", async ({ request }) => {
        const body = await request.json();
        saved.push(body);
        return HttpResponse.json(detail(NEW, { extracted_data: { ...EXTRACTED, ...body }, corrected: true, parser_type: "user_corrected" }));
      }),
    );
    renderAt();
    const user = userEvent.setup();
    const panel = await screen.findByRole("region", { name: "Resume details" });
    await within(panel).findByLabelText("Readiness score 78 out of 100");
    await user.click(within(panel).getByRole("button", { name: "Edit details" }));
    const form = within(panel).getByRole("form", { name: "Edit extracted details" });
    expect(within(form).getByLabelText("Full name")).toHaveValue("Asha Rao");
    const skills = within(form).getByLabelText(/^Skills/);
    expect(skills).toHaveValue("Python, SQL");
    await user.clear(skills);
    await user.type(skills, "Python, SQL, Pandas, python");
    await user.type(within(form).getByLabelText(/^Achievements/), "Hackathon finalist 2025");
    await user.click(within(form).getByRole("button", { name: "Save corrections" }));
    expect(await within(panel).findByText("Corrected by you")).toBeInTheDocument();
    expect(await within(panel).findByLabelText("Readiness score 84 out of 100")).toBeInTheDocument();
    expect(saved).toHaveLength(1);
    expect(saved[0].skills).toEqual(["Python", "SQL", "Pandas", "python"]);
    expect(saved[0].achievements).toEqual(["Hackathon finalist 2025"]);
    expect(saved[0].projects).toEqual([{ details: "Movie Recommender\nBuilt a collaborative-filtering recommender in Python." }]);
    expect(saved[0].github).toBe("javascript:alert(1)"); // unchanged values are kept as they were (shown, never linked)
  });

  it("converts edited sections without inventing anything", () => {
    expect(fromBlocks("A\nline two\n\n\nB")).toEqual([{ details: "A\nline two" }, { details: "B" }]);
    expect(toBlocks([{ details: "A" }, "B", {}])).toBe("A\n\nB");
    expect(fromCommaList("Python, SQL\nPython ,, Go")).toEqual(["Python", "SQL", "Go"]);
    expect(fromLines(" one \n\n two ")).toEqual(["one", "two"]);
    expect(toLines(["a", "b"])).toBe("a\nb");
  });

  it("warns when an upload duplicates an earlier resume", async () => {
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([NEW])),
      http.get("/api/resumes/12", () => HttpResponse.json(detail(NEW))),
      http.get("/api/resumes/13", () => HttpResponse.json(detail({ ...NEW, resume_id: 13 }))),
      http.post("/api/resumes/upload", () =>
        HttpResponse.json({ ...detail({ ...NEW, resume_id: 13 }), duplicate_of: [12], duplicate_kind: "identical_file" }, { status: 201 }),
      ),
    );
    renderAt();
    const user = userEvent.setup();
    await screen.findByRole("region", { name: "Resume details" });
    await user.upload(screen.getByTestId("resume-file-input"), new File(["%PDF-1.4"], "Asha_Rao_Resume_2026.pdf", { type: "application/pdf" }));
    expect(await screen.findByText(/is the same file as resume #12/)).toBeInTheDocument();
  });
});
