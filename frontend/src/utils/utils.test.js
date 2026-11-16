import { describe, expect, it } from "vitest";
import { formatDate, localInputToIso, parseDate } from "./dates";
import { safeRedirectPath } from "./redirect";
import { clearRefreshToken, getRefreshToken, isRemembered, saveRefreshToken } from "./storage";

describe("refresh-token storage (D4)", () => {
  it("uses sessionStorage by default", () => {
    saveRefreshToken("abc");
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBe("abc");
    expect(window.localStorage.getItem("acc.refresh_token")).toBeNull();
    expect(getRefreshToken()).toBe("abc");
    expect(isRemembered()).toBe(false);
  });

  it("uses localStorage only with Remember me, and never keeps two copies", () => {
    saveRefreshToken("one");
    saveRefreshToken("two", true);
    expect(window.localStorage.getItem("acc.refresh_token")).toBe("two");
    expect(window.sessionStorage.getItem("acc.refresh_token")).toBeNull();
    expect(isRemembered()).toBe(true);
    clearRefreshToken();
    expect(getRefreshToken()).toBeNull();
  });
});

describe("safeRedirectPath", () => {
  it.each(["/resumes", "/applications?status=APPLIED", "/internships/12#top"])("allows %s", (path) => {
    expect(safeRedirectPath(path)).toBe(path);
  });

  it.each([
    "https://evil.example", "//evil.example", "/\\evil.example", "\\\\evil", "javascript:alert(1)", "/javascript:alert(1)",
    "", null, "resumes", "/a\u0000b",
  ])("rejects %s", (path) => {
    expect(safeRedirectPath(path)).toBe("/");
  });
});

describe("dates", () => {
  it("parses both backend offset styles to the same instant", () => {
    expect(parseDate("2026-11-15T10:30:00+05:30").getTime()).toBe(parseDate("2026-11-15T05:00:00Z").getTime());
  });

  it("sends datetime-local values as UTC ISO strings", () => {
    expect(localInputToIso("2026-11-20T10:30")).toMatch(/Z$/);
    expect(localInputToIso("")).toBeNull();
  });

  it("formats missing dates safely", () => {
    expect(formatDate(null)).toBe("—");
  });
});
