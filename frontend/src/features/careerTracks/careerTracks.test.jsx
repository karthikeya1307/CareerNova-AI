import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../../App";
import { setAccessToken } from "../../api/client";
import { server } from "../../test/server";
import JobRoadmap from "../skillGaps/components/JobRoadmap";

// Fictional fixtures shaped like backend/services/career_tracks.py and skill_progress.py.
const student = { user_id: 7, first_name: "Asha", last_name: "Rao", role: "student", email: "asha@example.com", is_verified: true };
const RESUME = { resume_id: 11, filename: "cv.pdf", file_type: "pdf", status: "completed", uploaded_at: "2026-11-10T00:00:00Z" };
const SUMMARY = [
  { slug: "data-analyst", title: "Data Analyst", summary: "Turns raw data into reports.", core_skills: ["SQL", "Excel"], domains: ["Data Science"] },
  { slug: "devops-engineer", title: "DevOps Engineer", summary: "Automates delivery.", core_skills: ["Linux", "Docker"], domains: ["DevOps/Cloud"] },
];
const skill = (name, extra = {}) => ({ skill: name, tier: "core", on_resume: false, status: "not_started", status_label: "Not Started",
  level: "beginner", estimated_hours: 20, topics: ["Basics"], curated_plan: true, resource: null, ...extra });
const DETAIL = {
  ...SUMMARY[0], advanced_skills: ["Python"],
  skills: [skill("SQL", { on_resume: true, resource: { title: "PostgreSQL tutorial", url: "https://www.postgresql.org/docs/current/tutorial.html" } }), skill("Excel", { status: "learning", status_label: "Learning" })],
  roadmap: [{ stage: "Foundations", skills: ["Excel", "SQL"], goal: "Clean data and answer questions." }],
  exercises: ["Build a pivot-table report."], projects: ["A sales dashboard."], resume_advice: ["Name the tools you used."],
  interview_questions: [{ skill: "SQL", difficulty: "easy", question: "What is a JOIN?" }],
  coverage: { on_resume: 1, total: 2, percent: 50 }, resources_note: "Links point to official documentation.",
};

function renderAt(path) {
  setAccessToken("access-token");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App authProps={{ initialUser: student, restoreSession: false }} />
    </MemoryRouter>,
  );
}

describe("Career tracks", () => {
  it("lists the tracks and links to each one", async () => {
    server.use(http.get("/api/career-tracks", () => HttpResponse.json(SUMMARY)));
    renderAt("/career-tracks");
    const list = await screen.findByRole("list", { name: "Career tracks" });
    expect(within(list).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["/career-tracks/data-analyst", "/career-tracks/devops-engineer"]);
    expect(screen.getByRole("link", { name: "Career tracks" })).toBeInTheDocument(); // sidebar entry
  });

  it("shows a track with coverage, progress, roadmap, practice content and relevant jobs", async () => {
    const queries = [];
    const saved = [];
    server.use(
      http.get("/api/resumes/", () => HttpResponse.json([RESUME])),
      http.get("/api/career-tracks/data-analyst", ({ request }) => {
        queries.push(Object.fromEntries(new URL(request.url).searchParams));
        return HttpResponse.json(DETAIL);
      }),
      http.get("/api/career-tracks/data-analyst/jobs", () =>
        HttpResponse.json({ track: "data-analyst", items: [{ internship: { internship_id: 4, title: "BI Intern", company: "Ledger", source_label: "Sample listing (curated dataset)" }, track_skill_overlap: 3 }] }),
      ),
      http.put("/api/skill-gaps/progress", async ({ request }) => {
        const body = await request.json();
        saved.push(body);
        return HttpResponse.json({ skill: body.skill, status: body.status, status_label: "Practiced", updated_at: "2026-11-24T10:00:00Z" });
      }),
    );
    renderAt("/career-tracks/data-analyst");
    expect(await screen.findByRole("heading", { level: 1, name: "Data Analyst" })).toBeInTheDocument();
    await waitFor(() => expect(queries.at(-1)).toEqual({ resume_id: "11" }));
    expect(screen.getByText(/Your resume shows/)).toHaveTextContent("1 of 2 track skills (50%)");
    const skills = screen.getByRole("list", { name: "Track skills" });
    expect(within(skills).getByText("on your resume")).toBeInTheDocument();
    expect(within(skills).getByRole("link", { name: "PostgreSQL tutorial" })).toHaveAttribute("href", "https://www.postgresql.org/docs/current/tutorial.html");
    expect(within(skills).getByLabelText("Progress for Excel")).toHaveValue("learning");
    await userEvent.selectOptions(within(skills).getByLabelText("Progress for SQL"), "practiced");
    await waitFor(() => expect(saved).toEqual([{ skill: "SQL", status: "practiced" }]));
    expect(screen.getByRole("region", { name: "Learning roadmap" })).toHaveTextContent("Foundations");
    expect(screen.getByRole("region", { name: "Interview questions" })).toHaveTextContent("What is a JOIN?");
    expect(screen.getByRole("region", { name: "Practice exercises" })).toHaveTextContent("pivot-table");
    const jobs = screen.getByRole("region", { name: "Relevant opportunities" });
    expect(await within(jobs).findByRole("link", { name: "BI Intern" })).toHaveAttribute("href", "/internships/4");
    expect(within(jobs).getByText("Sample listing (curated dataset)")).toBeInTheDocument();
  });

  it("says when a track does not exist", async () => {
    server.use(
      http.get("/api/career-tracks/astronaut", () => HttpResponse.json({ detail: "Career track not found" }, { status: 404 })),
      http.get("/api/career-tracks/astronaut/jobs", () => HttpResponse.json({ detail: "Career track not found" }, { status: 404 })),
    );
    renderAt("/career-tracks/astronaut");
    expect(await screen.findByText("Career track not found")).toBeInTheDocument();
  });
});

