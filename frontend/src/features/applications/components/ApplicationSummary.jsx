import { Link } from "react-router-dom";
import { STATUSES } from "../../../api/applications";
import Badge from "../../../components/ui/Badge";
import Icon from "../../../components/ui/Icon";
import { formatDateTime } from "../../../utils/dates";
import { ResourceState } from "../../dashboard/components/DashboardCard";
import { applicationStatus, eventLabel, INTERVIEW_TYPE_LABEL } from "../applicationFormat";

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3" title={hint}>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-2xl font-semibold tabular-nums text-slate-900">{value}</dd>
    </div>
  );
}
const rate = (value) => (value == null ? "—" : `${Math.round(value * 10) / 10}%`);

// Totals from GET /applications/dashboard, shown as returned (rates are the backend's, with its formulas).
export default function ApplicationSummary({ summary, onStatus }) {
  return (
    <ResourceState resource={summary} label="your application summary" lines={3}>
      {(s) => (
        <div className="flex flex-col gap-5">
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Applications" value={s.total_applications} />
            <Stat label="Submitted" value={s.submitted_applications} hint={s.formulas?.submitted_applications} />
            <Stat label="Upcoming interviews" value={s.upcoming_interviews} />
            <Stat label="Saved internships" value={s.saved_internships} />
          </dl>

          <div>
            <h3 className="text-sm font-medium text-slate-700">By status</h3>
            <ul className="mt-2 flex flex-wrap gap-2" aria-label="Applications by status">
              {STATUSES.map((status) => {
                const st = applicationStatus(status);
                const count = s.by_status?.[status] ?? 0;
                return (
                  <li key={status}>
                    <button
                      type="button"
                      onClick={() => onStatus(status)}
                      className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                      aria-label={`${st.label}: ${count}. Show these applications`}
                    >
                      {st.label}
                      <span className="tabular-nums text-slate-500">{count}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <dl className="grid grid-cols-1 gap-2 text-xs text-slate-600 sm:grid-cols-3">
            {[
              ["Success rate", s.success_rate, s.formulas?.success_rate],
              ["Decision rate", s.decision_rate, s.formulas?.decision_rate],
              ["Interview rate", s.interview_rate, s.formulas?.interview_rate],
            ].map(([label, value, formula]) => (
              <div key={label} className="rounded-lg border border-slate-100 p-2.5">
                <dt className="font-medium text-slate-700">
                  {label}: <span className="tabular-nums">{rate(value)}</span>
                </dt>
                {formula && <dd className="mt-0.5 text-slate-500">{formula}</dd>}
              </div>
            ))}
          </dl>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div>
              <h3 className="text-sm font-medium text-slate-700">Upcoming interviews</h3>
              {s.next_interviews?.length ? (
                <ul className="mt-2 flex flex-col gap-2" aria-label="Upcoming interviews">
                  {s.next_interviews.map((i) => (
                    <li key={i.interview_id}>
                      <Link
                        to={`/applications/${i.application_id}`}
                        className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950 hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                      >
                        <Icon name="calendar" className="mt-0.5 h-4 w-4 shrink-0" />
                        <span className="min-w-0">
                          <span className="block font-medium">
                            {i.company_name} — {i.title}
                          </span>
                          <span className="block text-xs">
                            Round {i.round_number} · {INTERVIEW_TYPE_LABEL[i.interview_type] || i.interview_type} · {formatDateTime(i.scheduled_at)}
                          </span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-slate-500">No upcoming interviews.</p>
              )}
              <p className="mt-3 text-xs text-slate-500">
                Reminders: {s.pending_reminders} pending
                {s.overdue_reminders ? (
                  <>
                    {" "}
                    · <Badge tone="danger">{s.overdue_reminders} overdue</Badge>
                  </>
                ) : null}{" "}
                · {s.completed_reminders} completed
              </p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-slate-700">Recent activity</h3>
              {s.recent_activity?.length ? (
                <ul className="mt-2 flex flex-col gap-1.5 text-sm" aria-label="Recent activity">
                  {s.recent_activity.slice(0, 6).map((a) => (
                    <li key={a.activity_id} className="flex flex-col">
                      <Link to={`/applications/${a.application_id}`} className="font-medium text-slate-800 hover:underline">
                        {a.company_name} — {a.title}
                      </Link>
                      <span className="text-xs text-slate-500">
                        {eventLabel(a)} · {formatDateTime(a.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-slate-500">No activity yet.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </ResourceState>
  );
}
