import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createApplication, LIMITS, WORK_MODES } from "../../../api/applications";
import { normalizeError } from "../../../api/errors";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import Input from "../../../components/ui/Input";
import Select from "../../../components/ui/Select";
import { localInputToIso } from "../../../utils/dates";

const EMPTY = { company_name: "", title: "", application_url: "", location: "", work_mode: "", status: "APPLIED", applied_at: "", notes: "" };

// Mirrors ApplicationCreate for an external application (one not in the internship catalogue).
export function validateNewApplication(form, now = new Date()) {
  const errors = {};
  if (!form.company_name.trim()) errors.company_name = "Enter the company.";
  else if (form.company_name.trim().length > LIMITS.name) errors.company_name = `Use at most ${LIMITS.name} characters.`;
  if (!form.title.trim()) errors.title = "Enter the role.";
  else if (form.title.trim().length > LIMITS.name) errors.title = `Use at most ${LIMITS.name} characters.`;
  const url = form.application_url.trim();
  if (url) {
    let ok = false;
    try {
      const parsed = new URL(url);
      ok = (parsed.protocol === "http:" || parsed.protocol === "https:") && Boolean(parsed.hostname) && !/\s/.test(url);
    } catch {
      ok = false;
    }
    if (!ok) errors.application_url = "Enter a full http:// or https:// URL.";
    else if (url.length > LIMITS.url) errors.application_url = `Use at most ${LIMITS.url} characters.`;
  }
  if (form.location.trim().length > 150) errors.location = "Use at most 150 characters.";
  if (form.status === "APPLIED" && form.applied_at) {
    const when = new Date(form.applied_at);
    if (Number.isNaN(when.getTime()) || when > now || when < new Date("2000-01-01T00:00:00Z")) errors.applied_at = "Choose a date between 2000 and now.";
  }
  if (form.notes.length > LIMITS.notes) errors.notes = `Keep notes under ${LIMITS.notes} characters.`;
  return errors;
}

export default function NewApplicationForm({ onCancel }) {
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [duplicate, setDuplicate] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const busy = useRef(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (busy.current) return;
    const found = validateNewApplication(form);
    setErrors(found);
    setApiError(null);
    setDuplicate(null);
    if (Object.keys(found).length) return;
    const body = { company_name: form.company_name.trim(), title: form.title.trim(), status: form.status };
    if (form.application_url.trim()) body.application_url = form.application_url.trim();
    if (form.location.trim()) body.location = form.location.trim();
    if (form.work_mode) body.work_mode = form.work_mode;
    if (form.status === "APPLIED" && form.applied_at) body.applied_at = localInputToIso(form.applied_at);
    if (form.notes.trim()) body.notes = form.notes;

    busy.current = true;
    setSubmitting(true);
    try {
      const created = await createApplication(body);
      navigate(`/applications/${created.application_id}`, { state: { created: true } });
    } catch (failure) {
      const err = normalizeError(failure);
      if (err.status === 409 && err.detail?.application_id) setDuplicate(err.detail.application_id);
      setApiError(failure);
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate aria-label="Add an application" className="flex flex-col gap-4">
      <p className="text-xs text-slate-500">For an internship you applied to outside this site. Internships from the catalogue are tracked from their page.</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Input label="Company" value={form.company_name} onChange={set("company_name")} error={errors.company_name} maxLength={LIMITS.name} required />
        <Input label="Role" value={form.title} onChange={set("title")} error={errors.title} maxLength={LIMITS.name} required />
        <Input label="Application link (optional)" type="url" value={form.application_url} onChange={set("application_url")} error={errors.application_url} placeholder="https://" />
        <Input label="Location (optional)" value={form.location} onChange={set("location")} error={errors.location} maxLength={150} />
        <Select
          label="Work mode (optional)"
          value={form.work_mode}
          onChange={set("work_mode")}
          options={[{ value: "", label: "Not specified" }, ...WORK_MODES.map((m) => ({ value: m, label: m }))]}
        />
        <Select
          label="Status"
          value={form.status}
          onChange={set("status")}
          options={[
            { value: "APPLIED", label: "Applied" },
            { value: "SAVED", label: "Saved (not applied yet)" },
          ]}
        />
        {form.status === "APPLIED" && (
          <Input label="Date applied (optional, defaults to now)" type="datetime-local" value={form.applied_at} onChange={set("applied_at")} error={errors.applied_at} />
        )}
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="new-app-notes" className="text-sm font-medium text-slate-700">
          Notes (optional)
        </label>
        <textarea
          id="new-app-notes"
          rows={3}
          value={form.notes}
          onChange={set("notes")}
          aria-invalid={errors.notes ? true : undefined}
          className="cn-input"
        />
        {errors.notes && <p className="text-xs text-red-600">{errors.notes}</p>}
      </div>
      <ErrorAlert error={apiError} title="The application couldn't be added" />
      {duplicate && (
        <Link to={`/applications/${duplicate}`} className="text-sm font-medium text-brand-700 hover:underline">
          Open the existing application
        </Link>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={submitting}>
          Add application
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
