// Matching endpoints (backend/routes/matches.py). All resolve the resume through the signed-in
// user's ownership check; another user's resume or run answers 404.
import { api } from "./client";
import { normalizeError } from "./errors";

export const MATCH_MAX_K = 50; // backend: k 1..50

// GET /matches/resumes/{id} -> latest MatchRunResponse, or null when matching has not run yet (404).
export async function getLatestMatches(resumeId) {
  try {
    const { data } = await api.get(`/matches/resumes/${resumeId}`);
    return data;
  } catch (error) {
    if (normalizeError(error).status === 404) return null;
    throw error;
  }
}

// POST /matches/resumes/{id}?k&work_mode&location -> new MatchRunResponse (201).
// 422 when the resume lacks enough data to match.
export async function runMatching(resumeId, { k, work_mode, location } = {}) {
  const params = Object.fromEntries(Object.entries({ k, work_mode, location }).filter(([, v]) => v !== undefined && v !== null && v !== ""));
  const { data } = await api.post(`/matches/resumes/${resumeId}`, null, { params });
  return data;
}

// GET /matches/resumes/{id}/history -> MatchRunSummary[] (newest first).
export async function getMatchHistory(resumeId) {
  const { data } = await api.get(`/matches/resumes/${resumeId}/history`);
  return data;
}

// GET /matches/runs/{run_id} -> MatchRunResponse (owner only).
export async function getMatchRun(runId) {
  const { data } = await api.get(`/matches/runs/${runId}`);
  return data;
}

// GET /matches/resumes/{rid}/internships/{iid} -> MatchItem for one internship (rank null).
// 404 when the internship is unavailable (inactive / past deadline); 422 when the resume lacks data.
export async function scoreInternship(resumeId, internshipId) {
  const { data } = await api.get(`/matches/resumes/${resumeId}/internships/${internshipId}`);
  return data;
}

// GET /matches/explore -> {mode, resume_id, total, skip, limit, category_counts, items:[{internship, score,
// label, insights}]}. Every open opportunity (not only the best matches); with resumeId each job gets
// insights (skill match, eligibility, application readiness, category). Nothing is saved.
export async function exploreJobs({ resumeId, q, domain, location, workMode, category, skip = 0, limit = 20 } = {}) {
  const params = { skip, limit };
  if (resumeId) params.resume_id = resumeId;
  if (q && q.trim()) params.q = q.trim();
  if (domain) params.domain = domain;
  if (location && location.trim()) params.location = location.trim();
  if (workMode) params.work_mode = workMode;
  if (category) params.category = category;
  const { data } = await api.get("/matches/explore", { params });
  return data;
}
