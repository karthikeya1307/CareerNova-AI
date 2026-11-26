import { http, HttpResponse } from "msw";

// Default API mocks for tests only (never bundled into the app). Tests override them with
// server.use(...). The dashboard defaults describe a brand-new student with no data yet, matching
// the backend's real empty responses.
export const EMPTY_APPLICATION_SUMMARY = {
  generated_at: "2026-11-16T10:00:00Z",
  saved_internships: 0,
  total_applications: 0,
  by_status: {},
  submitted_applications: 0,
  selected: 0,
  rejected: 0,
  interviews_scheduled: 0,
  upcoming_interviews: 0,
  next_interviews: [],
  pending_reminders: 0,
  overdue_reminders: 0,
  completed_reminders: 0,
  success_rate: null,
  decision_rate: null,
  interview_rate: null,
  formulas: {},
  recent_activity: [],
};

export const EMPTY_INTERVIEW_PROGRESS = {
  sessions_total: 0,
  sessions_completed: 0,
  questions_answered: 0,
  answers_total: 0,
  average_score: null,
  by_category: {},
  by_skill: {},
  retry_improvement: { questions_retried: 0, average_change: null },
  trend: [],
};

// GET /resumes/{id}/readiness (backend readiness-v1) for a fairly complete resume.
export const SAMPLE_READINESS = {
  resume_id: 12, version: 2, filename: "Asha_Rao_CV.pdf", version_label: null, is_preferred: false,
  basis: "resume_content", same_content_as: [],
  corrected: false, algorithm: "readiness-v1", score: 78, label: "Good",
  categories: [
    { key: "contact", label: "Contact and profile", score: 8, max: 10, points: [{ points: 8, reason: "Name, email and phone found", earned: true }, { points: 2, reason: "No LinkedIn or GitHub link", earned: false }], recommendations: ["Add a LinkedIn or GitHub link so recruiters can see more of your work."] },
    { key: "structure", label: "Structure and completeness", score: 15, max: 15, points: [{ points: 15, reason: "All key sections present", earned: true }], recommendations: [] },
    { key: "skills", label: "Skills and evidence", score: 12, max: 20, points: [{ points: 6, reason: "6 skill(s) listed", earned: true }], recommendations: ["List at least 8 relevant technical skills."] },
    { key: "experience", label: "Experience and internships", score: 13, max: 15, points: [], recommendations: [] },
    { key: "projects", label: "Projects", score: 11, max: 15, points: [], recommendations: [] },
    { key: "education", label: "Education", score: 10, max: 10, points: [], recommendations: [] },
    { key: "credentials", label: "Certifications and achievements", score: 0, max: 5, points: [], recommendations: ["Add relevant certifications or completed courses."] },
    { key: "formatting", label: "Formatting and readability", score: 9, max: 10, points: [], recommendations: [] },
  ],
  strengths: ["Structure and completeness: 15/15", "Education: 10/10"],
  weaknesses: ["Certifications and achievements: 0/5"],
  recommendations: ["List at least 8 relevant technical skills.", "Add relevant certifications or completed courses."],
  parsing: { overall_confidence: 0.92, missing_core_fields: [], missing_recommended_sections: ["Certifications"], warnings: [], total_experience_months: 6 },
  disclaimer: "General resume readiness based on completeness and evidence in your resume. It is not a prediction of any specific employer's applicant-tracking system and does not guarantee an interview.",
};

export const SAMPLE_TRACKS = [
  { slug: "data-analyst", title: "Data Analyst", summary: "Turns data into decisions.", core_skills: ["SQL", "Excel"], domains: [] },
  { slug: "java-developer", title: "Java Developer", summary: "Builds Java services.", core_skills: ["Java", "Spring Boot"], domains: [] },
];

export const handlers = [
  http.get("/api/resumes/:id/readiness", () => HttpResponse.json(SAMPLE_READINESS)),
  http.get("/api/health", () =>
    HttpResponse.json({ status: "Healthy", database: "test-db", message: "Database connection successful" }),
  ),
  http.get("/api/resumes/", () => HttpResponse.json([])),
  // A new student has no profile yet: the backend answers 404 until POST /profiles/.
  http.get("/api/profiles/me", () => HttpResponse.json({ detail: "User profile not found" }, { status: 404 })),
  http.get("/api/interviews/progress", () => HttpResponse.json(EMPTY_INTERVIEW_PROGRESS)),
  http.get("/api/interviews/sessions", () => HttpResponse.json([])),
  // Admin pages (F10): an index that has never been built.
  http.get("/api/admin/index/status", () =>
    HttpResponse.json({ built: false, built_at: null, model_name: null, model_revision: null, dimension: null, indexed_vectors: 0,
      configured_model: "test-model", model_matches_configuration: false, active_internships: 0, document_status_counts: {}, stale: true }),
  ),
  http.get("/api/applications/dashboard", () => HttpResponse.json(EMPTY_APPLICATION_SUMMARY)),
  http.get("/api/applications", () => HttpResponse.json({ total: 0, skip: 0, limit: 5, items: [] })),
  http.get("/api/assistant/conversations", () => HttpResponse.json({ total: 0, skip: 0, limit: 3, items: [] })),
  // Assistant page (HR assignment): role picker and the student's study documents.
  http.get("/api/career-tracks", () => HttpResponse.json(SAMPLE_TRACKS)),
  http.get("/api/study-documents", () => HttpResponse.json([])),
  // Profile picture (HR feedback): none uploaded -> initials.
  http.get("/api/profiles/me/avatar", () => HttpResponse.json({ detail: "No profile picture" }, { status: 404 })),
];
