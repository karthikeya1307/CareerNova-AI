// Bookmark and application-tracking endpoints used by internship discovery
// (backend/routes/applications.py). Everything is scoped to the signed-in user.
import { api } from "./client";

// GET /applications/bookmarks/{iid} -> { saved, bookmark | null }
export async function getBookmarkStatus(internshipId) {
  const { data } = await api.get(`/applications/bookmarks/${internshipId}`);
  return data;
}

// POST /applications/bookmarks/{iid} -> BookmarkOut (201 new, 200 already saved).
export async function saveBookmark(internshipId) {
  const { data } = await api.post(`/applications/bookmarks/${internshipId}`);
  return data;
}

// DELETE /applications/bookmarks/{iid} -> 204
export async function removeBookmark(internshipId) {
  await api.delete(`/applications/bookmarks/${internshipId}`);
}

// POST /applications { internship_id, status } -> ApplicationOut (201).
// Company, title, URL etc. are copied from the internship by the backend; with status APPLIED the
// backend sets applied_at to now. 409 detail { message, application_id } when already tracked.
export async function trackInternshipApplication(internshipId, status = "APPLIED") {
  const { data } = await api.post("/applications", { internship_id: internshipId, status });
  return data;
}

// ------------------------------------------------------------------------------------------------
// Application tracking (F8). Mirrors backend/schemas/application_schema.py and
// services/application_service.py. Every request is scoped to the signed-in student; another
// student's application answers 404 "Application not found".

export const STATUSES = ["SAVED", "APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"];
// application_service.TRANSITIONS: the backend rejects anything else with 409. A "correction" can
// only undo the last status change (back to the status it came from).
export const TRANSITIONS = {
  SAVED: ["APPLIED", "WITHDRAWN"],
  APPLIED: ["SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"],
  SHORTLISTED: ["INTERVIEW_SCHEDULED", "SELECTED", "REJECTED", "WITHDRAWN"],
  INTERVIEW_SCHEDULED: ["SHORTLISTED", "SELECTED", "REJECTED", "WITHDRAWN"],
  SELECTED: ["WITHDRAWN"],
  REJECTED: [],
  WITHDRAWN: [],
};
// Interview rounds can be added only in these statuses (INTERVIEW_ALLOWED_STATUSES).
export const INTERVIEW_ALLOWED = ["APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED"];
export const INTERVIEW_TYPES = ["technical", "hr", "behavioral", "managerial", "case_study", "assignment", "group", "other"];
export const INTERVIEW_MODES = ["online", "offline", "phone"];
export const INTERVIEW_OUTCOMES = ["pending", "passed", "failed", "cancelled", "no_show"];
export const WORK_MODES = ["Onsite", "Hybrid", "Remote"];
export const SORT_FIELDS = ["updated_at", "created_at", "applied_at", "company_name", "title", "status"];
export const LIMITS = { notes: 5000, name: 200, url: 1000, reference: 100, contact: 120, reminderTitle: 150, reminderDescription: 2000, query: 100 };

// GET /applications/dashboard -> DashboardOut
export async function getApplicationDashboard() {
  const { data } = await api.get("/applications/dashboard");
  return data;
}

// GET /applications?status=&q=&sort=&order=&skip=&limit= -> { total, skip, limit, items }
export async function listApplications({ statuses = [], q, sort = "updated_at", order = "desc", skip = 0, limit = 20 } = {}) {
  const params = new URLSearchParams();
  for (const s of statuses) params.append("status", s);
  if (q) params.set("q", q);
  params.set("sort", sort);
  params.set("order", order);
  params.set("skip", String(skip));
  params.set("limit", String(limit));
  const { data } = await api.get("/applications", { params });
  return data;
}

// POST /applications -> ApplicationOut (201). Internal: { internship_id, status }. External: company/title...
export async function createApplication(body) {
  const { data } = await api.post("/applications", body);
  return data;
}

export async function getApplication(applicationId) {
  const { data } = await api.get(`/applications/${applicationId}`);
  return data;
}

// PATCH /applications/{id} (details only; status uses updateStatus)
export async function updateApplication(applicationId, body) {
  const { data } = await api.patch(`/applications/${applicationId}`, body);
  return data;
}

// PATCH /applications/{id}/status { status, correction, expected_status } -> StatusResult
export async function updateStatus(applicationId, { status, correction = false, expectedStatus }) {
  const { data } = await api.patch(`/applications/${applicationId}/status`, { status, correction, expected_status: expectedStatus });
  return data;
}

// GET /applications/{id}/history -> { status_history, activity }
export async function getHistory(applicationId) {
  const { data } = await api.get(`/applications/${applicationId}/history`);
  return data;
}

// DELETE /applications/{id}?confirm=true -> 204 (moves it to the trash)
export async function moveToTrash(applicationId) {
  await api.delete(`/applications/${applicationId}`, { params: { confirm: true } });
}

// GET /applications/trash -> { total, skip, limit, items }
export async function listTrash({ skip = 0, limit = 20 } = {}) {
  const { data } = await api.get("/applications/trash", { params: { skip, limit } });
  return data;
}

export async function restoreApplication(applicationId) {
  const { data } = await api.post(`/applications/${applicationId}/restore`);
  return data;
}

// DELETE /applications/{id}/permanent?confirm=true -> 204 (only from the trash)
export async function deletePermanently(applicationId) {
  await api.delete(`/applications/${applicationId}/permanent`, { params: { confirm: true } });
}

// Interview rounds (real company interviews; not the F7 practice sessions).
export async function listInterviewRounds(applicationId) {
  const { data } = await api.get(`/applications/${applicationId}/interviews`);
  return data;
}
export async function addInterviewRound(applicationId, body) {
  const { data } = await api.post(`/applications/${applicationId}/interviews`, body);
  return data;
}
export async function updateInterviewRound(interviewId, body) {
  const { data } = await api.patch(`/applications/interviews/${interviewId}`, body);
  return data;
}
// -> { deleted: true, status_change }
export async function deleteInterviewRound(interviewId) {
  const { data } = await api.delete(`/applications/interviews/${interviewId}`);
  return data;
}

// Reminders: stored only. The backend never sends them (ReminderOut.delivery is always "not_sent").
export async function listReminders({ applicationId, status = "pending", skip = 0, limit = 50 } = {}) {
  const params = { status, skip, limit };
  if (applicationId) params.application_id = applicationId;
  const { data } = await api.get("/applications/reminders", { params });
  return data;
}
export async function addReminder(applicationId, body) {
  const { data } = await api.post(`/applications/${applicationId}/reminders`, body);
  return data;
}
export async function updateReminder(reminderId, body) {
  const { data } = await api.patch(`/applications/reminders/${reminderId}`, body);
  return data;
}
export async function deleteReminder(reminderId) {
  await api.delete(`/applications/reminders/${reminderId}`);
}

// GET /applications/bookmarks?skip=&limit= -> { total, skip, limit, items: BookmarkOut[] }
export async function listBookmarks({ skip = 0, limit = 20 } = {}) {
  const { data } = await api.get("/applications/bookmarks", { params: { skip, limit } });
  return data;
}
