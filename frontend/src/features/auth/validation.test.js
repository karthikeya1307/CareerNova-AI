import { describe, expect, it } from "vitest";
import {
  compactErrors, normalisePhone, validateConfirmation, validateEmail, validateLoginPassword, validateName,
  validateNewPassword, validatePhone, validateToken,
} from "./validation";

describe("auth validation", () => {
  it.each(["student@example.com", " Name.Surname+tag@uni.ac.in "])("accepts email %s", (email) => {
    expect(validateEmail(email)).toBeNull();
  });

  it.each(["", "   ", "student", "student@", "@example.com", "a b@example.com", "student@example"])("rejects email %j", (email) => {
    expect(validateEmail(email)).toMatch(/email/i);
  });

  it("requires names up to the backend's 100 characters", () => {
    expect(validateName("  ", "first name")).toBe("Enter your first name.");
    expect(validateName("Ada", "first name")).toBeNull();
    expect(validateName("x".repeat(101), "last name")).toBe("Last name must be 100 characters or fewer.");
  });

  it("normalises and validates phone numbers like the backend", () => {
    expect(normalisePhone(" +91 (98765) 43-210 ")).toBe("+919876543210");
    expect(validatePhone("+91 98765 43210")).toBeNull();
    expect(validatePhone("98765.43210")).toBeNull();
    expect(validatePhone("")).toBe("Enter your phone number.");
    expect(validatePhone("12345")).toMatch(/7 to 15 digits/);
    expect(validatePhone("1234567890123456")).toMatch(/7 to 15 digits/);
    expect(validatePhone("98765abc43")).toMatch(/7 to 15 digits/);
  });

  it("enforces new-password rules (8-128, a letter and a number)", () => {
    expect(validateNewPassword("")).toBe("Create a password.");
    expect(validateNewPassword("abc12")).toMatch(/8 to 128 characters/);
    expect(validateNewPassword("abcdefgh")).toMatch(/number/);
    expect(validateNewPassword("12345678")).toMatch(/letter/);
    expect(validateNewPassword(`a1${"x".repeat(127)}`)).toMatch(/8 to 128/);
    expect(validateNewPassword("career2026")).toBeNull();
    expect(validateNewPassword("пароль2026")).toBeNull(); // any alphabet counts as a letter
  });

  it("never applies new-password rules at sign-in", () => {
    expect(validateLoginPassword("x")).toBeNull();
    expect(validateLoginPassword("")).toBe("Enter your password.");
  });

  it("checks the confirmation matches", () => {
    expect(validateConfirmation("career2026", "")).toBe("Confirm your password.");
    expect(validateConfirmation("career2026", "career2025")).toBe("Passwords do not match.");
    expect(validateConfirmation("career2026", "career2026")).toBeNull();
  });

  it("checks reset codes against the backend's 20-256 length", () => {
    expect(validateToken("")).toMatch(/reset code/);
    expect(validateToken("short")).toMatch(/doesn't look right/);
    expect(validateToken("has a space in the middle of it")).toMatch(/doesn't look right/);
    expect(validateToken("t".repeat(43))).toBeNull();
  });

  it("drops empty entries", () => {
    expect(compactErrors({ a: null, b: "x", c: undefined })).toEqual({ b: "x" });
  });
});
