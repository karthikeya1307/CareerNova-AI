// Authentication state (infrastructure; the sign-in screens arrive in F1).
//
//   * access token  -> memory only (api/client.js)
//   * refresh token -> sessionStorage, or localStorage with "Remember me" (utils/storage.js)
//   * status        -> "loading" (restoring a session) | "authenticated" | "anonymous"
//                      | "unavailable" (a stored session could not be checked because the server
//                        was unreachable or failed; the refresh token is kept, retrySession() retries)
//
// The client's 401 handler calls `refresh` here. Only a 401 from /auth/refresh clears the session.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getMe, logoutSession, refreshTokens } from "../api/auth";
import { configureAuth, isSessionRejected, refreshAccessToken, setAccessToken } from "../api/client";
import { ApiError, normalizeError } from "../api/errors";
import { clearRefreshToken, getRefreshToken, isRemembered, saveRefreshToken } from "../utils/storage";

const AuthContext = createContext(null);

export function AuthProvider({ children, initialUser = null, restoreSession = true }) {
  const [user, setUser] = useState(initialUser);
  const [status, setStatus] = useState(() => {
    if (initialUser) return "authenticated";
    return restoreSession && getRefreshToken() ? "loading" : "anonymous";
  });
  const [sessionError, setSessionError] = useState(null);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    clearRefreshToken();
    setUser(null);
    setSessionError(null);
    setStatus("anonymous");
  }, []);

  // Exchange the stored refresh token for a new access token (the backend rotates it).
  const refresh = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) throw new ApiError({ status: 401, message: "No refresh token" });
    const tokens = await refreshTokens(refreshToken);
    saveRefreshToken(tokens.refresh_token, isRemembered());
    return tokens.access_token;
  }, []);

  useEffect(() => {
    configureAuth({ refresh, onAuthFailure: clearSession });
    return () => configureAuth({});
  }, [refresh, clearSession]);

  // Restore a session after a page reload.
  useEffect(() => {
    if (status !== "loading") return undefined;
    let cancelled = false;
    (async () => {
      try {
        await refreshAccessToken();
        const me = await getMe();
        if (!cancelled) {
          setUser(me);
          setSessionError(null);
          setStatus("authenticated");
        }
      } catch (error) {
        if (cancelled) return;
        if (isSessionRejected(error)) {
          clearSession();
        } else {
          // Server unreachable or failing: keep the refresh token and let the user retry.
          // No automatic retry, so this can never loop.
          setAccessToken(null);
          setSessionError(normalizeError(error));
          setStatus("unavailable");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, clearSession]);

  const retrySession = useCallback(() => {
    setStatus((current) => (current === "unavailable" ? "loading" : current));
  }, []);

  // Called by the login screen with the /auth/login response.
  const startSession = useCallback(
    async (tokens, remember = false) => {
      setAccessToken(tokens.access_token);
      saveRefreshToken(tokens.refresh_token, remember);
      let me;
      try {
        me = await getMe();
      } catch (error) {
        // Never keep tokens for a session the UI could not start: revoke it (best effort) and clear.
        // A 401 from /auth/me may already have rotated the refresh token, so revoke the newest one.
        logoutSession(getRefreshToken() || tokens.refresh_token).catch(() => {});
        clearSession();
        throw error;
      }
      setUser(me);
      setSessionError(null);
      setStatus("authenticated");
      return me;
    },
    [clearSession],
  );

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    try {
      if (refreshToken) await logoutSession(refreshToken);
    } catch {
      // The session is cleared locally even if the server cannot be reached.
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo(
    () => ({
      user,
      status,
      sessionError,
      isAuthenticated: status === "authenticated",
      // The super admin can do everything an admin can (backend/utils/roles.ADMIN_ROLES).
      isAdmin: user?.role === "admin" || user?.role === "super_admin",
      isSuperAdmin: user?.role === "super_admin",
      startSession,
      logout,
      retrySession,
      setUser,
    }),
    [user, status, sessionError, startSession, logout, retrySession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
