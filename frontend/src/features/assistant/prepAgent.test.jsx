import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { validateStudyFile } from "../../api/studyDocuments";
import { server } from "../../test/server";
import { actionLink, sourceLink, sourcesOrigin } from "./assistantFormat";
import { blocks } from "./components/RichText";

// HR assignment: interview preparation agent + document Q&A in the assistant (fictional test data).
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const LLM_OFF = { available: false, provider: null, model: null, disclosure: null, assistant_disclosure: null };
const caps = { intents: {}, llm: LLM_OFF, limits: { message_chars: 2000, messages_per_minute: 10, messages_per_day: 200 }, notes: [] };
const conv = (extra = {}) => ({
  conversation_id: 5, title: "Role recommendations", resume_id: null, message_count: 0, last_message_at: null,
  created_at: "2026-11-24T08:00:00Z", updated_at: "2026-11-24T08:00:00Z", assistant: "interview", study_document_id: null,
  study_document_ids: [], target_role: null, messages: [], ...extra,
});
const DOC = { document_id: 3, filename: "sql_notes.pdf", file_type: "pdf", page_count: 2, section_count: 0, char_count: 841, chunk_count: 2,
  title: "SQL notes", warnings: [], preview: "A primary key...", created_at: "2026-11-24T08:00:00Z" };

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

function backend({ reply = "Done.", targetRole = null } = {}) {
  const state = { posts: [], puts: [], uploads: 0, conversation: conv({ target_role: targetRole }), docs: [] };
  server.use(
    http.get("/api/assistant/capabilities", () => HttpResponse.json(caps)),
    http.get("/api/assistant/conversations", () => HttpResponse.json({ total: 1, skip: 0, limit: 20, items: [state.conversation] })),
    http.post("/api/assistant/conversations", () => HttpResponse.json(state.conversation, { status: 201 })),
    http.get("/api/assistant/conversations/5", () => HttpResponse.json(state.conversation)),
    http.post("/api/assistant/conversations/5/messages", async ({ request }) => {
      const body = await request.json();
      state.posts.push(body.message);
      if (/Prepare me for Data Analyst/.test(body.message)) state.conversation = { ...state.conversation, target_role: "data-analyst" };
      const m = (id, sender, content) => ({ message_id: id, sender, content, intent: "role_recommendation", sources: [], result_set: null,
        suggested_actions: [], generation_method: sender === "user" ? null : "deterministic", warnings: [], created_at: "2026-11-24T09:00:00Z" });
      const n = state.posts.length * 2;
      return HttpResponse.json({ conversation_id: 5, user_message: m(n - 1, "user", body.message), assistant_message: m(n, "assistant", reply) },
        { status: 201 });
    }),
    http.get("/api/study-documents", () => HttpResponse.json(state.docs)),
    http.post("/api/study-documents", async ({ request }) => {
      const form = await request.formData();
      state.uploads += 1;
      state.uploadedName = form.get("file").name;
      state.docs = [DOC];
      return HttpResponse.json(DOC, { status: 201 });
    }),
    http.put("/api/assistant/conversations/5/study-document", async ({ request }) => {
      const body = await request.json();
      state.puts.push(body.document_ids);
      state.conversation = { ...state.conversation, study_document_ids: body.document_ids, study_document_id: body.document_ids[0] ?? null };
      return HttpResponse.json(state.conversation);
    }),
  );
  return state;
}

