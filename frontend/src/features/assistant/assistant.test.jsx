import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { actionLink, mergeMessages, sourceLink, sourcesOrigin, sourceTypeLabel } from "./assistantFormat";
import { validateMessage } from "./components/Composer";

// Fictional fixtures shaped like backend/schemas/assistant_schema.py (test-only data).
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const LLM_OFF = { available: false, provider: null, model: null, disclosure: null, assistant_disclosure: null };
const LLM_ON = {
  available: true, provider: "groq", model: "llama-3.3-70b-versatile", disclosure: "Generic disclosure.",
  assistant_disclosure: "With AI rewording, only the facts in the assistant's answer are sent to groq. Never sent: the text of your question.",
};
const caps = (llm = LLM_OFF) => ({
  intents: { skill_gap: ["what skills am I lacking"] }, llm,
  limits: { message_chars: 2000, messages_per_minute: 10, messages_per_day: 200, ai_answers_per_hour: 20, conversations: 200, messages_per_conversation: 500 },
  notes: ["Answers use only your own data."],
});
const conv = (id, extra = {}) => ({
  conversation_id: id, title: `Conversation ${id}`, resume_id: null, message_count: 2, last_message_at: "2026-11-16T09:00:00Z",
  created_at: "2026-11-16T08:00:00Z", updated_at: "2026-11-16T09:00:00Z", ...extra,
});
const userMsg = (id, content) => ({
  message_id: id, sender: "user", content, intent: null, sources: [], result_set: null, suggested_actions: [], generation_method: null, warnings: [],
  created_at: "2026-11-16T09:00:00Z",
});
const reply = (id, extra = {}) => ({
  message_id: id, sender: "assistant", content: "Your highest-priority skills to work on:\n- Docker\n- TensorFlow", intent: "skill_gap",
  sources: [
    { type: "skill_gap_recommendation", id: "12", label: "Docker recommendation", available: true },
    { type: "internship", id: "99", label: "Machine Learning Intern at Example Labs", available: true },
    { type: "internship", id: "98", label: "Closed role at Old Co", available: false },
    { type: "application_interview", id: "5", label: "Round 1 interview", available: true },
  ],
  result_set: { kind: "skill", items: [{ type: "skill", id: "Docker", label: "Docker" }, { type: "internship", id: "99", label: "Machine Learning Intern" }] },
  suggested_actions: [
    { label: "See the skill gaps for this internship", method: "GET", endpoint: "/skill-gaps/resumes/12/internships/99", body: {}, requires_confirmation: false },
    { label: "Create a tailored resume", method: "POST", endpoint: "/documents/resume", body: { resume_id: 12, internship_id: 99 }, requires_confirmation: true },
    { label: "Something unknown", method: "POST", endpoint: "/admin/secret", body: {}, requires_confirmation: true },
  ],
  generation_method: "deterministic",
  warnings: [{ code: "internship_closed", detail: "Closed role at Old Co is no longer open." }],
  created_at: "2026-11-16T09:00:05Z",
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

// Mutable backend; records requests.
function backend({ llm = LLM_OFF, conversations = [], stored = {} } = {}) {
  const state = { conversations: structuredClone(conversations), stored: structuredClone(stored), posts: [], creates: 0, listLimits: [], nextId: 100 };
  server.use(
    http.get("/api/assistant/capabilities", () => HttpResponse.json(caps(llm))),
    http.get("/api/assistant/conversations", ({ request }) => {
      const limit = Number(new URL(request.url).searchParams.get("limit"));
      state.listLimits.push(limit);
      return HttpResponse.json({ total: state.conversations.length, skip: 0, limit, items: state.conversations.slice(0, limit) });
    }),
    http.post("/api/assistant/conversations", () => {
      state.creates += 1;
      const c = conv(7, { title: null, message_count: 0, last_message_at: null });
      state.conversations = [c, ...state.conversations];
      state.stored[7] = state.stored[7] || [];
      return HttpResponse.json({ ...c, messages: [] }, { status: 201 });
    }),
    http.get("/api/assistant/conversations/:id", ({ params }) => {
      const c = state.conversations.find((x) => String(x.conversation_id) === params.id);
      if (!c) return HttpResponse.json({ detail: "Conversation not found" }, { status: 404 });
      return HttpResponse.json({ ...c, messages: (state.stored[params.id] || []).slice(-50) });
    }),
    http.post("/api/assistant/conversations/:id/messages", async ({ params, request }) => {
      const body = await request.json();
      state.posts.push({ id: params.id, body });
      const u = userMsg(state.nextId, body.message);
      const a = reply(state.nextId + 1);
      state.nextId += 2;
      state.stored[params.id] = [...(state.stored[params.id] || []), u, a];
      state.conversations = state.conversations.map((c) => (String(c.conversation_id) === params.id ? { ...c, title: "Skill gaps", message_count: c.message_count + 2 } : c));
      return HttpResponse.json({ conversation_id: Number(params.id), user_message: u, assistant_message: a }, { status: 201 });
    }),
  );
  return state;
}
const chat = () => screen.getByRole("region", { name: "Chat" });
const box = () => screen.getByLabelText("Your question");

// ================================================================================================
describe("Assistant: starting and sending", () => {
  it("shows an empty state with suggested questions and the standard (no AI) method", async () => {
    backend();
    renderAt("/assistant");
    expect(await screen.findByRole("heading", { name: "How can I help you use CareerNova AI?" })).toBeInTheDocument();
    const suggestions = screen.getByRole("list", { name: "Suggested questions" });
    // Five questions are sent here; interview preparation is a link to the Interview Preparation Assistant.
    expect(within(suggestions).getAllByRole("button")).toHaveLength(5);
    const prep = within(suggestions).getByRole("link", { name: "Help me prepare for an interview" });
    expect(prep).toHaveAttribute("href", "/interview-assistant");
    expect(await screen.findByText(/AI rewording isn't configured on this server/)).toBeInTheDocument();
    expect(screen.getByText(/No AI is used/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(await screen.findByText("No conversations yet. Your chats are saved here.")).toBeInTheDocument();
    expect(screen.getByText(/Up to 10 messages a minute and 200 a day/)).toBeInTheDocument();
  });

  it("opens the Interview Preparation Assistant from the interview suggestion without sending a message", async () => {
    const state = backend();
    renderAt("/assistant");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: "Help me prepare for an interview" }));
    await waitFor(() => expect(location()).toBe("/interview-assistant"));
    expect(await screen.findByRole("heading", { name: "Let's get you interview-ready" })).toBeInTheDocument();
    expect(state.posts).toHaveLength(0);
    expect(state.creates).toBe(0);
  });

  it("sends a suggested question, creates the conversation and renders the backend's answer with sources", async () => {
    const state = backend();
    renderAt("/assistant");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "What skills are missing from my resume?" }));
    await waitFor(() => expect(location()).toBe("/assistant/7"));
    expect(state.creates).toBe(1);
    expect(state.posts).toEqual([{ id: "7", body: { message: "What skills are missing from my resume?", use_llm: false, llm_consent: false } }]);

    const log = await within(chat()).findByRole("log", { name: "Messages" });
    const [mine, theirs] = within(log).getAllByRole("article");
    expect(mine).toHaveAccessibleName("Your message");
    expect(within(mine).getByText("What skills are missing from my resume?")).toBeInTheDocument();
    expect(theirs).toHaveAccessibleName("Assistant reply");
    expect(within(theirs).getByText(/Your highest-priority skills to work on/)).toBeInTheDocument();
    expect(within(theirs).getByText(/Standard answer/)).toBeInTheDocument();
    expect(within(theirs).getByText("Closed role at Old Co is no longer open.")).toBeInTheDocument();

    const sources = within(theirs).getByRole("list", { name: "Sources" });
    expect(within(sources).getByRole("link", { name: "Docker recommendation" })).toHaveAttribute("href", "/skill-gaps");
    expect(within(sources).getByRole("link", { name: "Machine Learning Intern at Example Labs" })).toHaveAttribute("href", "/internships/99");
    expect(within(sources).queryByRole("link", { name: "Closed role at Old Co" })).not.toBeInTheDocument();
    expect(within(sources).getByText("No longer available")).toBeInTheDocument();
    expect(within(sources).queryByRole("link", { name: "Round 1 interview" })).not.toBeInTheDocument();
    expect(within(sources).getByText("Round 1 interview")).toBeInTheDocument();

    const results = within(theirs).getByRole("list", { name: "Results" });
    expect(within(results).queryByRole("link", { name: "Docker" })).not.toBeInTheDocument();
    expect(within(results).getByRole("link", { name: "Machine Learning Intern" })).toHaveAttribute("href", "/internships/99");

    const actions = within(theirs).getByRole("list", { name: "Suggested next steps" });
    expect(within(actions).getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["See the skill gaps for this internship", "/skill-gaps/internships/99"],
      ["Create a tailored resume", "/documents?type=resume&internship=99&resume=12"],
    ]);
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Your conversations" })).getByRole("link", { name: /Skill gaps/ })).toHaveAttribute("aria-current", "page"));
  });

  it("sends with Enter, keeps Shift+Enter for new lines, and validates empty messages", async () => {
    const state = backend({ conversations: [conv(7, { message_count: 0 })] });
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Conversation 7" });
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(screen.getByText("Type a question first.")).toBeInTheDocument();
    await user.type(box(), "   ");
    await user.keyboard("{Enter}");
    expect(state.posts).toHaveLength(0);
    await user.clear(box());
    await user.type(box(), "Line one{Shift>}{Enter}{/Shift}line two");
    expect(box()).toHaveValue("Line one\nline two");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(state.posts).toHaveLength(1));
    expect(state.posts[0].body.message).toBe("Line one\nline two");
    expect(box()).toHaveValue("");
  });

  it("keeps the text and retries in the same conversation after a failure", async () => {
    const state = backend();
    let fail = true;
    server.use(http.post("/api/assistant/conversations/:id/messages", async ({ params, request }) => {
      const body = await request.json();
      state.posts.push({ id: params.id, body });
      if (fail) {
        fail = false;
        return HttpResponse.json({ detail: "The assistant could not answer right now. Please try again." }, { status: 503 });
      }
      return HttpResponse.json({ conversation_id: 7, user_message: userMsg(1, body.message), assistant_message: reply(2) }, { status: 201 });
    }));
    renderAt("/assistant");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your question"), "What should I learn next?");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    const alert = await screen.findByText(/The assistant could not answer right now/);
    expect(alert.closest("[role=alert]")).toHaveTextContent("Your message wasn't sent.");
    expect(box()).toHaveValue("What should I learn next?");
    await waitFor(() => expect(location()).toBe("/assistant/7"));
    expect(screen.queryByRole("article", { name: "Assistant reply" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Assistant reply" })).toBeInTheDocument();
    expect(state.creates).toBe(1);
    expect(state.posts.map((p) => p.id)).toEqual(["7", "7"]);
    expect(box()).toHaveValue("");
  });

  it.each([
    [429, { detail: "Too many assistant requests. Try again in 42 seconds." }, { "Retry-After": "42" }, /Slow down a little\. Too many assistant requests\. Try again in 42 seconds\. \(about 42 s\)/],
    [422, { detail: [{ loc: ["body", "message"], msg: "Value error, Cannot be blank.", type: "value_error" }] }, {}, /Your message wasn't sent/],
    [409, { detail: "This conversation has reached 500 messages. Start a new conversation." }, {}, /reached 500 messages/],
  ])("shows a %s error without losing the text", async (status, body, headers, message) => {
    backend({ conversations: [conv(7)], stored: { 7: [] } });
    server.use(http.post("/api/assistant/conversations/:id/messages", () => HttpResponse.json(body, { status, headers })));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Conversation 7" });
    await user.type(box(), "Where do my applications stand?");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(within(chat()).getByRole("alert")).toHaveTextContent(message));
    expect(box()).toHaveValue("Where do my applications stand?");
    if (status === 409) expect(screen.getByRole("button", { name: "Start a new conversation" })).toBeInTheDocument();
  });

  it("reports network failures", async () => {
    backend({ conversations: [conv(7)], stored: { 7: [] } });
    server.use(http.post("/api/assistant/conversations/:id/messages", () => HttpResponse.error()));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Conversation 7" });
    await user.type(box(), "Hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText(/Cannot reach the server/)).toBeInTheDocument();
    expect(box()).toHaveValue("Hello");
  });

  it("sends only one message when Send is pressed repeatedly", async () => {
    const state = backend({ conversations: [conv(7)], stored: { 7: [] } });
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    server.use(http.post("/api/assistant/conversations/:id/messages", async ({ request }) => {
      const body = await request.json();
      state.posts.push(body);
      await held;
      return HttpResponse.json({ conversation_id: 7, user_message: userMsg(1, body.message), assistant_message: reply(2) }, { status: 201 });
    }));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Conversation 7" });
    await user.type(box(), "Help me prepare for an interview.");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("The assistant is looking at your data…")).toBeInTheDocument();
    expect(screen.getByText("Sending…", { selector: "p" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await user.type(box(), "x{Enter}");
    await waitFor(() => expect(state.posts).toHaveLength(1));
    release();
    expect(await screen.findByRole("article", { name: "Assistant reply" })).toBeInTheDocument();
    expect(state.posts).toHaveLength(1);
  });
});

// ================================================================================================
describe("Assistant: history and management", () => {
  it("lists conversations, opens one in message order and loads earlier messages", async () => {
    const older = [userMsg(1, "First question"), reply(2, { content: "First answer", sources: [], suggested_actions: [], warnings: [], result_set: null })];
    const recent = [userMsg(3, "Second question"), reply(4, { content: "Second answer", sources: [], suggested_actions: [], warnings: [], result_set: null })];
    const state = backend({ conversations: [conv(7, { message_count: 4 }), conv(8, { title: "Interview help" })], stored: { 7: recent } });
    const befores = [];
    server.use(http.get("/api/assistant/conversations/7/messages", ({ request }) => {
      befores.push(new URL(request.url).searchParams.get("before_id"));
      return HttpResponse.json(older);
    }));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    const list = await screen.findByRole("list", { name: "Your conversations" });
    expect(within(list).getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual(["/assistant/7", "/assistant/8"]);
    expect(within(list).getByRole("link", { name: /Conversation 7/ })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Second answer")).toBeInTheDocument();
    expect(screen.getByText("No sources for this answer", { exact: false })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Load earlier messages" }));
    await waitFor(() => expect(within(screen.getByRole("log")).getAllByRole("article")).toHaveLength(4));
    expect(befores).toEqual(["3"]);
    expect(within(screen.getByRole("log")).getAllByRole("article").map((a) => a.querySelector("p").textContent)).toEqual([
      "First question", "First answer", "Second question", "Second answer",
    ]);
    expect(screen.queryByRole("button", { name: "Load earlier messages" })).not.toBeInTheDocument();

    await user.click(within(list).getByRole("link", { name: /Interview help/ }));
    await waitFor(() => expect(location()).toBe("/assistant/8"));
    expect(await screen.findByRole("heading", { name: "Interview help" })).toBeInTheDocument();
    expect(screen.queryByText("Second answer")).not.toBeInTheDocument();
    expect(state.listLimits[0]).toBe(20);
  });

  it("shows more conversations through the backend's paging", async () => {
    const many = Array.from({ length: 25 }, (_, i) => conv(i + 1));
    const state = backend({ conversations: many });
    renderAt("/assistant");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Show more (5 older)" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Your conversations" })).getAllByRole("link")).toHaveLength(25));
    expect(state.listLimits).toEqual([20, 40]);
  });

  it("renames a conversation", async () => {
    backend({ conversations: [conv(7)], stored: { 7: [] } });
    const patches = [];
    server.use(http.patch("/api/assistant/conversations/7", async ({ request }) => {
      const body = await request.json();
      patches.push(body);
      return HttpResponse.json(conv(7, { title: body.title }));
    }));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Rename" }));
    await user.clear(screen.getByLabelText("Conversation title"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("Enter a title.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Conversation title"), "  Data roles  ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("heading", { name: "Data roles" })).toBeInTheDocument();
    expect(patches).toEqual([{ title: "Data roles" }]);
  });

  it("deletes a conversation only after confirmation", async () => {
    const state = backend({ conversations: [conv(7)], stored: { 7: [] } });
    const deletes = [];
    server.use(http.delete("/api/assistant/conversations/7", ({ request }) => {
      deletes.push(new URL(request.url).search);
      state.conversations = [];
      return new HttpResponse(null, { status: 204 });
    }));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(deletes).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Your resumes, applications and other data are not affected.");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete conversation" }));
    await waitFor(() => expect(location()).toBe("/assistant"));
    expect(deletes).toEqual(["?confirm=true"]);
    expect(await screen.findByText("No conversations yet. Your chats are saved here.")).toBeInTheDocument();
  });

  it("shows not found for a missing or another student's conversation", async () => {
    backend();
    renderAt("/assistant/77");
    expect(await screen.findByText("Conversation not found")).toBeInTheDocument();
    expect(screen.queryByLabelText("Your question")).not.toBeInTheDocument();
  });

  it("retries a conversation that failed to load", async () => {
    const state = backend({ conversations: [conv(7)], stored: { 7: [userMsg(1, "Hi")] } });
    let calls = 0;
    server.use(http.get("/api/assistant/conversations/7", () => {
      calls += 1;
      return calls === 1 ? HttpResponse.json({ detail: "Forbidden" }, { status: 403 }) : HttpResponse.json({ ...state.conversations[0], messages: state.stored[7] });
    }));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await user.click(await within(chat()).findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Hi")).toBeInTheDocument();
  });

  it("toggles the conversation list on small screens", async () => {
    backend({ conversations: [conv(7)] });
    renderAt("/assistant");
    const user = userEvent.setup();
    const toggle = await screen.findByRole("button", { name: /Conversations/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("assistant-conversations")).toHaveClass("block");
  });

  it("sends the student to sign in when the session has expired", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    const expired = () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 });
    server.use(
      http.get("/api/assistant/capabilities", expired),
      http.get("/api/assistant/conversations", expired),
      http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })),
    );
    renderAt("/assistant");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/login?next=%2Fassistant"));
  });
});

