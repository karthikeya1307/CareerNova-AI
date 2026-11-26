// Skill-gap endpoints (backend/routes/skill_gaps.py). Every query is filtered by the signed-in
// user; another user's resume or recommendation answers 404.
import { api } from "./client";

// GapStatus literal in backend/schemas/skill_gap_schema.py.
export const GAP_STATUSES = ["pending", "in_progress", "completed", "dismissed"];
export const GENERATE_TOP_K = { min: 1, max: 20, default: 5 };

// GET /skill-gaps/resumes/{rid}/internships/{iid} -> InternshipGapResponse (read-only analysis):
// { internship, summary{required_/preferred_ total|matched|partial|missing}, matched, partial, missing,
//   learning_order, learning_plans }. 404 if the internship is unavailable.
export async function getInternshipGap(resumeId, internshipId) {
  const { data } = await api.get(`/skill-gaps/resumes/${resumeId}/internships/${internshipId}`);
  return data;
}

// GET /skill-gaps?resume_id&status&current_only -> RecommendationItem[] ordered by priority (desc).
export async function listRecommendations(resumeId, { status, currentOnly = true } = {}) {
  const params = { resume_id: resumeId };
  if (status) params.status = status;
  if (!currentOnly) params.current_only = false;
  const { data } = await api.get("/skill-gaps", { params });
  return data;
}

// POST /skill-gaps/resumes/{rid} with { top_k } (latest match run) or { internship_ids } -> GenerateResponse.
// Replaces the *current* recommendation set for the resume; progress on returning skills is kept.
// 409: no matching run yet / none of its internships still available; 422: resume has no skills.
export async function generateRecommendations(resumeId, body) {
  const { data } = await api.post(`/skill-gaps/resumes/${resumeId}`, body);
  return data;
}

// PATCH /skill-gaps/{id} { status } -> the persisted RecommendationItem.
export async function updateRecommendationStatus(recommendationId, status) {
  const { data } = await api.patch(`/skill-gaps/${recommendationId}`, { status });
  return data;
}

// P3 skill progress: GET /skill-gaps/progress -> {statuses, labels, skills: {Name: {status, updated_at}}}
export const PROGRESS_LABELS = { not_started: "Not Started", learning: "Learning", practiced: "Practiced", completed: "Completed" };
export async function getSkillProgress() {
  const { data } = await api.get("/skill-gaps/progress");
  return data;
}

// PUT /skill-gaps/progress {skill, status} -> {skill, status, status_label, updated_at}. 404 for unknown skills.
export async function setSkillProgress(skill, status) {
  const { data } = await api.put("/skill-gaps/progress", { skill, status });
  return data;
}

// GET /skill-gaps/resumes/{rid}/internships/{iid}/roadmap -> ordered steps with plans, questions, project, status.
export async function getJobRoadmap(resumeId, internshipId) {
  const { data } = await api.get(`/skill-gaps/resumes/${resumeId}/internships/${internshipId}/roadmap`);
  return data;
}

// GET /skill-gaps/role-analysis?role&resume_id -> skills grouped with evidence (demonstrated / listed / not found),
// the target role's requirements and prioritised gaps. Without a role: a labelled general analysis (no gaps).
export async function getRoleAnalysis(role, resumeId) {
  const params = {};
  if (role) params.role = role;
  if (resumeId) params.resume_id = resumeId;
  const { data } = await api.get("/skill-gaps/role-analysis", { params });
  return data;
}
