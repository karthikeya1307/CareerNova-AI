import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import { validateAnswer } from "./components/QuestionCard";
import { validateSessionForm } from "./components/StartSessionForm";
import { categoryLabel, scoreTone, sessionStatus } from "./interviewFormat";

// Fictional fixtures shaped like backend/schemas/interview_schema.py (test-only data).
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
const LLM_OFF = { available: false, provider: null, model: null, disclosure: null };
const LLM_ON = { available: true, provider: "groq", model: "llama-3.3-70b-versatile", disclosure: "Relevant resume content is sent to groq. Your contact details are removed first." };
const BANK = { technical_version: "1", behavioral_version: "1", skills_covered: 24, technical_questions: 180, by_difficulty: { easy: 60, medium: 70, hard: 50 }, behavioral_questions: 30 };

const question = (id, position, category, extra = {}) => ({
  question_id: id, position, category, difficulty: "medium", text: `Question ${id} text?`, skill: null, skill_status: null,
  source_fact_ids: [], time_limit_seconds: null, answered: false, attempts: 0, latest_score: null, latest_feedback: null,
  evaluation: null, revealed: false, key_points: ["Point A", "Point B"], explanation: "Why this matters.",
  suggested_answer: { type: "key_points", points: ["Point A", "Point B"], explanation: "Why this matters.", note: null }, ...extra,
});
const SESSION = {
  session_id: 41, title: "Practice interview - Machine Learning Intern at Example Labs", mode: "practice", status: "started",
  resume_id: 12, internship_id: 99, difficulty: "mixed", question_mix: { technical: 1, project: 2, behavioral: 1, internship: 0 },
  generation_method: "deterministic", total_questions: 3, answered_count: 0, score: null,
  summary: { generation: { checked_statements: 0, warnings: [], rejected_statements: [], llm: { used: false, accepted: 0, rejected: 0 } }, requested_questions: 4 },
  notices: [{ code: "fewer_questions", category: "project", requested: 2, generated: 1, detail: "Your resume has 1 project or experience entry to ask about." }],
  started_at: "2026-11-16T10:00:00Z", completed_at: null,
  questions: [
    question(1, 1, "technical", { text: "What is overfitting and how do you prevent it?", skill: "Machine Learning", difficulty: "easy" }),
    question(2, 2, "behavioral", { text: "Tell me about a time you worked in a team.", suggested_answer: { type: "star", points: ["Situation", "Task", "Action", "Result"], tips: ["Keep it short."], possible_stories: ["Movie Recommender"] } }),
    question(3, 3, "project", { text: "Walk me through your Movie Recommender project." }),
  ],
};
const ANSWER = {
  answer_id: 501, question_id: 1, attempt: 1, answer_text: "Overfitting is when a model memorises training data.", time_taken_seconds: 5,
  score: 72.5, label: "Good", feedback: "Key-point coverage 72.5/100 (Good). Automated guidance, not a hiring decision.", feedback_source: "rubric",
  created_at: "2026-11-16T10:05:00Z",
  evaluation: {
    score: 72.5, label: "Good", word_count: 48, components: { key_point_coverage: 0.75, length: 1 }, category: "technical", method: "keyword",
    covered_points: [{ point: "Explain what overfitting is", matched_by: "keyword", similarity: null }],
    missed_points: [{ point: "Mention regularisation", similarity: null, reason: "not_covered" }],
    incorrect_statements: [], tips: ["Say how you would detect it."], caps_applied: [], advisories: [],
  },
};
const COMPLETED = {
  ...SESSION, status: "completed", completed_at: "2026-11-16T10:30:00Z", answered_count: 1, score: 24.2,
  questions: SESSION.questions.map((q) => (q.question_id === 1 ? { ...q, answered: true, attempts: 1, latest_score: 72.5, latest_feedback: ANSWER.feedback, evaluation: ANSWER.evaluation } : q)),
  summary: {
    ...SESSION.summary, overall_score: 24.2, label: "Needs work", answered: 1, total: 3, unanswered_count_as_zero: true, average_answered_score: 72.5,
    by_category: { technical: 72.5 }, strengths: ["technical: What is overfitting and how do you prevent it?"], improvements: [],
    related_skill_gaps: [{ recommendation_id: 9, skill: "Machine Learning", status: "in_progress", priority_score: 0.8 }],
  },
};
const LIST_ITEM = (s) => ({ session_id: s.session_id, title: s.title, mode: s.mode, status: s.status, internship_id: s.internship_id, resume_id: s.resume_id,
  total_questions: s.total_questions, answered_count: s.answered_count, score: s.score, started_at: s.started_at, completed_at: s.completed_at });

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

