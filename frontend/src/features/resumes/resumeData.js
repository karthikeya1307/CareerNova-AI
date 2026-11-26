// Helpers for backend resume data (ResumeListItem, ResumeDetailResponse / ResumeParsedData).

// The resume matching, skill gaps and the assistants should use: the student's preferred version if it
// parsed successfully, otherwise the newest resume whose parsing succeeded (the list is newest first).
export function latestParsed(resumes) {
  const list = resumes || [];
  return list.find((r) => r.is_preferred && r.status === "completed") || list.find((r) => r.status === "completed") || null;
}

// Parser list sections (education, work_experience, projects, internships) are objects shaped
// { details: "line\nline" }. Turn each into { heading, lines } without guessing structure; any
// other keys are shown as "key: value" lines rather than dropped.
export function entryLines(entry) {
  if (entry == null) return { heading: null, lines: [] };
  if (typeof entry === "string") return splitLines(entry);
  if (typeof entry !== "object") return { heading: String(entry), lines: [] };
  const { details, ...rest } = entry;
  const base = typeof details === "string" ? splitLines(details) : { heading: null, lines: [] };
  const extras = Object.entries(rest)
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "")
    .map(([key, value]) => `${humanKey(key)}: ${Array.isArray(value) ? value.join(", ") : String(value)}`);
  if (!base.heading && extras.length) return { heading: extras[0], lines: extras.slice(1) };
  return { heading: base.heading, lines: [...base.lines, ...extras] };
}

function splitLines(text) {
  const lines = String(text)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return { heading: lines[0] || null, lines: lines.slice(1) };
}

function humanKey(key) {
  const text = String(key).replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Contact fields shown from the parsed resume (ResumeParsedData).
export const CONTACT_FIELDS = [
  { key: "full_name", label: "Full name" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "address", label: "Address" },
  { key: "linkedin", label: "LinkedIn", link: true },
  { key: "github", label: "GitHub", link: true },
];

// Only http(s) links are rendered as links; anything else is shown as plain text.
export function safeExternalUrl(value) {
  if (!value) return null;
  const text = String(value).trim();
  const candidate = /^https?:\/\//i.test(text) ? text : /^(www\.)?(linkedin\.com|github\.com)\//i.test(text) ? `https://${text}` : null;
  if (!candidate) return null;
  try {
    const url = new URL(candidate);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}