describe("Interview preparation agent in the assistant", () => {
  it("sends quick actions as normal chat messages and formats the structured answer", async () => {
    const state = backend({ reply: "Based on your resume:\n## Roles that fit\n- **Data Analyst** - fit 75/100\n  - Missing core skills: Statistics.\n1. First question" });
    renderAt("/interview-assistant/5");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Recommend suitable roles" }));
    await waitFor(() => expect(state.posts).toEqual(["Which roles are suitable for my resume?"]));
    const answer = await screen.findByRole("article", { name: "Assistant reply" });
    expect(within(answer).getByText("Roles that fit")).toBeInTheDocument();
    expect(within(answer).getByText("Data Analyst").tagName).toBe("STRONG");
    expect(within(answer).queryByText(/## /)).not.toBeInTheDocument();
    expect(within(answer).getByText("Missing core skills: Statistics.")).toBeInTheDocument();

    for (const [label, message] of [["Analyze my resume", "Analyze my resume"], ["Technical questions", "Generate technical questions"],
      ["HR questions", "Generate HR questions"], ["My preparation roadmap", "Create my preparation roadmap"]]) {
      await user.click(screen.getByRole("button", { name: label }));
      await waitFor(() => expect(state.posts.at(-1)).toBe(message));
    }
  });

  it("selects a role from the picker and links the mock interview for it", async () => {
    const state = backend({ reply: "Target role set: Data Analyst." });
    renderAt("/interview-assistant/5");
    const user = userEvent.setup();
    const picker = await screen.findByRole("combobox", { name: "Prepare for" });
    await waitFor(() => expect(within(picker).getByRole("option", { name: "Data Analyst" })).toBeInTheDocument());
    await user.selectOptions(picker, "data-analyst");
    await waitFor(() => expect(state.posts).toEqual(["Prepare me for Data Analyst"]));
    const mock = await screen.findByRole("link", { name: /Mock interview: Data Analyst/ });
    expect(mock).toHaveAttribute("href", "/interview-prep?role=data-analyst&mode=mock");
  });
});

describe("Document Q&A in the assistant", () => {
  it("uploads a PDF, attaches it to the chat and can stop using it", async () => {
    const state = backend();
    renderAt("/interview-assistant/5");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Upload a study document" }));
    const panel = screen.getByRole("region", { name: "Study documents" });
    const input = panel.querySelector('input[type="file"]');
    await user.upload(input, new File(["%PDF-1.7 test"], "sql_notes.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(state.puts).toEqual([[3]]));
    expect(state.uploads).toBe(1);   // (jsdom reports multipart file names as "blob")
    expect(await within(panel).findByText(/Extracted PDF · 2 pages · 841 characters from sql_notes.pdf/)).toBeInTheDocument();
    expect(await screen.findByText(/Answering from your document:/)).toHaveTextContent("sql_notes.pdf");

    await user.click(screen.getByRole("button", { name: "Stop using it" }));
    await waitFor(() => expect(state.puts).toEqual([[3], []]));
    await waitFor(() => expect(screen.queryByText(/Answering from your document:/)).not.toBeInTheDocument());
  });

  it("checks files before uploading and shows the backend's reason when extraction fails", async () => {
    const state = backend();
    server.use(http.post("/api/study-documents", () => HttpResponse.json(
      { detail: { code: "no_text", message: "No readable text was found in this PDF. It looks scanned. OCR is not available." } }, { status: 422 })));
    renderAt("/interview-assistant/5");
    const user = userEvent.setup({ applyAccept: false });
    await user.click(await screen.findByRole("button", { name: "Upload a study document" }));
    const panel = screen.getByRole("region", { name: "Study documents" });
    const input = panel.querySelector('input[type="file"]');
    await user.upload(input, new File(["hello"], "notes.txt", { type: "text/plain" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("Only PDF and DOCX files are supported.");
    await user.upload(input, new File(["%PDF-1.7"], "scan.pdf", { type: "application/pdf" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("OCR is not available");
    expect(state.puts).toEqual([]);
  });
});

describe("Formatting helpers", () => {
  it("parses headings, bullets, nested bullets and numbered lines", () => {
    expect(blocks("Intro\n## Heading\n- one\n* two\n  - nested\n3. third")).toEqual([
      { type: "text", text: "Intro" }, { type: "heading", text: "Heading" }, { type: "bullet", level: 1, text: "one" },
      { type: "bullet", level: 1, text: "two" }, { type: "bullet", level: 2, text: "nested" }, { type: "numbered", number: "3", text: "third" },
    ]);
  });

  it("links career tracks, study documents and role mock interviews safely", () => {
    expect(sourceLink({ type: "career_track", id: "data-analyst", available: true })).toBe("/career-tracks/data-analyst");
    expect(sourceLink({ type: "career_track", id: "../admin", available: true })).toBe("/career-tracks");
    expect(sourceLink({ type: "study_document", id: "3:0", available: true })).toBeNull();
    expect(sourcesOrigin([{ type: "study_document" }])).toBe("from your document");
    expect(actionLink({ endpoint: "/interviews/sessions", body: { target_role: "java-developer", mode: "mock" } }))
      .toBe("/interview-prep?role=java-developer&mode=mock");
    expect(actionLink({ endpoint: "/interviews/sessions", body: { target_role: "<script>" } })).toBe("/interview-prep");
  });

  it("validates study files like the backend", () => {
    expect(validateStudyFile(new File(["x"], "a.pdf"))).toBeNull();
    expect(validateStudyFile(new File(["x"], "a.docx"))).toBeNull();
    expect(validateStudyFile(new File(["x"], "a.png"))).toBe("Only PDF and DOCX files are supported.");
    expect(validateStudyFile(new File([], "a.pdf"))).toBe("The file is empty.");
  });
});

describe("Two separate assistants", () => {
  it("keeps separate conversation lists and tools, and switches between the assistants", async () => {
    const asked = [];
    server.use(
      http.get("/api/assistant/capabilities", () => HttpResponse.json(caps)),
      http.get("/api/assistant/conversations", ({ request }) => {
        const kind = new URL(request.url).searchParams.get("assistant");
        asked.push(kind);
        const items = kind === "interview" ? [conv({ conversation_id: 9, title: "Prep chat" })]
          : [conv({ conversation_id: 4, title: "How do I upload?", assistant: "application" })];
        return HttpResponse.json({ total: 1, skip: 0, limit: 20, items });
      }),
    );
    renderAt("/assistant");
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { level: 1, name: "Application Assistant" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /How do I upload\?/ })).toHaveAttribute("href", "/assistant/4");
    expect(screen.queryByRole("button", { name: "Recommend suitable roles" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload a study document" })).not.toBeInTheDocument();
    expect(asked).toContain("application");

    const switcher = screen.getByRole("navigation", { name: "Assistants" });
    await user.click(within(switcher).getByRole("link", { name: /Interview Prep Assistant/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Interview Preparation Assistant" })).toBeInTheDocument();
    expect(screen.getByTestId("location").textContent).toBe("/interview-assistant");
    expect(await screen.findByRole("link", { name: /Prep chat/ })).toHaveAttribute("href", "/interview-assistant/9");
    expect(screen.getByRole("button", { name: "Recommend suitable roles" })).toBeInTheDocument();
    expect(asked).toContain("interview");
  });

  it("opens a chat under the assistant it belongs to", async () => {
    backend();
    renderAt("/assistant/5");                       // conversation 5 is an interview chat
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/interview-assistant/5"));
  });
});
