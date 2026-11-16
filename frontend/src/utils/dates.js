// The backend returns timestamps with an offset: "+05:30" (Phases 1-6) or "Z" (Phases 7-8).
// Both parse correctly with Date. Phase 7+ requests need an offset: always send toISOString().

export function parseDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value, options = { dateStyle: "medium" }) {
  const date = parseDate(value);
  return date ? new Intl.DateTimeFormat(undefined, options).format(date) : "—";
}

export function formatDateTime(value) {
  return formatDate(value, { dateStyle: "medium", timeStyle: "short" });
}

// <input type="datetime-local"> gives local wall-clock time without an offset.
export function localInputToIso(localValue) {
  const date = parseDate(localValue);
  return date ? date.toISOString() : null;
}

export function isoToLocalInput(value) {
  const date = parseDate(value);
  if (!date) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}`;
}
