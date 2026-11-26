// Auth endpoints (backend: backend/routes/auth.py). Public calls skip the access token and the
// 401 refresh/retry: a 401 from login means "wrong credentials", not "session expired".
import { api } from "./client";

const PUBLIC = { skipAuth: true, skipAuthRefresh: true };

// POST /auth/login -> { access_token, refresh_token, token_type, expires_in, refresh_expires_in }
// 401 wrong email/password, 403 email not verified.
export async function login(email, password) {
  const { data } = await api.post("/auth/login", { email, password }, PUBLIC);
  return data;
}

// POST /auth/register -> 201 UserResponse. 409 email taken; 503 account created but the
// verification email could not be sent.
export async function register({ first_name, last_name, phone_number, email, password }) {
  const { data } = await api.post("/auth/register", { first_name, last_name, phone_number, email, password }, PUBLIC);
  return data;
}

// GET /auth/verify-email?token= -> { message }. 400 invalid / already used / expired.
export async function verifyEmail(token) {
  const { data } = await api.get("/auth/verify-email", { ...PUBLIC, params: { token } });
  return data;
}

// POST /auth/resend-verification -> generic { message } (never reveals whether the account exists).
export async function resendVerification(email) {
  const { data } = await api.post("/auth/resend-verification", { email }, PUBLIC);
  return data;
}

// POST /auth/forgot-password -> generic { message } (never reveals whether the account exists).
export async function forgotPassword(email) {
  const { data } = await api.post("/auth/forgot-password", { email }, PUBLIC);
  return data;
}

// POST /auth/reset-password -> { message }. 400 invalid / used / expired token. Revokes all sessions.
export async function resetPassword(token, newPassword) {
  const { data } = await api.post("/auth/reset-password", { token, new_password: newPassword }, PUBLIC);
  return data;
}

// POST /auth/invitation/check { token } -> { email, first_name, last_name, expires_at }.
// Errors: 400 {detail: {code: "invalid" | "inactive"}}, 410 {detail: {code: "expired" | "used" | "revoked"}}.
export async function checkInvitation(token) {
  const { data } = await api.post("/auth/invitation/check", { token }, PUBLIC);
  return data;
}

// POST /auth/invitation/accept { token, password } -> { message, email }. Activates the account with
// the person's own password (single use). Same errors as checkInvitation; 422 for a weak password.
export async function acceptInvitation(token, password) {
  const { data } = await api.post("/auth/invitation/accept", { token, password }, PUBLIC);
  return data;
}

// POST /auth/refresh - rotates the refresh token; returns new access AND refresh tokens.
export async function refreshTokens(refreshToken) {
  const { data } = await api.post("/auth/refresh", { refresh_token: refreshToken }, PUBLIC);
  return data;
}

// GET /auth/me - the signed-in user.
export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

// POST /auth/logout - revokes the refresh token's session.
export async function logoutSession(refreshToken) {
  await api.post("/auth/logout", { refresh_token: refreshToken }, PUBLIC);
}
