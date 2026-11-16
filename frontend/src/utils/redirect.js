// Only allow in-app redirect targets such as "/resumes?x=1".
// Rejects absolute URLs, protocol-relative "//evil", backslash tricks "/\evil" (react-router
// advisory GHSA-wrjc-x8rr-h8h6 for v6) and anything with a scheme.
export function safeRedirectPath(next, fallback = "/") {
  if (typeof next !== "string" || next.length === 0 || next.length > 2000) return fallback;
  if (!next.startsWith("/")) return fallback;
  if (next.startsWith("//") || next.includes("\\")) return fallback;
  if (/^\/[^/?#]*:/.test(next)) return fallback;
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(next)) return fallback;
  return next;
}
