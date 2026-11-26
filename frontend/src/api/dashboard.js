// Endpoints used by the student dashboard. All are authenticated and the backend scopes every
// query to the signed-in user (current_user), so no user id is ever sent from the browser.
import { api } from "./client";

// Resume and matching endpoints live in api/resumes.js and api/matches.js (shared with their pages).
export { RESUME_EXTENSIONS, RESUME_MAX_BYTES, getResumeSkills, listResumes, uploadResume } from "./resumes";
export { getLatestMatches, runMatching } from "./matches";

// GET /documents/resumes/{rid}/internships/{iid}/ats-report -> keyword coverage + resume checks
// for ONE internship. The backend does not compute an overall ATS score.
export async function getAtsReport(resumeId, internshipId) {
  const { data } = await api.get(`/documents/resumes/${resumeId}/internships/${internshipId}/ats-report`);
  return data;
}

// Skill-gap endpoints live in api/skillGaps.js (shared with the Skill gaps pages).
export { getInternshipGap as getSkillGap, listRecommendations as listSkillGapRecommendations } from "./skillGaps";

// GET /interviews/progress -> ProgressOut (average_score is 0-100, null before any answer).
export async function getInterviewProgress() {
  const { data } = await api.get("/interviews/progress");
  return data;
}

// GET /interviews/sessions -> SessionListItem[] (newest first). Lives in api/interviews.js.
export { listSessions as listInterviewSessions } from "./interviews";

// GET /applications/dashboard -> DashboardOut (counts by status, upcoming interviews, rates).
export async function getApplicationSummary() {
  const { data } = await api.get("/applications/dashboard");
  return data;
}

// GET /applications?sort=updated_at&order=desc&limit= -> { total, items: ApplicationOut[] }
export async function listRecentApplications(limit = 5) {
  const { data } = await api.get("/applications", { params: { sort: "updated_at", order: "desc", limit } });
  return data;
}

// GET /assistant/conversations?limit= -> { total, items: ConversationOut[] }
export async function listConversations(limit = 3) {
  const { data } = await api.get("/assistant/conversations", { params: { limit } });
  return data;
}