const ROADMAP = {
  resume_id: 11, internship_id: 9, title: "Platform Intern", company: "Nimbus", skill_match: 40, have: ["Python"],
  steps: [
    { step: 1, skill: "Docker", importance: "required", gap: "missing", why: "Platform Intern at Nimbus lists Docker as a required skill.",
      evidence: ["Not on your resume yet."], learning: { level: "beginner", estimated_hours: 25, prerequisites: [], topics: ["Images and containers"], curated: true },
      resource: { title: "Docker: Get started", url: "https://docs.docker.com/get-started/" }, interview_questions: ["What is a container?"],
      project: "Build a small project that uses Docker.", status: "not_started", status_label: "Not Started" },
    { step: 2, skill: "Kubernetes", importance: "preferred", gap: "partial", why: "Platform Intern at Nimbus lists Kubernetes as a preferred skill.",
      evidence: ["You have related skills: Docker Compose."], learning: { level: "intermediate", estimated_hours: 40, prerequisites: ["Docker"], topics: ["Pods"], curated: false },
      resource: null, interview_questions: [], project: "Build a small project that uses Kubernetes.", status: "completed", status_label: "Completed" },
  ],
  progress: { total: 2, completed: 1, by_status: { not_started: 1, learning: 0, practiced: 0, completed: 1 }, percent: 50 },
};

describe("Per-job learning roadmap", () => {
  it("lists steps in order, shows the plan and saves progress", async () => {
    const saved = [];
    server.use(
      http.get("/api/skill-gaps/resumes/11/internships/9/roadmap", () => HttpResponse.json(ROADMAP)),
      http.put("/api/skill-gaps/progress", async ({ request }) => {
        const body = await request.json();
        saved.push(body);
        return HttpResponse.json({ skill: body.skill, status: body.status, status_label: "Completed", updated_at: "2026-11-24T10:00:00Z" });
      }),
    );
    setAccessToken("access-token");
    render(<JobRoadmap resumeId={11} internshipId={9} />);
    const list = await screen.findByRole("list", { name: "Learning roadmap" });
    expect(within(list).getAllByRole("listitem").filter((li) => li.parentElement === list).map((li) => li.textContent.slice(0, 7))).toEqual(["1Docker", "2Kubern"]);
    expect(screen.getByLabelText("Roadmap progress")).toHaveTextContent("1 of 2 skills completed (50%)");
    await userEvent.click(screen.getByRole("button", { name: /Show learning plan for Docker/ }));
    expect(screen.getByRole("link", { name: "Docker: Get started" })).toHaveAttribute("href", "https://docs.docker.com/get-started/");
    expect(screen.getByText("What is a container?")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Progress for Docker"), "completed");
    await waitFor(() => expect(saved).toEqual([{ skill: "Docker", status: "completed" }]));
    expect(await screen.findByText("2 of 2 skills completed (100%)")).toBeInTheDocument();
  });

  it("restores the previous status and explains when saving fails", async () => {
    server.use(
      http.get("/api/skill-gaps/resumes/11/internships/9/roadmap", () => HttpResponse.json(ROADMAP)),
      http.put("/api/skill-gaps/progress", () => HttpResponse.json({ detail: "'Docker' is not in the skill catalogue." }, { status: 404 })),
    );
    setAccessToken("access-token");
    render(<JobRoadmap resumeId={11} internshipId={9} />);
    const select = await screen.findByLabelText("Progress for Docker");
    await userEvent.selectOptions(select, "learning");
    expect(await screen.findByRole("alert")).toHaveTextContent("not in the skill catalogue");
    expect(select).toHaveValue("not_started");
  });
});