// Mutable backend: GET returns the current session; answers and completion change it.
function backend({ llm = LLM_OFF, resumes = [FAILED, LATEST, OLDER], sessions = [], session = SESSION } = {}) {
  const state = { session: structuredClone(session), posts: [], answers: [] };
  server.use(
    http.get("/api/resumes/", () => HttpResponse.json(resumes)),
    http.get("/api/documents/llm-status", () => HttpResponse.json(llm)),
    http.get("/api/interviews/question-bank/version", () => HttpResponse.json(BANK)),
    http.get("/api/interviews/sessions", () => HttpResponse.json(sessions)),
    http.get("/api/internships/", () => HttpResponse.json({ total: 1, skip: 0, limit: 8, items: [INTERNSHIP] })),
    http.get("/api/internships/99", () => HttpResponse.json(INTERNSHIP)),
    http.get("/api/interviews/sessions/41", () => HttpResponse.json(state.session)),
    http.post("/api/interviews/sessions/41/questions/:qid/answers", async ({ params, request }) => {
      const body = await request.json();
      state.answers.push(body);
      const qid = Number(params.qid);
      state.session.questions = state.session.questions.map((q) =>
        q.question_id === qid ? { ...q, answered: true, attempts: q.attempts + 1, latest_score: ANSWER.score, latest_feedback: ANSWER.feedback, evaluation: ANSWER.evaluation } : q);
      state.session.status = "in_progress";
      state.session.answered_count = state.session.questions.filter((q) => q.answered).length;
      return HttpResponse.json({ ...ANSWER, question_id: qid, answer_text: body.answer_text }, { status: 201 });
    }),
  );
  return state;
}
function capturePost(path, response) {
  const bodies = [];
  server.use(http.post(path, async ({ request }) => {
    bodies.push(await request.json().catch(() => null));
    return typeof response === "function" ? response() : HttpResponse.json(response, { status: 201 });
  }));
  return bodies;
}
const startForm = () => screen.getByRole("form", { name: "Start an interview session" });

