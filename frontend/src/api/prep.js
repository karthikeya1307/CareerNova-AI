// Interview preparation agent (backend/routes/prep.py): resume-based roles, questions, guidance, roadmap.
// 409 { code: "resume_required" } when the student has no parsed resume yet.
import { api } from "./client";

export async function getRecommendedRoles(limit = 5) {
  const { data } = await api.get("/prep/roles", { params: { limit } });
  return data;
}
