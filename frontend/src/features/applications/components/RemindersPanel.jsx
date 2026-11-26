import { useState } from "react";
import { listReminders } from "../../../api/applications";
import useApiResource from "../../../hooks/useApiResource";
import { CardEmpty, CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import ReminderItem from "./ReminderItem";

const STATES = [
  { id: "pending", label: "Pending" },
  { id: "completed", label: "Done" },
  { id: "all", label: "All" },
];

// All stored reminders (GET /applications/reminders?status=pending|completed|all).
export default function RemindersPanel({ onChanged }) {
  const [state, setState] = useState("pending");
  const list = useApiResource(() => listReminders({ status: state, limit: 100 }), `reminders:${state}`);
  const changed = () => {
    list.reload();
    onChanged?.();
  };
  return (
    <div className="flex flex-col gap-3">
      <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        Reminders are saved notes with a due time. They are shown here and on your dashboard; no email, SMS or push notification is sent.
        Add them from an application's page.
      </p>
      <div role="group" aria-label="Filter reminders" className="inline-flex w-fit gap-1 rounded-lg bg-slate-100 p-1">
        {STATES.map((s) => (
          <button
            key={s.id}
            type="button"
            aria-pressed={state === s.id}
            onClick={() => setState(s.id)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
              state === s.id ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
      {(list.status === "loading" || list.status === "idle") && !list.data ? (
        <CardSkeleton label="your reminders" lines={3} />
      ) : list.status === "error" ? (
        <CardError error={list.error} onRetry={list.reload} label="your reminders" />
      ) : !list.data.items.length ? (
        <CardEmpty title={state === "completed" ? "No completed reminders" : "No reminders"} message="Add a reminder from an application to see it here." />
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Reminders">
          {list.data.items.map((r) => (
            <ReminderItem key={r.reminder_id} reminder={r} showApplication onChanged={changed} />
          ))}
        </ul>
      )}
    </div>
  );
}
