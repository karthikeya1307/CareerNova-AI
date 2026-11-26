// Display helpers for backend values on the dashboard.

// Application statuses (backend/schemas/application_schema.py `Status`).
export const APPLICATION_STATUS = {
  SAVED: { label: "Saved", tone: "neutral" },
  APPLIED: { label: "Applied", tone: "info" },
  SHORTLISTED: { label: "Shortlisted", tone: "info" },
  INTERVIEW_SCHEDULED: { label: "Interview scheduled", tone: "warning" },
  SELECTED: { label: "Selected", tone: "success" },
  REJECTED: { label: "Rejected", tone: "danger" },
  WITHDRAWN: { label: "Withdrawn", tone: "neutral" },
};

export function applicationStatus(status) {
  return APPLICATION_STATUS[status] || { label: humanize(status), tone: "neutral" };
}

// Resume statuses (backend Resume.status): uploaded | completed | failed.
export const RESUME_STATUS = {
  completed: { label: "Parsed", tone: "success" },
  uploaded: { label: "Processing", tone: "warning" },
  failed: { label: "Parsing failed", tone: "danger" },
};

export function resumeStatus(status) {
  return RESUME_STATUS[status] || { label: humanize(status), tone: "neutral" };
}

export function humanize(value) {
  const text = String(value ?? "").replace(/_/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1).toLowerCase() : "—";
}

// The best result of a match run: highest score, ties broken by rank.
export function bestMatch(run) {
  const results = run?.results || [];
  return results.reduce((best, item) => {
    if (!best) return item;
    if (item.score > best.score) return item;
    if (item.score === best.score && (item.rank ?? Infinity) < (best.rank ?? Infinity)) return item;
    return best;
  }, null);
}

export function percent(part, total) {
  return total > 0 ? Math.round((part / total) * 100) : 0;
}

export function greeting(date = new Date()) {
  const hour = date.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}
