// Refresh-token storage (decision D4).
//   * Access tokens are NEVER stored: they live in memory only (api/client.js).
//   * Refresh tokens go to sessionStorage by default (cleared when the tab/browser closes)
//     and to localStorage only when the user ticks "Remember me".
//   * Passwords are never stored anywhere.
// Every access is wrapped in try/catch: storage can be unavailable (private mode, blocked).

const KEY = "acc.refresh_token";

function safe(fn, fallback = null) {
  try {
    return fn();
  } catch {
    return fallback;
  }
}

export function saveRefreshToken(token, remember = false) {
  clearRefreshToken();
  const store = remember ? window.localStorage : window.sessionStorage;
  safe(() => store.setItem(KEY, token));
}

export function getRefreshToken() {
  return (
    safe(() => window.sessionStorage.getItem(KEY)) || safe(() => window.localStorage.getItem(KEY)) || null
  );
}

export function isRemembered() {
  return Boolean(safe(() => window.localStorage.getItem(KEY)));
}

export function clearRefreshToken() {
  safe(() => window.sessionStorage.removeItem(KEY));
  safe(() => window.localStorage.removeItem(KEY));
}
