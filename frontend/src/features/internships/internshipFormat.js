// Display and sorting helpers for backend InternshipResponse objects.
import { parseDate } from "../../utils/dates";

export function formatStipend(amount, currency = "INR") {
  if (amount == null) return null;
  if (amount === 0) return "Unpaid";
  try {
    return `${new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount)}/month`;
  } catch {
    return `${amount} ${currency}/month`;
  }
}

export function formatDuration(weeks) {
  if (weeks == null) return null;
  if (weeks % 4 === 0 && weeks >= 8) return `${weeks / 4} months`;
  return `${weeks} week${weeks === 1 ? "" : "s"}`;
}

// { label, tone } for the deadline, or null when the internship has none.
export function deadlineInfo(deadline, now = new Date()) {
  const date = parseDate(deadline);
  if (!date) return null;
  const days = Math.ceil((date.getTime() - now.getTime()) / 86400000);
  if (days < 0) return { label: "Deadline passed", tone: "danger", date };
  if (days === 0) return { label: "Closes today", tone: "warning", date };
  if (days <= 7) return { label: `Closes in ${days} day${days === 1 ? "" : "s"}`, tone: "warning", date };
  return { label: `Apply by ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date)}`, tone: "neutral", date };
}

// Client-side sorts (the backend list has a fixed order by id). Missing values always sort last.
const text = (key) => (a, b) => String(a[key] || "").localeCompare(String(b[key] || ""), undefined, { sensitivity: "base" });
const numeric = (key, dir) => (a, b) => {
  const x = a[key];
  const y = b[key];
  if (x == null && y == null) return 0;
  if (x == null) return 1;
  if (y == null) return -1;
  return dir * (x - y);
};
const byDeadline = (a, b) => {
  const x = parseDate(a.deadline)?.getTime();
  const y = parseDate(b.deadline)?.getTime();
  if (x == null && y == null) return 0;
  if (x == null) return 1;
  if (y == null) return -1;
  return x - y;
};

export const SORTS = [
  { id: "", label: "Default order" },
  { id: "title", label: "Title (A–Z)", compare: text("title") },
  { id: "company", label: "Company (A–Z)", compare: text("company") },
  { id: "stipend", label: "Stipend (highest first)", compare: numeric("stipend_per_month", -1) },
  { id: "duration", label: "Duration (shortest first)", compare: numeric("duration_weeks", 1) },
  { id: "deadline", label: "Deadline (soonest first)", compare: byDeadline },
];

export function sortInternships(items, sortId) {
  const sort = SORTS.find((s) => s.id === sortId);
  if (!sort?.compare) return items;
  // Stable: ties keep the backend order.
  return items.map((item, index) => ({ item, index })).sort((a, b) => sort.compare(a.item, b.item) || a.index - b.index).map((x) => x.item);
}

export const EXAMPLE_QUERIES = [
  "Python internships for freshers",
  "Data science internships",
  "Machine learning internships",
  "Backend developer internships",
  "AI and generative AI internships",
];
