import { PROFILE_LIMITS } from "../../api/profile";

// Form <-> API mapping for the student profile (backend ProfileCreate / ProfileUpdate).
export const PROFILE_FIELDS = ["college", "degree", "graduation_year", "location"];

export function toFormValues(profile) {
  return {
    college: profile?.college ?? "",
    degree: profile?.degree ?? "",
    graduation_year: profile?.graduation_year == null ? "" : String(profile.graduation_year),
    location: profile?.location ?? "",
  };
}

// Same rules as the backend schema: optional text with max lengths, year 1900-2100.
export function validateProfile(values) {
  const errors = {};
  const text = (name, label, max) => {
    if ((values[name] || "").trim().length > max) errors[name] = `${label} must be ${max} characters or fewer.`;
  };
  text("college", "College", PROFILE_LIMITS.college);
  text("degree", "Degree", PROFILE_LIMITS.degree);
  text("location", "Location", PROFILE_LIMITS.location);
  const year = (values.graduation_year || "").trim();
  if (year) {
    if (!/^\d{4}$/.test(year)) errors.graduation_year = "Enter a four-digit year, for example 2027.";
    else if (Number(year) < PROFILE_LIMITS.yearMin || Number(year) > PROFILE_LIMITS.yearMax) {
      errors.graduation_year = `Enter a year between ${PROFILE_LIMITS.yearMin} and ${PROFILE_LIMITS.yearMax}.`;
    }
  }
  return errors;
}

// API value for each field: trimmed text or null; year as an integer or null.
export function toApiValues(values) {
  const clean = (v) => {
    const t = (v || "").trim();
    return t ? t : null;
  };
  const year = (values.graduation_year || "").trim();
  return {
    college: clean(values.college),
    degree: clean(values.degree),
    graduation_year: year ? Number(year) : null,
    location: clean(values.location),
  };
}

// Only the fields that differ from the saved profile (PATCH sends nothing else).
export function changedFields(values, profile) {
  const next = toApiValues(values);
  return Object.fromEntries(PROFILE_FIELDS.filter((f) => next[f] !== (profile?.[f] ?? null)).map((f) => [f, next[f]]));
}

// Completeness from real data only: the account, the saved profile and a parsed resume.
export function completeness({ user, profile, hasParsedResume }) {
  const items = [
    { id: "name", label: "Name", done: Boolean(user?.first_name && user?.last_name) },
    { id: "email", label: "Verified email", done: Boolean(user?.email && user?.is_verified) },
    { id: "phone", label: "Phone number", done: Boolean(user?.phone_number) },
    { id: "college", label: "College", done: Boolean(profile?.college) },
    { id: "degree", label: "Degree", done: Boolean(profile?.degree) },
    { id: "graduation_year", label: "Graduation year", done: profile?.graduation_year != null },
    { id: "location", label: "Location", done: Boolean(profile?.location) },
    { id: "resume", label: "Parsed resume", done: Boolean(hasParsedResume) },
  ];
  const done = items.filter((i) => i.done).length;
  return { items, done, total: items.length, percent: Math.round((done / items.length) * 100) };
}
