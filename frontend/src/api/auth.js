// Auth endpoints used by the infrastructure in F0. Screens (login, register, ...) arrive in F1.
import { api } from "./client";

// POST /auth/refresh - rotates the refresh token; returns new access AND refresh tokens.
export async function refreshTokens(refreshToken) {
  const { data } = await api.post(
    "/auth/refresh",
    { refresh_token: refreshToken },
    { skipAuth: true, skipAuthRefresh: true },
  );
  return data;
}

// GET /auth/me - the signed-in user.
export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

// POST /auth/logout - revokes the refresh token's session.
export async function logoutSession(refreshToken) {
  await api.post("/auth/logout", { refresh_token: refreshToken }, { skipAuth: true, skipAuthRefresh: true });
}
