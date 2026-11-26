import { formatDateTime } from "../../../utils/dates";
import { CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import { applicationStatus, changeType, eventLabel } from "../applicationFormat";

// GET /applications/{id}/history: status changes and the activity log, newest first.
export default function HistoryTimeline({ history }) {
  if ((history.status === "loading" || history.status === "idle") && !history.data) return <CardSkeleton label="the history" lines={3} />;
  if (history.status === "error") return <CardError error={history.error} onRetry={history.reload} label="the history" />;
  const statuses = [...(history.data.status_history || [])].sort((a, b) => b.history_id - a.history_id);
  const activity = [...(history.data.activity || [])].sort((a, b) => b.activity_id - a.activity_id);
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
      <div>
        <h3 className="text-sm font-medium text-slate-700">Status changes</h3>
        <ol className="mt-2 flex flex-col gap-2 border-l border-slate-200 pl-4" aria-label="Status history">
          {statuses.map((h) => (
            <li key={h.history_id} className="text-sm">
              <p className="font-medium text-slate-900">
                {h.from_status ? `${applicationStatus(h.from_status).label} → ` : ""}
                {applicationStatus(h.to_status).label}
              </p>
              <p className="text-xs text-slate-500">
                {changeType(h.change_type)} · {formatDateTime(h.changed_at)}
              </p>
            </li>
          ))}
        </ol>
      </div>
      <div>
        <h3 className="text-sm font-medium text-slate-700">Activity</h3>
        {activity.length ? (
          <ul className="mt-2 flex flex-col gap-1.5 text-sm" aria-label="Activity">
            {activity.map((e) => (
              <li key={e.activity_id}>
                <span className="text-slate-800">{eventLabel(e)}</span>
                <span className="block text-xs text-slate-500">{formatDateTime(e.created_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-500">No activity yet.</p>
        )}
      </div>
    </div>
  );
}
