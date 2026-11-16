import { api } from "./client";

// GET /health - public, read-only database connectivity check.
export async function getHealth() {
  const { data } = await api.get("/health", { skipAuth: true, skipAuthRefresh: true });
  return data;
}