// ================================================================================================
describe("Interview preparation landing page", () => {
  it("offers only the backend's options, defaults to the latest parsed resume and starts a practice session", async () => {
    backend({ sessions: [LIST_ITEM(COMPLETED)] });
    const bodies = capturePost("/api/interviews/sessions", SESSION);
    renderAt("/interview-prep");
    const user = userEvent.setup();

    const resumeSelect = await screen.findByLabelText("Resume to use");
    expect(within(resumeSelect).getAllByRole("option").map((o) => o.textContent)).toEqual([
      expect.stringContaining("Asha_Resume_2026.pdf"),
      expect.stringContaining("Asha_Resume_2025.docx"),
    ]);
    expect(resumeSelect).toHaveValue("12");
    expect(screen.getAllByRole("radio").map((r) => r.value)).toEqual(["practice", "mock"]);
    expect(screen.getByRole("radio", { name: /^Practice/ })).toBeChecked();
    expect(within(screen.getByLabelText("Difficulty")).getAllByRole("option").map((o) => o.value)).toEqual(["mixed", "easy", "medium", "hard"]);
    expect(screen.getByLabelText("Technical")).toHaveValue("3");
    expect(screen.getByLabelText("Internship-specific")).toHaveValue("1");
    expect(screen.queryByLabelText(/Time limit per question/)).not.toBeInTheDocument(); // mock mode only
    expect(await screen.findByText(/No AI is used/)).toBeInTheDocument();
    expect(await screen.findByText(/180 technical questions across 24 skills/)).toBeInTheDocument();

    const history = await screen.findByRole("list", { name: "Interview sessions" });
    const link = within(history).getByRole("link");
    expect(link).toHaveAttribute("href", "/interview-prep/sessions/41");
    expect(within(link).getByText("Score 24.2/100")).toBeInTheDocument();
    expect(within(link).getByText("1/3 answered")).toBeInTheDocument();

    await user.click(within(startForm()).getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(location()).toBe("/interview-prep/sessions/41"));
    expect(bodies).toEqual([{
      resume_id: 12, internship_id: null, mode: "practice", mix: { technical: 3, project: 2, behavioral: 2, internship: 1 },
      difficulty: "mixed", time_limit_seconds: null, use_llm: false, llm_consent: false,
    }]);
    expect(await screen.findByText(/Your questions are ready/)).toBeInTheDocument();
  });

  it("uses the internship from the link and sends mock mode, difficulty, mix and time limit", async () => {
    backend();
    const bodies = capturePost("/api/interviews/sessions", SESSION);
    renderAt("/interview-prep?internship=99&resume=5");
    const user = userEvent.setup();
    expect(await screen.findByText("Machine Learning Intern")).toBeInTheDocument();
    expect(screen.getByLabelText("Resume to use")).toHaveValue("5");
    await user.click(screen.getByRole("radio", { name: /^Mock interview/ }));
    await user.selectOptions(screen.getByLabelText("Difficulty"), "hard");
    await user.clear(screen.getByLabelText("Technical"));
    await user.type(screen.getByLabelText("Technical"), "5");
    await user.type(screen.getByLabelText(/Time limit per question/), "120");
    await user.click(screen.getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({
      resume_id: 5, internship_id: 99, mode: "mock", mix: { technical: 5, project: 2, behavioral: 2, internship: 1 },
      difficulty: "hard", time_limit_seconds: 120, use_llm: false, llm_consent: false,
    });
  });

  it("lets the student choose an internship by searching, or clear it", async () => {
    backend();
    const bodies = capturePost("/api/interviews/sessions", SESSION);
    renderAt("/interview-prep");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Search internships/), "machine");
    await user.click(screen.getByRole("button", { name: "Find internships" }));
    await user.click(await within(await screen.findByRole("list", { name: "Internship search results" })).findByRole("button", { name: /Machine Learning Intern/ }));
    expect(screen.getByText("Target internship (optional)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(bodies[0]?.internship_id).toBe(99));
  });

  it("validates the question mix and time limit before calling the API", async () => {
    backend();
    const bodies = capturePost("/api/interviews/sessions", SESSION);
    renderAt("/interview-prep");
    const user = userEvent.setup();
    for (const name of ["Technical", "Project / experience", "Behavioural", "Internship-specific"]) {
      await user.clear(await screen.findByLabelText(name));
      await user.type(screen.getByLabelText(name), "0");
    }
    await user.click(screen.getByRole("button", { name: "Start interview" }));
    expect(await screen.findByText(/Choose 1–15 questions in total \(currently 0\)/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Technical"));
    await user.type(screen.getByLabelText("Technical"), "11");
    await user.click(screen.getByRole("radio", { name: /^Mock interview/ }));
    await user.type(screen.getByLabelText(/Time limit per question/), "10");
    await user.click(screen.getByRole("button", { name: "Start interview" }));
    expect(await screen.findByText("Enter a whole number from 0 to 10.")).toBeInTheDocument();
    expect(screen.getByText(/Enter 30–900 seconds/)).toBeInTheDocument();
    expect(bodies).toHaveLength(0);
  });

  it("requires explicit consent before asking for AI-tailored questions", async () => {
    backend({ llm: LLM_ON });
    const bodies = capturePost("/api/interviews/sessions", SESSION);
    renderAt("/interview-prep");
    const user = userEvent.setup();
    const aiBox = await screen.findByRole("checkbox", { name: "Use AI-tailored questions (groq, llama-3.3-70b-versatile)" });
    expect(aiBox).not.toBeChecked();
    expect(screen.queryByText(LLM_ON.disclosure)).not.toBeInTheDocument();
    await user.click(aiBox);
    expect(screen.getByText(LLM_ON.disclosure)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start interview" }));
    expect(await screen.findByText(/Accept the disclosure to use AI-tailored questions/)).toBeInTheDocument();
    expect(bodies).toHaveLength(0);
    await user.click(screen.getByRole("checkbox", { name: "I have read this and agree to AI-tailored questions for this session" }));
    await user.click(screen.getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ use_llm: true, llm_consent: true });
  });

  it.each([
    [422, "No parsed information is available for this resume."],
    [404, "Internship not found"],
    [503, "AI assistance is not configured on this server."],
  ])("shows the backend's %s error and keeps the form", async (status, detail) => {
    backend();
    capturePost("/api/interviews/sessions", () => HttpResponse.json({ detail }, { status }));
    renderAt("/interview-prep");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start interview" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The session couldn't be started");
    expect(alert).toHaveTextContent(detail);
    expect(location()).toBe("/interview-prep");
    expect(screen.getByRole("button", { name: "Start interview" })).toBeEnabled();
  });

  it("reports network failures", async () => {
    backend();
    capturePost("/api/interviews/sessions", () => HttpResponse.error());
    renderAt("/interview-prep");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start interview" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the server/);
  });

  it("creates only one session when Start is clicked repeatedly", async () => {
    backend();
    let posts = 0;
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    server.use(http.post("/api/interviews/sessions", async () => {
      posts += 1;
      await held;
      return HttpResponse.json(SESSION, { status: 201 });
    }));
    renderAt("/interview-prep");
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: "Start interview" });
    await user.click(button);
    await user.click(button);
    await waitFor(() => expect(posts).toBe(1));
    release();
    await waitFor(() => expect(location()).toBe("/interview-prep/sessions/41"));
    expect(posts).toBe(1);
  });

  it("asks for a parsed resume first", async () => {
    backend({ resumes: [FAILED] });
    renderAt("/interview-prep");
    expect(await screen.findByText("Upload a resume first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to resumes" })).toHaveAttribute("href", "/resumes");
  });

  it("filters the history by status, shows an empty state and retries after an error", async () => {
    backend();
    const queries = [];
    let fail = true;
    server.use(http.get("/api/interviews/sessions", ({ request }) => {
      queries.push(new URL(request.url).searchParams.get("status"));
      if (fail) {
        fail = false;
        return HttpResponse.json({ detail: "Service unavailable" }, { status: 503 });
      }
      return HttpResponse.json([]);
    }));
    renderAt("/interview-prep");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No sessions yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Completed" }));
    expect(await screen.findByText("No sessions with this status")).toBeInTheDocument();
    expect(queries).toEqual([null, null, "completed"]);
    expect(location()).toBe("/interview-prep?show=completed");
  });
});

