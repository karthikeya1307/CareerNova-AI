// Labels for backend skill-gap values (backend/schemas/skill_gap_schema.py, services/skill_gap.py).

export const STATUS_META = {
  pending: { label: "To do", tone: "neutral" },
  in_progress: { label: "In progress", tone: "info" },
  completed: { label: "Completed", tone: "success" },
  dismissed: { label: "Dismissed", tone: "neutral" },
};

export const GAP_LEVEL = {
  missing: { label: "Missing", tone: "danger" },
  partial: { label: "Partly there", tone: "warning" },
  matched: { label: "You have it", tone: "success" },
};

export const IMPORTANCE = { required: "Required", preferred: "Preferred" };

export function statusMeta(status) {
  return STATUS_META[status] || { label: status, tone: "neutral" };
}

export function gapLevel(level) {
  return GAP_LEVEL[level] || { label: level, tone: "neutral" };
}

// "Completed" can come from the student or from the backend detecting the skill on the resume.
export function completedViaLabel(value) {
  if (value === "resume") return "Detected on your resume";
  if (value === "user") return "Marked by you";
  return null;
}

// Counts of real recommendation records by status (no derived scores).
export function countByStatus(items) {
  return (items || []).reduce((acc, rec) => ({ ...acc, [rec.status]: (acc[rec.status] || 0) + 1 }), {});
}

// The next thing to learn: highest-priority recommendation still open (list is priority-ordered).
export function nextRecommendation(items) {
  const open = (items || []).filter((r) => r.status === "in_progress" || r.status === "pending");
  return open.find((r) => r.status === "in_progress") || open[0] || null;
}
