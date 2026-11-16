import { describe, expect, it } from "vitest";
import { ApiError, DEFAULT_MESSAGES, normalizeError } from "./errors";

const axiosError = (status, data, headers = {}) => ({ response: { status, data, headers }, config: {} });

describe("normalizeError", () => {
  it("uses a string detail as the message", () => {
    const error = normalizeError(axiosError(404, { detail: "Resume not found" }));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.message).toBe("Resume not found");
  });

  it("maps 422 validation lists to field errors", () => {
    const error = normalizeError(
      axiosError(422, {
        detail: [
          { loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" },
          { loc: ["body", "password"], msg: "Value error, Password is too short", type: "value_error" },
          { loc: ["body"], msg: "Field required", type: "missing" },
        ],
      }),
    );
    expect(error.status).toBe(422);
    expect(error.message).toBe(DEFAULT_MESSAGES[422]);
    expect(error.fieldErrors).toEqual({
      email: "value is not a valid email address",
      password: "Password is too short",
      _form: "Field required",
    });
  });

  it("keeps object details (for example a 409 duplicate with the existing id)", () => {
    const error = normalizeError(
      axiosError(409, { detail: { message: "You already have an application for this opening.", application_id: 12 } }),
    );
    expect(error.message).toBe("You already have an application for this opening.");
    expect(error.detail.application_id).toBe(12);
  });

  it("reads Retry-After on 429", () => {
    const error = normalizeError(axiosError(429, { detail: "Too many assistant requests." }, { "retry-after": "42" }));
    expect(error.status).toBe(429);
    expect(error.retryAfter).toBe(42);
  });

  it("explains network failures without technical details", () => {
    const error = normalizeError({ code: "ERR_NETWORK", message: "Network Error" });
    expect(error.status).toBe(0);
    expect(error.message).toBe(DEFAULT_MESSAGES[0]);
  });

  it("falls back to a default message per status", () => {
    expect(normalizeError(axiosError(503, null)).message).toBe(DEFAULT_MESSAGES[503]);
    expect(normalizeError(axiosError(418, {})).message).toBe(DEFAULT_MESSAGES[500]);
  });

  it("returns ApiError instances unchanged", () => {
    const original = new ApiError({ status: 403, message: "No" });
    expect(normalizeError(original)).toBe(original);
  });
});
