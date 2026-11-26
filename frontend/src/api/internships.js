// Internship endpoints (backend/routes/internships.py). Students only ever see active internships;
// inactive or past-deadline ones answer 404.
import { api } from "./client";

export const WORK_MODES = ["Onsite", "Hybrid", "Remote"]; // backend WorkMode literal
export const LIST_MAX_LIMIT = 100; // backend: limit 1..100
export const SEARCH_MAX_K = 50; // backend: k 1..50
export const SEARCH_QUERY = { min: 2, max: 500 }; // backend: q 2..500
export const KEYWORD_MAX = 100; // backend: q max_length=100

function clean(params) {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && String(v).trim() !== ""));
}

// GET /internships/?q&domain&work_mode&location&skill&skip&limit -> { total, skip, limit, items }.
// q matches title/company/description; skill is an exact (case-insensitive) skill name. Fixed order by id.
export async function listInternships({ q, domain, work_mode, location, skill, skip = 0, limit = 20 } = {}) {
  const { data } = await api.get("/internships/", { params: clean({ q, domain, work_mode, location, skill, skip, limit }) });
  return data;
}

// Every internship matching the filters (pages of 100). Used only for client-side sorting, because
// the backend has no sort parameter. `maxPages` bounds the work if the catalogue grows.
export async function listAllInternships(filters = {}, { maxPages = 20 } = {}) {
  const items = [];
  let total = 0;
  for (let page = 0; page < maxPages; page += 1) {
    const data = await listInternships({ ...filters, skip: page * LIST_MAX_LIMIT, limit: LIST_MAX_LIMIT });
    total = data.total;
    items.push(...data.items);
    if (items.length >= total || data.items.length === 0) break;
  }
  return { total, items };
}

// GET /internships/filters -> { domains, work_modes, locations } (active internships only).
export async function getInternshipFilters() {
  const { data } = await api.get("/internships/filters");
  return data;
}

// GET /internships/{id} -> InternshipResponse.
export async function getInternship(internshipId) {
  const { data } = await api.get(`/internships/${internshipId}`);
  return data;
}

// GET /internships/search?q&k -> { query, index_built_at, results: [{ similarity, internship }] }.
// Semantic (embedding) search over the FAISS index; 503 when the index or model is unavailable.
export async function searchInternships(query, k = 10) {
  const { data } = await api.get("/internships/search", { params: { q: query, k } });
  return data;
}
