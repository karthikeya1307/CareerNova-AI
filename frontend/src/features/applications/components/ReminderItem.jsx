import { useState } from "react";
import { Link } from "react-router-dom";
import { deleteReminder, updateReminder } from "../../../api/applications";
import { errorMessage } from "../../../api/errors";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import { useConfirm } from "../../../context/ConfirmContext";
import { formatDateTime } from "../../../utils/dates";

// One stored reminder (ReminderOut). Reminders are never sent by email, SMS or push: they are only
// listed here and on the dashboard.
export default function ReminderItem({ reminder: r, showApplication = false, onChanged }) {
  const confirm = useConfirm();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const run = async (name, task) => {
    if (busy) return;
    setBusy(name);
    setError(null);
    try {
      await task();
      onChanged?.();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  };
  const toggle = () => run("toggle", () => updateReminder(r.reminder_id, { is_completed: !r.is_completed }));
  const remove = async () => {
    const ok = await confirm({ title: "Delete this reminder?", message: `“${r.title}” will be deleted.`, confirmLabel: "Delete reminder", tone: "danger" });
    if (ok) await run("delete", () => deleteReminder(r.reminder_id));
  };

  return (
    // Stacked at every width: on an application page reminders sit in a narrow side column.
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3">
      <div className="min-w-0">
        <p className={`font-medium ${r.is_completed ? "text-slate-500 line-through" : "text-slate-900"}`}>{r.title}</p>
        {showApplication && (
          <Link to={`/applications/${r.application_id}`} className="text-sm text-brand-700 hover:underline">
            {r.company_name} — {r.application_title}
          </Link>
        )}
        {r.description && <p className="mt-0.5 whitespace-pre-line text-sm text-slate-600">{r.description}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
          {formatDateTime(r.remind_at)}
          {r.is_completed ? <Badge tone="success">Done</Badge> : r.overdue ? <Badge tone="danger">Overdue</Badge> : r.due_within_24h ? <Badge tone="warning">Due within 24 hours</Badge> : null}
          {r.delivery === "not_sent" && <span>· Stored only, not sent</span>}
        </p>
        {error && (
          <p role="alert" className="mt-1 text-sm text-red-700">
            {error}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={toggle} loading={busy === "toggle"} disabled={Boolean(busy)} className="py-1.5" aria-label={`${r.is_completed ? "Mark as not done" : "Mark as done"}: ${r.title}`}>
          {r.is_completed ? "Mark as not done" : "Mark as done"}
        </Button>
        <Button variant="ghost" onClick={remove} disabled={Boolean(busy)} className="py-1.5" aria-label={`Delete reminder ${r.title}`}>
          Delete
        </Button>
      </div>
    </li>
  );
}