// ================================================================================================
describe("Assistant: AI consent", () => {
  it("keeps AI off by default and requires explicit consent before sending use_llm", async () => {
    const state = backend({ llm: LLM_ON, conversations: [conv(7)], stored: { 7: [] } });
    renderAt("/assistant/7");
    const user = userEvent.setup();
    const ai = await screen.findByRole("checkbox", { name: "Use AI rewording (groq, llama-3.3-70b-versatile)" });
    expect(ai).not.toBeChecked();
    expect(screen.queryByText(LLM_ON.assistant_disclosure)).not.toBeInTheDocument();

    await user.type(box(), "Which internships match my profile?");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(state.posts).toHaveLength(1));
    expect(state.posts[0].body).toEqual({ message: "Which internships match my profile?", use_llm: false, llm_consent: false });

    await user.click(ai);
    expect(screen.getByText(LLM_ON.assistant_disclosure)).toBeInTheDocument();
    await user.type(box(), "And again with AI");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Accept the disclosure to use AI rewording, or turn it off.")).toBeInTheDocument();
    expect(state.posts).toHaveLength(1);
    expect(box()).toHaveValue("And again with AI");

    await user.click(screen.getByRole("checkbox", { name: "I have read this and agree to AI rewording for my messages in this conversation" }));
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(state.posts).toHaveLength(2));
    expect(state.posts[1].body).toEqual({ message: "And again with AI", use_llm: true, llm_consent: true });
  });

  it("shows the backend's AI error when the provider is unavailable", async () => {
    backend({ llm: LLM_ON, conversations: [conv(7)], stored: { 7: [] } });
    server.use(http.post("/api/assistant/conversations/:id/messages", () => HttpResponse.json({ detail: "AI assistance is not configured on this server." }, { status: 503 })));
    renderAt("/assistant/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: /Use AI rewording/ }));
    await user.click(screen.getByRole("checkbox", { name: /I have read this and agree/ }));
    await user.type(box(), "Hi");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText(/AI assistance is not configured on this server/)).toBeInTheDocument();
  });

  it("falls back to the standard method when capabilities can't be loaded", async () => {
    backend();
    server.use(http.get("/api/assistant/capabilities", () => HttpResponse.json({ detail: "Service unavailable" }, { status: 503 })));
    renderAt("/assistant");
    expect(await screen.findByText(/AI rewording status couldn't be checked, so it's turned off/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("labels AI-reworded answers", async () => {
    backend({ conversations: [conv(7)], stored: { 7: [reply(2, { generation_method: "llm", warnings: [] })] } });
    renderAt("/assistant/7");
    expect(await screen.findByText(/AI-reworded \(fact-checked\)/)).toBeInTheDocument();
  });
});

// ================================================================================================
describe("Assistant integration and helpers", () => {
  it("links recent conversations on the dashboard", async () => {
    server.use(http.get("/api/assistant/conversations", () => HttpResponse.json({ total: 1, skip: 0, limit: 3, items: [conv(7, { title: "Skill gaps" })] })));
    renderAt("/");
    const card = (await screen.findByRole("heading", { name: "AI assistants" })).closest("section");
    expect(await within(card).findByRole("link", { name: "Continue conversation: Skill gaps" })).toHaveAttribute("href", "/assistant/7");
    expect(within(card).getByRole("link", { name: /Ask the Application Assistant/ })).toHaveAttribute("href", "/assistant");
  });

  it("maps sources and actions only to existing pages", () => {
    expect(sourceLink({ type: "resume_fact", id: "12:experience-1" })).toBe("/resumes/12");
    expect(sourceLink({ type: "document", id: "31" })).toBe("/documents/31");
    expect(sourceLink({ type: "interview_session", id: "41" })).toBe("/interview-prep/sessions/41");
    expect(sourceLink({ type: "application", id: "21" })).toBe("/applications/21");
    expect(sourceLink({ type: "application", id: "21", available: false })).toBeNull();
    expect(sourceLink({ type: "internship", id: "javascript:alert(1)" })).toBeNull();
    expect(sourceLink({ type: "unknown_kind", id: "1" })).toBeNull();
    expect(actionLink({ endpoint: "/interviews/sessions", body: { resume_id: 12, internship_id: 99 } })).toBe("/interview-prep?internship=99&resume=12");
    expect(actionLink({ endpoint: "/applications/bookmarks/99" })).toBe("/internships/99");
    expect(actionLink({ endpoint: "/applications", body: { internship_id: 99 } })).toBe("/internships/99");
    expect(actionLink({ endpoint: "/matches/resumes/12" })).toBe("/matches");
    expect(actionLink({ endpoint: "/resumes/upload" })).toBe("/resumes");
    expect(actionLink({ endpoint: "https://evil.example/x" })).toBeNull();
    // Step-by-step guidance links: exactly these in-app pages, nothing derived from them.
    for (const page of ["/profile", "/resumes", "/matches", "/internships", "/skill-gaps", "/interview-prep", "/documents", "/career-tracks"])
      expect(actionLink({ endpoint: page })).toBe(page);
    for (const bad of ["/admin", "/profile/../admin", "/profile?x=1", "//evil.example", "/resumes/"])
      expect(actionLink({ endpoint: bad })).toBeNull();
  });

  it("orders messages by id without duplicates and validates length", () => {
    expect(mergeMessages([{ message_id: 3 }, { message_id: 1 }], [{ message_id: 3, x: 1 }, { message_id: 2 }]).map((m) => m.message_id)).toEqual([1, 2, 3]);
    expect(validateMessage("  ")).toBe("Type a question first.");
    expect(validateMessage("x".repeat(2001))).toBe("Keep your message under 2,000 characters.");
    expect(validateMessage("ok")).toBeNull();
  });
});

// ================================================================================================
describe("Assistant: product questions (RAG product guide)", () => {
  const guideReply = (id) => reply(id, {
    intent: "product_help",
    content: "Here is what the CareerNova AI guide says:\n- Matching compares your resume with each internship.",
    sources: [{ type: "product_doc", id: "04_internship_matching#2", label: "Product guide: Internship discovery and matching › How matching works", available: true }],
    result_set: null, suggested_actions: [], warnings: [],
  });

  it("offers product questions and shows the cited guide sections without links", async () => {
    const state = backend();
    server.use(
      http.post("/api/assistant/conversations/:id/messages", async ({ params, request }) => {
        const body = await request.json();
        state.posts.push({ id: params.id, body });
        return HttpResponse.json({ conversation_id: Number(params.id), user_message: userMsg(100, body.message), assistant_message: guideReply(101) }, { status: 201 });
      }),
    );
    renderAt("/assistant");
    const about = await screen.findByRole("list", { name: "Questions about CareerNova AI" });
    expect(within(about).getAllByRole("button")).toHaveLength(4);
    await userEvent.setup().click(within(about).getByRole("button", { name: "How does internship matching work?" }));
    await waitFor(() => expect(state.posts).toEqual([{ id: "7", body: { message: "How does internship matching work?", use_llm: false, llm_consent: false } }]));

    const log = await within(chat()).findByRole("log", { name: "Messages" });
    const theirs = within(log).getAllByRole("article")[1];
    expect(within(theirs).getByText(/Matching compares your resume/)).toBeInTheDocument();
    expect(within(theirs).getByText("Based on 1 source from the product guide")).toBeInTheDocument();
    const sources = within(theirs).getByRole("list", { name: "Sources" });
    expect(within(sources).getByText("Product guide:")).toBeInTheDocument();
    expect(within(sources).getByText(/How matching works/)).toBeInTheDocument();
    expect(within(sources).queryByRole("link")).not.toBeInTheDocument();
  });

  it("labels product-guide sources", () => {
    expect(sourceTypeLabel("product_doc")).toBe("Product guide");
    expect(sourceLink({ type: "product_doc", id: "01_overview#1" })).toBeNull();
    expect(sourcesOrigin([{ type: "product_doc" }])).toBe("from the product guide");
    expect(sourcesOrigin([{ type: "product_doc" }, { type: "resume" }])).toBe("from your data and the product guide");
    expect(sourcesOrigin([{ type: "resume" }])).toBe("from your data");
    expect(sourcesOrigin(undefined)).toBe("from your data");
  });
});
