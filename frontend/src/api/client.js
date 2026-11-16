// Shared Axios client for the FastAPI backend.
//
// * baseURL "/api" (Vite proxy in development, see vite.config.js).
// * The access token is held in memory only and attached as "Authorization: Bearer ...".
// * On a 401 the request is retried ONCE after a refresh. All requests that fail at the same
//   time share ONE refresh call: the backend rotates refresh tokens, so two parallel refreshes
//   would revoke each other.
// * The session is cleared only when the refresh endpoint itself answers 401.
// * Errors are normalised to ApiError (api/errors.js).

import axios from "axios";
import { normalizeError } from "./errors";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

let accessToken = null;
let refreshHandler = null; // async () => newAccessToken   (provided by AuthContext)
let authFailureHandler = null; // () => void              (provided by AuthContext)
let refreshPromise = null;

export function setAccessToken(token) {
  accessToken = token || null;
}

export function getAccessToken() {
  return accessToken;
}

export function configureAuth({ refresh = null, onAuthFailure = null } = {}) {
  refreshHandler = refresh;
  authFailureHandler = onAuthFailure;
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // matching runs and document generation can take a while
});

api.interceptors.request.use((config) => {
  if (accessToken && !config.skipAuth) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// Only an HTTP 401 from the refresh endpoint ends the session. Network failures (status 0),
// 5xx and other errors leave the stored refresh token alone.
export function isSessionRejected(error) {
  return normalizeError(error).status === 401;
}

export function refreshAccessToken() {
  if (!refreshHandler) return Promise.reject(new Error("No refresh handler configured"));
  if (!refreshPromise) {
    refreshPromise = Promise.resolve()
      .then(() => refreshHandler())
      .then((token) => {
        setAccessToken(token);
        return token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error?.config;
    const status = error?.response?.status;
    const canRefresh = status === 401 && original && !original._retried && !original.skipAuthRefresh && refreshHandler;

    if (canRefresh) {
      original._retried = true;
      try {
        const token = await refreshAccessToken();
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      } catch (refreshError) {
        const failure = normalizeError(refreshError);
        if (isSessionRejected(failure)) {
          // The server rejected the refresh token: the session is really over.
          setAccessToken(null);
          if (authFailureHandler) authFailureHandler();
          return Promise.reject(normalizeError(error));
        }
        // Network failure or server error: keep the stored refresh token (the session may still
        // be valid) and report the real problem instead of "session expired".
        return Promise.reject(failure);
      }
    }
    return Promise.reject(normalizeError(error));
  },
);
