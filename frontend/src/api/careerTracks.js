// Career tracks (backend/routes/career_tracks.py): curated content for each role.
import { api } from "./client";

export async function listCareerTracks() {
  const { data } = await api.get("/career-tracks");
  return data;
}

// GET /career-tracks/{slug}?resume_id= -> skills (with resume coverage and progress), roadmap, exercises,
// projects, resume advice, interview questions (from the question bank). 404 for unknown tracks.
export async function getCareerTrack(slug, resumeId) {
  const { data } = await api.get(`/career-tracks/${encodeURIComponent(slug)}`, { params: resumeId ? { resume_id: resumeId } : {} });
  return data;
}

// GET /career-tracks/{slug}/jobs -> {track, items: [{internship, track_skill_overlap}]}
export async function getCareerTrackJobs(slug, limit = 10) {
  const { data } = await api.get(`/career-tracks/${encodeURIComponent(slug)}/jobs`, { params: { limit } });
  return data;
}