// ================================================================================================
describe("Answering an interview session", () => {
  it("shows the backend's questions, notices and progress, and keeps drafts while navigating", async () => {
    backend();
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: SESSION.title })).toBeInTheDocument();
    expect(screen.getByText("Not started")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Session notices" })).getByText(/Your resume has 1 project/)).toHaveTextContent("Project / experience: 1 of 2");
    const nav = screen.getByRole("navigation", { name: "Questions" });
    expect(within(nav).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Question 1, Technical, unanswered", "Question 2, Behavioural, unanswered", "Question 3, Project / experience, unanswered",
    ]);
    expect(screen.getByRole("heading", { name: "What is overfitting and how do you prevent it?" })).toBeInTheDocument();
    expect(screen.getByText("Easy")).toBeInTheDocument();
    expect(screen.getByText("Machine Learning")).toBeInTheDocument();
    expect(screen.getByText("Unanswered")).toBeInTheDocument();
    expect(screen.getByText("Question 1 of 3")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Your answer"), "Draft for question one");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(location()).toBe("/interview-prep/sessions/41?q=1"));
    expect(screen.getByRole("heading", { name: "Tell me about a time you worked in a team." })).toBeInTheDocument();
    expect(screen.getByText("Structure your answer (STAR)")).toBeInTheDocument();
    expect(screen.getByLabelText("Your answer")).toHaveValue("");
    await user.click(within(nav).getByRole("button", { name: /Question 1,/ }));
    expect(screen.getByLabelText("Your answer")).toHaveValue("Draft for question one");
  });

  it("submits an answer and shows the backend's score, feedback, strengths and improvements", async () => {
    const state = backend();
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your answer"), "Overfitting is when a model memorises training data.");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    const evaluation = await screen.findByRole("region", { name: "Evaluation" });
    expect(within(evaluation).getByText("72.5")).toBeInTheDocument();
    expect(within(evaluation).getByText("Good")).toBeInTheDocument();
    expect(within(evaluation).getByText("Rubric feedback (no AI)")).toBeInTheDocument();
    expect(within(evaluation).getByText(ANSWER.feedback)).toBeInTheDocument();
    expect(within(within(evaluation).getByRole("list", { name: "Key points covered" })).getByText("Explain what overfitting is")).toBeInTheDocument();
    expect(within(within(evaluation).getByRole("list", { name: "Key points missed" })).getByText("Mention regularisation")).toBeInTheDocument();
    expect(within(evaluation).getByText("Say how you would detect it.")).toBeInTheDocument();

    expect(state.answers).toHaveLength(1);
    expect(state.answers[0]).toMatchObject({ answer_text: "Overfitting is when a model memorises training data.", use_llm_feedback: false, llm_consent: false });
    expect(Number.isInteger(state.answers[0].time_taken_seconds)).toBe(true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Question 1, Technical, answered" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Finish session \(2 unanswered\)/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByLabelText("Your answer")).toHaveValue("Overfitting is when a model memorises training data.");
    expect(screen.getByRole("button", { name: "Submit new attempt" })).toBeInTheDocument();
  });

  it("validates blank answers and sends nothing", async () => {
    const state = backend();
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your answer"), "   ");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    expect(await screen.findByText("Write an answer before submitting.")).toBeInTheDocument();
    expect(state.answers).toHaveLength(0);
  });

  it.each([
    ["a 503", () => HttpResponse.json({ detail: "AI assistance is not configured on this server." }, { status: 503 }), "AI assistance is not configured"],
    ["a network failure", () => HttpResponse.error(), /Cannot reach the server/],
  ])("keeps the typed answer after %s", async (_name, reply, message) => {
    backend();
    server.use(http.post("/api/interviews/sessions/41/questions/:qid/answers", reply));
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your answer"), "My careful answer");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your answer couldn't be evaluated");
    expect(alert).toHaveTextContent(message);
    expect(screen.getByLabelText("Your answer")).toHaveValue("My careful answer");
    expect(screen.getByRole("button", { name: "Submit answer" })).toBeEnabled();
  });

  it("reloads a session that was closed elsewhere (409) without losing the answer text", async () => {
    const state = backend();
    server.use(http.post("/api/interviews/sessions/41/questions/:qid/answers", () => {
      state.session = structuredClone(COMPLETED);
      return HttpResponse.json({ detail: "This interview session is closed." }, { status: 409 });
    }));
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your answer"), "Late answer");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Your answer")).not.toBeInTheDocument();
  });

  it("sends only one answer when Submit is clicked repeatedly", async () => {
    const state = backend();
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    server.use(http.post("/api/interviews/sessions/41/questions/:qid/answers", async ({ request }) => {
      state.answers.push(await request.json());
      await held;
      return HttpResponse.json(ANSWER, { status: 201 });
    }));
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your answer"), "An answer");
    const button = screen.getByRole("button", { name: "Submit answer" });
    await user.click(button);
    await user.click(button);
    await waitFor(() => expect(state.answers).toHaveLength(1));
    release();
    expect(await screen.findByRole("region", { name: "Evaluation" })).toBeInTheDocument();
    expect(state.answers).toHaveLength(1);
  });

  it("asks for consent before sending an answer for AI feedback", async () => {
    const state = backend({ llm: LLM_ON });
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    const box = await screen.findByRole("checkbox", { name: "Use AI feedback (groq, llama-3.3-70b-versatile)" });
    expect(box).not.toBeChecked();
    await user.click(box);
    await user.type(screen.getByLabelText("Your answer"), "An answer");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    expect(await screen.findByText("Accept the disclosure to get AI feedback, or turn it off.")).toBeInTheDocument();
    expect(state.answers).toHaveLength(0);
    await user.click(screen.getByRole("checkbox", { name: "I have read this and agree to send my answers for AI feedback in this session" }));
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    await waitFor(() => expect(state.answers).toHaveLength(1));
    expect(state.answers[0]).toMatchObject({ use_llm_feedback: true, llm_consent: true });
  });

  it("hides the model answer in mock mode until it is revealed", async () => {
    const hidden = { ...SESSION, mode: "mock", questions: SESSION.questions.map((q) => ({ ...q, key_points: null, explanation: null, suggested_answer: null, time_limit_seconds: 120 })) };
    backend({ session: hidden });
    const reveals = [];
    server.use(http.post("/api/interviews/sessions/41/questions/:qid/reveal", ({ params }) => {
      reveals.push(params.qid);
      return HttpResponse.json({ ...SESSION.questions[0], time_limit_seconds: 120, revealed: true });
    }));
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    expect(await screen.findByText(/model answer is hidden until you answer/)).toBeInTheDocument();
    expect(screen.getByText("Time limit 120s")).toBeInTheDocument();
    expect(screen.queryByText("Point A")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reveal the model answer" }));
    expect(await screen.findByText("Point A")).toBeInTheDocument();
    expect(reveals).toEqual(["1"]);
  });

  it("finishes the session after confirmation and shows the backend's results", async () => {
    const state = backend();
    const completes = capturePost("/api/interviews/sessions/41/complete", () => {
      state.session = structuredClone(COMPLETED);
      return HttpResponse.json(COMPLETED);
    });
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Finish session \(3 unanswered\)/ }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("3 questions are unanswered and will count as 0 in the overall score.");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(completes).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /Finish session/ }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Finish session" }));
    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(completes).toHaveLength(1);
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Needs work")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    expect(screen.getByText(/Unanswered questions count as 0/)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Strengths" })).getByText(/overfitting/)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Scores by category" })).getByText("Technical: 72.5")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Related skill gaps" })).getByText("Machine Learning · In progress")).toBeInTheDocument();
    expect(screen.queryByLabelText("Your answer")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Practise again" })).toHaveAttribute("href", "/interview-prep?internship=99");
  });
});

