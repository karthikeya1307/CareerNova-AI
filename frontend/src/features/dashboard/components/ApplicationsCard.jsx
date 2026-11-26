import { Link } from "react-router-dom";
import Badge from "../../../components/ui/Badge";
import Icon from "../../../components/ui/Icon";
import { formatDate, formatDateTime } from "../../../utils/dates";
import { applicationStatus } from "../format";
import DashboardCard, { CardEmpty, ResourceState } from "./DashboardCard";

const ctaClass =
  "inline-flex items-center justify-center rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600";

function Stat({ label, value }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-2xl font-semibold tabular-nums text-slate-900">{value}</dd>
    </div>
  );
}

// The most useful next step, chosen from the backend's counts only (nothing is estimated).
export function nextApplicationStep(s) {
  if (!s) return null;
  if (s.overdue_reminders > 0) {
    return { text: `${s.overdue_reminders} overdue reminder${s.overdue_reminders === 1 ? "" : "s"} to review`, to: "/applications?tab=reminders", tone: "danger" };
  }
  const next = s.next_interviews?.[0];
  if (next) return { text: `Prepare for your interview with ${next.company_name}`, to: `/applications/${next.application_id}`, tone: "warning" };
  if (s.pending_reminders > 0) {
    return { text: `${s.pending_reminders} pending reminder${s.pending_reminders === 1 ? "" : "s"}`, to: "/applications?tab=reminders", tone: "info" };
  }
  if (s.saved_internships > 0 && s.total_applications === 0) return { text: "Apply to the internships you saved", to: "/applications?tab=saved", tone: "info" };
  return null;
}
const STEP_TONE = { danger: "bg-red-50 text-red-800", warning: "bg-amber-50 text-amber-900", info: "bg-brand-50 text-brand-800" };

// Application tracking: totals from GET /applications/dashboard and the latest applications.
export default function ApplicationsCard({ summary, recent }) {
  return (
    <DashboardCard title="Applications" icon="briefcase" link="/applications">
      <div className="flex flex-1 flex-col gap-5">
        <ResourceState resource={summary} label="application totals" lines={2}>
          {(s) => {
            const step = nextApplicationStep(s);
            return (
            <div className="flex flex-col gap-3">
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Applications" value={s.total_applications} />
                <Stat label="Submitted" value={s.submitted_applications} />
                <Stat label="Upcoming interviews" value={s.upcoming_interviews} />
                <Stat label="Offers" value={s.selected} />
              </dl>
              {s.next_interviews?.[0] && (
                <Link
                  to={`/applications/${s.next_interviews[0].application_id}`}
                  className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 hover:bg-amber-100"
                >
                  <Icon name="calendar" className="h-4 w-4 shrink-0" />
                  <span>
                    Next interview: <span className="font-medium">{s.next_interviews[0].company_name}</span> —{" "}
                    {s.next_interviews[0].title}, {formatDateTime(s.next_interviews[0].scheduled_at)}
                  </span>
                </Link>
              )}
              {step && step.to !== `/applications/${s.next_interviews?.[0]?.application_id}` && (
                <Link to={step.to} className={`rounded-lg px-3 py-2 text-sm font-medium hover:underline ${STEP_TONE[step.tone]}`}>
                  Next step: {step.text}
                </Link>
              )}
            </div>
            );
          }}
        </ResourceState>

        <div className="flex flex-1 flex-col">
          <h3 className="mb-2 text-sm font-medium text-slate-700">Recent applications</h3>
          <ResourceState resource={recent} label="recent applications" lines={3}>
            {(data) => {
              const items = data?.items || [];
              if (!items.length) {
                return (
                  <CardEmpty
                    title="No applications yet"
                    message="Track internships you apply to and follow their status here."
                    action={
                      <Link to="/internships" className={ctaClass}>
                        Browse internships
                      </Link>
                    }
                  />
                );
              }
              return (
                <ul className="divide-y divide-slate-100" aria-label="Recent applications">
                  {items.map((a) => {
                    const st = applicationStatus(a.status);
                    return (
                      <li key={a.application_id} className="flex items-center justify-between gap-3 py-2.5">
                        <div className="min-w-0">
                          <Link to={`/applications/${a.application_id}`} className="block truncate text-sm font-medium text-slate-900 hover:underline">
                            {a.title}
                          </Link>
                          <p className="truncate text-xs text-slate-500">
                            {a.company_name} · updated {formatDate(a.updated_at)}
                          </p>
                        </div>
                        <Badge tone={st.tone}>{st.label}</Badge>
                      </li>
                    );
                  })}
                </ul>
              );
            }}
          </ResourceState>
        </div>
      </div>
    </DashboardCard>
  );
}
