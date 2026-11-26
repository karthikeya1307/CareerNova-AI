// Client-side validation for the auth forms. The limits mirror backend/schemas/user_schema.py so
// users see problems before a request is sent; the backend still validates everything.

export const LIMITS = {
  name: 100,
  passwordMin: 8,
  passwordMax: 128,
  tokenMin: 20,
  tokenMax: 256,
};

// Practical email check (the backend uses a full RFC validator).
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(value) {
  const email = (value || "").trim();
  if (!email) return "Enter your email address.";
  if (email.length > 254 || !EMAIL_RE.test(email)) return "Enter a valid email address, like name@example.com.";
  return null;
}

export function validateName(value, label) {
  const name = (value || "").trim();
  if (!name) return `Enter your ${label}.`;
  if (name.length > LIMITS.name) return `${capitalise(label)} must be ${LIMITS.name} characters or fewer.`;
  return null;
}

// Same rule as the backend: strip spaces, brackets, dots and dashes; 7-15 digits, optional leading +.
export function normalisePhone(value) {
  return (value || "").trim().replace(/[\s().-]/g, "");
}

export function validatePhone(value) {
  if (!(value || "").trim()) return "Enter your phone number.";
  if (!/^\+?\d{7,15}$/.test(normalisePhone(value))) return "Enter a valid phone number with 7 to 15 digits.";
  return null;
}

// Requirements shown live under new-password fields. The backend enforces the length; the letter and
// number rules are a client-side strength floor for new passwords only (never applied at sign-in).
export const PASSWORD_RULES = [
  { id: "length", label: `${LIMITS.passwordMin} to ${LIMITS.passwordMax} characters`,
    test: (v) => v.length >= LIMITS.passwordMin && v.length <= LIMITS.passwordMax },
  { id: "letter", label: "At least one letter", test: (v) => /\p{L}/u.test(v) },
  { id: "number", label: "At least one number", test: (v) => /\d/.test(v) },
];

export function validateNewPassword(value) {
  const password = value || "";
  if (!password) return "Create a password.";
  const failed = PASSWORD_RULES.find((rule) => !rule.test(password));
  return failed ? `Password needs: ${failed.label.toLowerCase()}.` : null;
}

export function validateConfirmation(password, confirmation) {
  if (!confirmation) return "Confirm your password.";
  return password === confirmation ? null : "Passwords do not match.";
}

export function validateLoginPassword(value) {
  return value ? null : "Enter your password.";
}

export function validateToken(value) {
  const token = (value || "").trim();
  if (!token) return "Enter the reset code from your email.";
  if (token.length < LIMITS.tokenMin || token.length > LIMITS.tokenMax || /\s/.test(token)) {
    return "That reset code doesn't look right. Copy the whole code from the email.";
  }
  return null;
}

// Drop empty entries so `Object.keys(errors).length` means "has errors".
export function compactErrors(errors) {
  return Object.fromEntries(Object.entries(errors).filter(([, message]) => message));
}

function capitalise(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