// ================================================================================================
describe("Reviewing sessions", () => {
  it("reviews an evaluated answer and every attempt of a completed session", async () => {
    backend({ session: COMPLETED });
    server.use(http.get("/api/interviews/sessions/41/questions/1/answers", () => HttpResponse.json([ANSWER])));
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    const evaluation = await screen.findByRole("region", { name: "Evaluation" });
    expect(within(evaluation).getByText("72.5")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show your answer" }));
    const attempts = await screen.findByRole("list", { name: "Your attempts" });
    expect(within(attempts).getByText(ANSWER.answer_text)).toBeInTheDocument();
    expect(within(attempts).getByText("72.5/100 · Good")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Question 2,/ }));
    expect(screen.getByText("Not answered before the session was closed.")).toBeInTheDocument();
  });

  it("shows a not-found state for a missing or another student's session", async () => {
    backend();
    server.use(http.get("/api/interviews/sessions/77", () => HttpResponse.json({ detail: "Interview session not found" }, { status: 404 })));
    renderAt("/interview-prep/sessions/77");
    expect(await screen.findByText("Session not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All sessions" })).toHaveAttribute("href", "/interview-prep");
  });

  it("retries after a failed load", async () => {
    backend();
    let calls = 0;
    server.use(http.get("/api/interviews/sessions/41", () => {
      calls += 1;
      return calls === 1 ? HttpResponse.json({ detail: "Forbidden" }, { status: 403 }) : HttpResponse.json(SESSION);
    }));
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: SESSION.title })).toBeInTheDocument();
  });

  it("deletes a session after confirmation", async () => {
    backend();
    const deleted = [];
    server.use(http.delete("/api/interviews/sessions/41", () => {
      deleted.push(41);
      return new HttpResponse(null, { status: 204 });
    }));
    renderAt("/interview-prep/sessions/41");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete session" }));
    await waitFor(() => expect(location()).toBe("/interview-prep"));
    expect(deleted).toEqual([41]);
  });

  it("sends the student to sign in when the session has expired", async () => {
    window.sessionStorage.setItem("acc.refresh_token", "x".repeat(40));
    const expired = () => HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 });
    server.use(
      http.get("/api/resumes/", expired),
      http.get("/api/interviews/sessions", expired),
      http.get("/api/interviews/question-bank/version", expired),
      http.get("/api/documents/llm-status", expired),
      http.post("/api/auth/refresh", () => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 })),
    );
    renderAt("/interview-prep");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(location()).toBe("/login?next=%2Finterview-prep"));
  });
});

