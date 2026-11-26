import { useRef, useState } from "react";
import { addReminder, LIMITS, listReminders } from "../../../api/applications";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import Input from "../../../components/ui/Input";
import useApiResource from "../../../hooks/useApiResource";
import { localInputToIso } from "../../../utils/dates";
import { CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import ReminderItem from "./ReminderItem";

const TWO_YEARS = 730 * 24 * 3600 * 1000;

// Mirrors ReminderCreate: title 1-150, description up to 2000, remind_at not in the past and within two years.
export function validateReminder(form, now = new Date()) {
  const errors = {};
  if (!form.title.trim()) errors.title = "Enter a title.";
  else if (form.title.trim().length > LIMITS.reminderTitle) errors.title = `Use at most ${LIMITS.reminderTitle} characters.`;
  if (form.description.length > LIMITS.reminderDescription) errors.description = `Use at most ${LIMITS.reminderDescription} characters.`;
  const when = form.remind_at ? new Date(form.remind_at) : null;
  if (!when || Number.isNaN(when.getTime())) errors.remind_at = "Choose when.";
  else if (when < now) errors.remind_at = "Choose a time in the future.";
  else if (when.getTime() - now.getTime() > TWO_YEARS) errors.remind_at = "Choose a time within two years.";
  return errors;
}

export default function ApplicationReminders({ applicationId, onChanged }) {
  const list = useApiResource(() => listReminders({ applicationId, status: "all", limit: 100 }), `app-reminders:${applicationId}`);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", remind_at: "" });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  const changed = () => {
    list.reload();
    onChanged?.();
  };

  const submit = async (event) => {
    event.preventDefault();
    if (lock.current) return;
    const found = validateReminder(form);
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length) return;
    lock.current = true;
    setBusy(true);
    try {
      const body = { title: form.title.trim(), remind_at: localInputToIso(form.remind_at) };
      if (form.description.trim()) body.description = form.description;
      await addReminder(applicationId, body);
      setForm({ title: "", description: "", remind_at: "" });
      setAdding(false);
      changed();
    } catch (failure) {
      setApiError(failure);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="reminders-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="reminders-title" className="text-base font-semibold text-slate-900">
          Reminders
        </h2>
        {!adding && (
          <Button variant="secondary" onClick={() => setAdding(true)} className="py-1.5">
            Add reminder
          </Button>
        )}
      </div>
      <p className="text-xs text-slate-500">Stored reminders only: they appear here and on your dashboard. No email, SMS or push notification is sent.</p>
      {adding && (
        <form onSubmit={submit} noValidate aria-label="Add reminder" className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input label="Title" value={form.title} onChange={set("title")} error={errors.title} maxLength={LIMITS.reminderTitle} required />
            <Input label="Remind me at" type="datetime-local" value={form.remind_at} onChange={set("remind_at")} error={errors.remind_at} required />
          </div>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            Details (optional)
            <textarea rows={2} value={form.description} onChange={set("description")} className="rounded-md border border-slate-300 px-3 py-2 text-sm font-normal shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
            {errors.description && <span className="text-xs font-normal text-red-600">{errors.description}</span>}
          </label>
          <ErrorAlert error={apiError} title="The reminder couldn't be saved" />
          <div className="flex gap-2">
            <Button type="submit" loading={busy}>
              Save reminder
            </Button>
            <Button variant="ghost" onClick={() => setAdding(false)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {(list.status === "loading" || list.status === "idle") && !list.data ? (
        <CardSkeleton label="reminders" lines={2} />
      ) : list.status === "error" ? (
        <CardError error={list.error} onRetry={list.reload} label="reminders" />
      ) : !list.data.items.length ? (
        <p className="text-sm text-slate-500">No reminders for this application.</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Application reminders">
          {list.data.items.map((r) => (
            <ReminderItem key={r.reminder_id} reminder={r} onChanged={changed} />
          ))}
        </ul>
      )}
    </section>
  );
}
