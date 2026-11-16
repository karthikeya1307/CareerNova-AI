// Turn any Axios/FastAPI failure into one predictable shape for the UI.
//
// FastAPI returns `detail` as:
//   * a string                       -> { "detail": "Resume not found" }
//   * a list (422 validation errors) -> { "detail": [{ "loc": ["body", "email"], "msg": "...", ... }] }
//   * an object (e.g. Phase 7 409)   -> { "detail": { "message": "...", "application_id": 12 } }

export const DEFAULT_MESSAGES = {
  0: "Cannot reach the server. Check that the backend is running and try again.",
  400: "The request could not be processed.",
  401: "Your session has expired. Please sign in again.",
  403: "You do not have permission to do that.",
  404: "The requested item was not found.",
  409: "That conflicts with existing data.",
  413: "The file is too large.",
  415: "That file type is not supported.",
  422: "Please check the highlighted fields.",
  429: "Too many requests. Please wait and try again.",
  500: "Something went wrong on the server.",
  503: "The service is temporarily unavailable. Please try again later.",
};

export class ApiError extends Error {
  constructor({ status = 0, message, fieldErrors = {}, detail = null, retryAfter = null, code = null }) {
    super(message || DEFAULT_MESSAGES[status] || DEFAULT_MESSAGES[500]);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.detail = detail;
    this.retryAfter = retryAfter;
    this.code = code;
  }
}

function fieldName(loc) {
  if (!Array.isArray(loc)) return "_form";
  const parts = loc.filter((part) => part !== "body" && part !== "query" && part !== "path");
  return parts.length ? parts.join(".") : "_form";
}

function cleanMessage(msg) {
  // Pydantic prefixes custom validator messages with "Value error, ".
  return String(msg || "").replace(/^Value error,\s*/i, "");
}

function parseRetryAfter(headers) {
  const raw = headers?.["retry-after"] ?? headers?.get?.("retry-after");
  const seconds = Number.parseInt(raw, 10);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function normalizeError(error) {
  if (error instanceof ApiError) return error;

  const response = error?.response;
  if (!response) {
    return new ApiError({ status: 0, code: error?.code || "network_error" });
  }

  const { status, data, headers } = response;
  const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
  const retryAfter = parseRetryAfter(headers);

  if (Array.isArray(detail)) {
    const fieldErrors = {};
    for (const item of detail) {
      const name = fieldName(item?.loc);
      if (!fieldErrors[name]) fieldErrors[name] = cleanMessage(item?.msg);
    }
    return new ApiError({ status, message: DEFAULT_MESSAGES[422], fieldErrors, detail, retryAfter });
  }
  if (typeof detail === "string") {
    return new ApiError({ status, message: detail, detail, retryAfter });
  }
  if (detail && typeof detail === "object") {
    return new ApiError({ status, message: detail.message || DEFAULT_MESSAGES[status], detail, retryAfter });
  }
  return new ApiError({ status, detail: data ?? null, retryAfter });
}

export function errorMessage(error) {
  return normalizeError(error).message;
}