// ================================================================================================
describe("Interview preparation integration", () => {
  it("shows the latest session on the dashboard with links to start and to the history", async () => {
    backend({ sessions: [LIST_ITEM(COMPLETED)] });
    server.use(http.get("/api/interviews/progress", () => HttpResponse.json({
      sessions_total: 1, sessions_completed: 1, questions_answered: 1, answers_total: 1, average_score: 72.5,
      by_category: { technical: 72.5 }, by_skill: {}, retry_improvement: { questions_retried: 0, average_change: null }, trend: [],
    })));
    renderAt("/");
    const card = (await screen.findByRole("heading", { name: "Interview preparation" })).closest("section");
    const latest = await within(card).findByRole("link", { name: SESSION.title });
    expect(latest).toHaveAttribute("href", "/interview-prep/sessions/41");
    expect(within(card).getByText("Completed")).toBeInTheDocument();
    expect(within(card).getByText("Score 24.2/100")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Start a new session" })).toHaveAttribute("href", "/interview-prep");
    expect(within(card).getByRole("link", { name: /All sessions/ })).toHaveAttribute("href", "/interview-prep");
  });

  it("links from the internship page and redirects the old /interviews address", async () => {
    backend();
    server.use(
      http.get("/api/applications/bookmarks/99", () => HttpResponse.json({ saved: false, bookmark: null })),
    );
    renderAt("/internships/99");
    expect(await screen.findByRole("link", { name: "Practise interview questions" })).toHaveAttribute("href", "/interview-prep?internship=99");
  });

  it("redirects /interviews to the interview preparation page", async () => {
    backend();
    renderAt("/interviews");
    await waitFor(() => expect(location()).toBe("/interview-prep"));
    expect(await screen.findByRole("heading", { name: "Interview preparation" })).toBeInTheDocument();
  });
});

describe("Interview helpers", () => {
  it("validates forms and answers against the backend's limits", () => {
    expect(validateSessionForm({ mix: { technical: "3", project: "2", behavioral: "2", internship: "1" }, mode: "practice", timeLimit: "" })).toEqual({});
    expect(validateSessionForm({ mix: { technical: "10", project: "5", behavioral: "1", internship: "0" }, mode: "practice" })).toEqual({
      mix: "Choose 1–15 questions in total (currently 16).",
    });
    expect(validateSessionForm({ mix: { technical: "x", project: "6", behavioral: "0", internship: "0" }, mode: "mock", timeLimit: "901" })).toEqual({
      technical: "Enter a whole number from 0 to 10.", project: "Enter a whole number from 0 to 5.", timeLimit: "Enter 30–900 seconds, or leave it empty for no limit.",
    });
    expect(validateAnswer(" ")).toBe("Write an answer before submitting.");
    expect(validateAnswer("x".repeat(5001))).toBe("Keep your answer under 5,000 characters.");
    expect(validateAnswer("Fine.")).toBeNull();
    expect(categoryLabel("behavioral")).toBe("Behavioural");
    expect(sessionStatus("in_progress").label).toBe("In progress");
    expect([scoreTone(80), scoreTone(50), scoreTone(10), scoreTone(null)]).toEqual(["success", "warning", "danger", "neutral"]);
  });
});
