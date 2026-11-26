import { Link } from "react-router-dom";
import Badge from "../../../components/ui/Badge";
import { formatDateTime } from "../../../utils/dates";
import { formatScore, scoreTone, sessionStatus } from "../../interviews/interviewFormat";
import { humanize } from "../format";
import DashboardCard, { CardEmpty, ResourceState } from "./DashboardCard";
import ScoreRing from "./ScoreRing";

const ctaClass =
  "inline-flex items-center justify-center rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600";

// Most recent session (GET /interviews/sessions, newest first). Only shown once the list has loaded.
function LatestSession({ sessions }) {
  if (sessions?.status !== "success" || !sessions.data?.length) return null;
  const s = sessions.data[0];
  const status = sessionStatus(s.status);
  return (
    <div className="rounded-lg bg-slate-50 p-2.5 text-sm">
      <p className="text-xs text-slate-500">Latest session · {formatDateTime(s.started_at)}</p>
      <Link to={`/interview-prep/sessions/${s.session_id}`} className="block truncate font-medium text-slate-900 hover:underline" title={s.title || undefined}>
        {s.title || `Session #${s.session_id}`}
      </Link>
      <span className="mt-1 flex flex-wrap gap-1.5">
        <Badge tone={status.tone}>{status.label}</Badge>
        {s.score != null ? <Badge tone={scoreTone(s.score)}>Score {formatScore(s.score)}/100</Badge> : null}
      </span>
    </div>
  );
}

// Interview practice progress (GET /interviews/progress; scores are 0-100 rubric averages).
export default function InterviewCard({ progress, sessions }) {
  return (
    <DashboardCard title="Interview preparation" icon="mic" link="/interview-prep" linkLabel="All sessions">
      <ResourceState resource={progress} label="interview progress" lines={3}>
        {(p) => {
          if (!p || p.sessions_total === 0) {
            return (
              <CardEmpty
                title="No practice sessions yet"
                message="Practise technical, project and behavioural questions generated from your resume."
                action={
                  <Link to="/interview-prep" className={ctaClass}>
                    Start practising
                  </Link>
                }
              />
            );
          }
          const categories = Object.entries(p.by_category || {}).sort((a, b) => b[1] - a[1]);
          const strongest = categories[0];
          const weakest = categories.length > 1 ? categories[categories.length - 1] : null;
          return (
            <div className="flex flex-1 flex-col gap-4">
              <div className="flex items-center gap-4">
                {p.average_score == null ? (
                  <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-full bg-slate-50 text-center text-xs text-slate-500">
                    No answers scored yet
                  </div>
                ) : (
                  <ScoreRing value={p.average_score} label="average practice score" />
                )}
                <dl className="grid flex-1 grid-cols-2 gap-2 text-sm">
                  <div>
                    <dt className="text-xs text-slate-500">Sessions completed</dt>
                    <dd className="font-semibold tabular-nums text-slate-900">
                      {p.sessions_completed}/{p.sessions_total}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">Questions answered</dt>
                    <dd className="font-semibold tabular-nums text-slate-900">{p.questions_answered}</dd>
                  </div>
                </dl>
              </div>
              <p className="text-xs text-slate-500">Average practice score across your answered questions.</p>
              <LatestSession sessions={sessions} />
              {(strongest || weakest) && (
                <ul className="flex flex-col gap-1 text-xs text-slate-600">
                  {strongest && (
                    <li>
                      Strongest: <span className="font-medium text-slate-900">{humanize(strongest[0])}</span> ({Math.round(strongest[1])}%)
                    </li>
                  )}
                  {weakest && (
                    <li>
                      Practise more: <span className="font-medium text-slate-900">{humanize(weakest[0])}</span> ({Math.round(weakest[1])}%)
                    </li>
                  )}
                </ul>
              )}
              <Link to="/interview-prep" className="mt-auto inline-flex w-fit items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
                Start a new session
              </Link>
            </div>
          );
        }}
      </ResourceState>
    </DashboardCard>
  );
}
