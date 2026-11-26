import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getQuestionBankInfo, listSessions } from "../../api/interviews";
import Badge from "../../components/ui/Badge";
import Icon from "../../components/ui/Icon";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import StartSessionForm from "./components/StartSessionForm";
import { formatScore, isOpen, modeLabel, scoreTone, sessionStatus } from "./interviewFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";
const FILTERS = [
  { id: "", label: "All" },
  { id: "in_progress", label: "In progress" },
  { id: "started", label: "Not started" },
  { id: "completed", label: "Completed" },
];

function SessionHistory({ filter, onFilter }) {
  const sessions = useApiResource(() => listSessions({ status: filter || undefined }), `sessions:${filter}`);
  return (
    <section aria-labelledby="sessions-title" className={panel}>
      <div className="mb-4 flex flex-col gap-3">
        <h2 id="sessions-title" className="text-base font-semibold text-slate-900">
          Your sessions
        </h2>
        <div role="group" aria-label="Filter sessions" className="flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
          {FILTERS.map((f) => (
            <button
              key={f.id || "all"}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => onFilter(f.id)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                filter === f.id ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {sessions.status === "loading" || sessions.status === "idle" ? (
        <CardSkeleton label="your sessions" lines={3} />
      ) : sessions.status === "error" ? (
        <CardError error={sessions.error} onRetry={sessions.reload} label="your sessions" />
      ) : !sessions.data.length ? (
        <CardEmpty
          title={filter ? "No sessions with this status" : "No sessions yet"}
          message={filter ? "Try another filter." : "Start your first practice session with the form."}
        />
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Interview sessions">
          {sessions.data.map((s) => {
            const status = sessionStatus(s.status);
            return (
              <li key={s.session_id}>
                <Link
                  to={`/interview-prep/sessions/${s.session_id}`}
                  className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-slate-900">{s.title || `Session #${s.session_id}`}</span>
                    <span className="block text-xs text-slate-500">
                      Started {formatDateTime(s.started_at)}
                      {s.completed_at ? ` · completed ${formatDateTime(s.completed_at)}` : ""}
                    </span>
                  </span>
                  <span className="flex flex-wrap gap-1.5">
                    <Badge tone={status.tone}>{status.label}</Badge>
                    <Badge>{modeLabel(s.mode)}</Badge>
                    <Badge>
                      {s.answered_count}/{s.total_questions ?? "?"} answered
                    </Badge>
                    {s.score != null ? <Badge tone={scoreTone(s.score)}>Score {formatScore(s.score)}/100</Badge> : null}
                    {isOpen(s.status) ? <Badge tone="info">Continue</Badge> : null}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function BankInfo() {
  const bank = useApiResource(getQuestionBankInfo, "question-bank");
  if (bank.status !== "success" || !bank.data) return null; // informational only
  const b = bank.data;
  return (
    <p className="text-xs text-slate-500">
      Question bank: {b.technical_questions} technical questions across {b.skills_covered} skills
      {b.by_difficulty ? ` (${Object.entries(b.by_difficulty).map(([d, n]) => `${n} ${d}`).join(", ")})` : ""} and {b.behavioral_questions} behavioural questions.
    </p>
  );
}

// Interview preparation: start a session and open previous ones.
// Query: ?internship=ID&resume=ID pre-fill the form; ?show= filters the history.
export default function InterviewPrepPage() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.some((f) => f.id === params.get("show")) ? params.get("show") || "" : "";

  useEffect(() => {
    const previous = document.title;
    document.title = "Interview preparation · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const setFilter = (id) => {
    const next = new URLSearchParams(params);
    if (id) next.set("show", id);
    else next.delete("show");
    setParams(next, { replace: true });
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Interview preparation</h1>
        <p className="mt-1 text-sm text-slate-600">
          Practise technical, project, behavioural and internship-specific questions generated from your resume. Write your answer, get rubric-based
          feedback, and finish the session for a summary.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <section aria-labelledby="start-title" className={`${panel} min-w-0`}>
          <h2 id="start-title" className="mb-1 flex items-center gap-2 text-base font-semibold text-slate-900">
            <Icon name="mic" className="h-5 w-5 text-brand-600" />
            Start a session
          </h2>
          <ol className="mb-4 list-decimal pl-5 text-xs text-slate-600">
            <li>Choose your resume and, optionally, the internship you're preparing for.</li>
            <li>Pick practice or mock mode, difficulty and how many questions of each kind.</li>
            <li>Answer at your own pace; you can retry questions until you finish the session.</li>
          </ol>
          <StartSessionForm
            key={`${params.get("internship")}:${params.get("resume")}:${params.get("role")}`}
            initialInternshipId={params.get("internship")}
            initialResumeId={params.get("resume")}
            initialRole={params.get("role")}
            initialMode={params.get("mode")}
          />
          <div className="mt-4">
            <BankInfo />
          </div>
        </section>
        <div className="min-w-0 self-start">
          <SessionHistory filter={filter} onFilter={setFilter} />
        </div>
      </div>
    </div>
  );
}
