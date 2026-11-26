// Display helpers for application tracking. Values and rules come from the backend; this file only
// supplies labels.
import { applicationStatus } from "../dashboard/format";

export { applicationStatus };

export const SORT_LABEL = {
  updated_at: "Last updated",
  created_at: "Date added",
  applied_at: "Date applied",
  company_name: "Company",
  title: "Role",
  status: "Status",
};

export const INTERVIEW_TYPE_LABEL = {
  technical: "Technical",
  hr: "HR",
  behavioral: "Behavioural",
  managerial: "Managerial",
  case_study: "Case study",
  assignment: "Assignment",
  group: "Group discussion",
  other: "Other",
};
export const INTERVIEW_MODE_LABEL = { online: "Online", offline: "In person", phone: "Phone" };
export const OUTCOME = {
  pending: { label: "Pending", tone: "warning" },
  passed: { label: "Passed", tone: "success" },
  failed: { label: "Not passed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  no_show: { label: "No-show", tone: "neutral" },
};
export const outcome = (o) => OUTCOME[o] || { label: o, tone: "neutral" };

// Status changes that close or decide an application: confirm before sending.
export const CONSEQUENTIAL = ["SELECTED", "REJECTED", "WITHDRAWN"];

export const CHANGE_TYPE = {
  created: "Created",
  manual: "Changed by you",
  correction: "Correction (undo)",
  interview_added: "Interview round added",
  interview_cancelled: "Interview rounds cancelled",
};
export const changeType = (t) => CHANGE_TYPE[t] || t;

const EVENT = {
  application_created: "Application added",
  status_changed: "Status changed",
  details_updated: "Details updated",
  application_deleted: "Moved to the trash",
  application_restored: "Restored from the trash",
  interview_added: "Interview round added",
  interview_updated: "Interview round updated",
  interview_deleted: "Interview round deleted",
  reminder_created: "Reminder added",
  reminder_updated: "Reminder updated",
  reminder_deleted: "Reminder deleted",
};
export function eventLabel(event) {
  const base = EVENT[event.event_type] || event.event_type;
  const d = event.details || {};
  if (event.event_type === "status_changed" && d.to_status) {
    return `${base}: ${applicationStatus(d.from_status).label} → ${applicationStatus(d.to_status).label}`;
  }
  if (d.round_number) return `${base} (round ${d.round_number})`;
  if (Array.isArray(d.fields) && d.fields.length) return `${base}: ${d.fields.join(", ").replace(/_/g, " ")}`;
  return base;
}

// The status the last change came from (a correction may only go back there), from GET /history.
// Same rule as application_service.last_change_into: the newest entry (highest history_id) into
// the current status.
export function correctionTarget(history, current) {
  const latest = [...(history?.status_history || [])]
    .filter((e) => e.to_status === current)
    .sort((a, b) => b.history_id - a.history_id)[0];
  return latest?.from_status || null;
}
