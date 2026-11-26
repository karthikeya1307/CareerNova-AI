// Administrator endpoints (backend/routes/admin.py and the admin-only routes in routes/internships.py).
// The backend checks the role on every call (require_admin -> 403 for students; role changes and
// managing administrators need the super admin). Not provided by the backend, so not offered here:
// sending invitations (Phase 2), skill management and a statistics endpoint.
import { api } from "./client";
import { listInternships } from "./internships";

export const ROLES = ["student", "admin", "super_admin"]; // backend/utils/roles.VALID_ROLES
export const ASSIGNABLE_ROLES = ["student", "admin"]; // super_admin is only granted from the command line
export const USERS_MAX_LIMIT = 200; // GET /admin/users: limit 1..200
export const INTERNSHIP_LIMITS = {
  title: 200, company: 200, description: 5000, eligibility: 2000, location: 150, application_url: 1000, domain: 80, min_education: 200,
  skills: 30, skillName: 60,
};

// GET /admin/users?skip=&limit=&q=&role=&is_active= -> UserResponse[] ordered by user_id (no total).
// q searches name and email (case-insensitive, server side). UserResponse: {user_id, user_uuid,
// first_name, last_name, phone_number, email, role, is_verified, created_at, is_active, last_login_at}
export async function listUsers({ skip = 0, limit = 50, q, role, isActive } = {}) {
  const params = { skip, limit };
  if (q && q.trim()) params.q = q.trim();
  if (role) params.role = role;
  if (isActive === true || isActive === false) params.is_active = isActive;
  const { data } = await api.get("/admin/users", { params });
  return data;
}

// POST /admin/users {first_name, last_name, email, phone_number?, role} -> UserResponse (201).
// Creates a pending account (not verified, no usable password; activation by invitation in Phase 2).
// 409 when the email exists, 403 when an admin tries to create an admin.
export async function createUser(body) {
  const { data } = await api.post("/admin/users", body);
  return data;
}

// POST /admin/users/{id}/deactivate | reactivate -> UserResponse. Deactivation signs the user out
// everywhere; data is kept. 403 for the super admin and (for admins) other administrators.
export async function deactivateUser(userId) {
  const { data } = await api.post(`/admin/users/${userId}/deactivate`);
  return data;
}

export async function reactivateUser(userId) {
  const { data } = await api.post(`/admin/users/${userId}/reactivate`);
  return data;
}

// POST /admin/users/{id}/invitation -> AdminUserResponse (new single-use link emailed; the previous link
// stops working). 429 {detail:{code:"cooldown"|"daily_limit"}} with Retry-After; 409 for active or
// deactivated accounts. POST /admin/users/{id}/invitation/revoke -> AdminUserResponse.
export async function sendInvitation(userId) {
  const { data } = await api.post(`/admin/users/${userId}/invitation`);
  return data;
}

export async function revokeInvitation(userId) {
  const { data } = await api.post(`/admin/users/${userId}/invitation/revoke`);
  return data;
}

// GET /admin/email/status -> {mode, ok, problems, warnings, host, port, security, ...} (never secrets)
export async function getEmailStatus() {
  const { data } = await api.get("/admin/email/status");
  return data;
}

// GET /admin/audit-events?skip=&limit=&action=&target_user_id= -> {total, skip, limit, items}
export async function listAuditEvents({ skip = 0, limit = 50, action, targetUserId } = {}) {
  const params = { skip, limit };
  if (action) params.action = action;
  if (targetUserId) params.target_user_id = targetUserId;
  const { data } = await api.get("/admin/audit-events", { params });
  return data;
}

// Every user, page by page (the list has no total). `maxPages` bounds the work.
// Returns { items, complete } — complete is false if the cap was reached.
export async function listAllUsers({ maxPages = 10 } = {}) {
  const items = [];
  for (let page = 0; page < maxPages; page += 1) {
    const batch = await listUsers({ skip: page * USERS_MAX_LIMIT, limit: USERS_MAX_LIMIT });
    items.push(...batch);
    if (batch.length < USERS_MAX_LIMIT) return { items, complete: true };
  }
  return { items, complete: false };
}

// PATCH /admin/users/{id}/role { role } -> UserResponse. Super admin only (403 otherwise); never for
// the super admin account itself.
export async function updateUserRole(userId, role) {
  const { data } = await api.patch(`/admin/users/${userId}/role`, { role });
  return data;
}

// GET /admin/index/status -> IndexStatusResponse (read-only)
export async function getIndexStatus() {
  const { data } = await api.get("/admin/index/status");
  return data;
}

// POST /admin/index/rebuild -> IndexRebuildResponse {indexed, deactivated_documents, built_at, model_name, dimension}.
// Synchronous (no progress reporting). 409 when a rebuild is already running, 503 when embeddings fail.
export async function rebuildIndex() {
  const { data } = await api.post("/admin/index/rebuild");
  return data;
}

// GET /internships/?include_inactive=true (admins also see deactivated internships).
export async function adminListInternships({ q, domain, includeInactive = true, skip = 0, limit = 20 } = {}) {
  const { data } = await api.get("/internships/", {
    params: Object.fromEntries(Object.entries({ q, domain, include_inactive: includeInactive || undefined, skip, limit }).filter(([, v]) => v !== undefined && v !== "")),
  });
  return data;
}

// Totals only (limit=1): active, and active + deactivated.
export async function internshipTotals() {
  const [active, all] = await Promise.all([listInternships({ limit: 1 }), adminListInternships({ limit: 1 })]);
  return { active: active.total, all: all.total };
}

// POST /internships/ (InternshipCreate) -> InternshipResponse (201). Created as active, source "admin".
export async function createInternship(body) {
  const { data } = await api.post("/internships/", body);
  return data;
}

// PATCH /internships/{id} (InternshipUpdate, only the fields that changed) -> InternshipResponse.
export async function updateInternship(internshipId, body) {
  const { data } = await api.patch(`/internships/${internshipId}`, body);
  return data;
}

// POST /internships/{id}/verify -> InternshipResponse with last_verified_at = now (audited).
export async function verifyInternship(internshipId) {
  const { data } = await api.post(`/internships/${internshipId}/verify`);
  return data;
}

// DELETE /internships/{id} -> 204. Soft delete: sets is_active=false (reactivate with PATCH is_active).
export async function deactivateInternship(internshipId) {
  await api.delete(`/internships/${internshipId}`);
}
