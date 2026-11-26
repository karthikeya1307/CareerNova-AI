import { useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { errorMessage } from "../../api/errors";
import { WORK_MODES } from "../../api/internships";
import { getLatestMatches, getMatchHistory, getMatchRun, MATCH_MAX_K, runMatching } from "../../api/matches";
import { listResumes } from "../../api/resumes";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import Input from "../../components/ui/Input";
import Select from "../../components/ui/Select";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import { latestParsed } from "../resumes/resumeData";
import ExploreJobs from "./ExploreJobs";
import JobInsights, { CategoryBadge } from "./JobInsights";
import MatchBreakdown from "./MatchBreakdown";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";
const K_OPTIONS = [5, 10, 20, MATCH_MAX_K];

export function orderedResults(run) {
  return [...(run?.results || [])].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || b.score - a.score);
}

function ResultItem({ item }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const it = item.internship;
  return (
    <li className="rounded-xl border border-slate-200/80 bg-white">
      <div className="flex flex-wrap items-center gap-3 p-4">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-700" aria-label={`Rank ${item.rank ?? "—"}`}>
          {item.rank ?? "—"}
        </span>
        <div className="min-w-0 flex-1">
          <Link to={`/internships/${it.internship_id}`} className="font-medium text-slate-900 hover:text-brand-700 hover:underline">
            {it.title}
          </Link>
          <p className="truncate text-xs text-slate-500">{[it.company, it.location, it.work_mode].filter(Boolean).join(" · ")}</p>
        </div>
        <div className="flex items-center gap-2">
          <CategoryBadge insights={item.insights} />
          <Badge tone="info">{item.label}</Badge>
          <span className="w-12 text-right text-lg font-semibold tabular-nums text-slate-900">{Math.round(item.score)}%</span>
        </div>
        <Button variant="ghost" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)} className="px-2 py-1 text-xs">
          {open ? "Hide breakdown" : "Show breakdown"}
          <span className="sr-only"> for {it.title}</span>
          <Icon name="chevronDown" className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </Button>
      </div>
      {open && (
        <div id={panelId} className="flex flex-col gap-5 border-t border-slate-100 p-4">
          <JobInsights insights={item.insights} />
          <MatchBreakdown match={item} />
          <Link to={`/skill-gaps/internships/${it.internship_id}`} className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
            <Icon name="chart" className="h-4 w-4" />
            View skill gap and learning plan<span className="sr-only"> for {it.title}</span>
          </Link>
        </div>
      )}
    </li>
  );
}

function RunForm({ resumeId, onRun }) {
  const [k, setK] = useState("10");
  const [mode, setMode] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    const loc = location.trim();
    if (loc && (loc.length < 2 || loc.length > 150)) {
      setError("Location must be 2 to 150 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onRun(await runMatching(resumeId, { k: Number(k), work_mode: mode || undefined, location: loc || undefined }));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3" aria-label="Run matching">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Select label="Results" value={k} onChange={(e) => setK(e.target.value)} options={K_OPTIONS.map((n) => ({ value: String(n), label: `Top ${n}` }))} />
        <Select label="Work mode" value={mode} onChange={(e) => setMode(e.target.value)} options={[{ value: "", label: "Any" }, ...WORK_MODES.map((m) => ({ value: m, label: m }))]} />
        <Input label="Location (optional)" value={location} maxLength={150} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Bengaluru" />
      </div>
      <div>
        <Button type="submit" loading={busy}>
          {!busy && <Icon name="sparkles" className="h-4 w-4" />}
          {busy ? "Matching…" : "Run matching"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
    </form>
  );
}

// RAG-based matching results: the matching engine ranks active internships against the latest parsed
// resume (skills, semantic similarity from the embedding index, education, location).
export default function MatchesPage() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run");
  const resumes = useApiResource(listResumes, "resumes");
  const resume = resumes.status === "success" ? latestParsed(resumes.data) : null;
  const rid = resume?.resume_id ?? null;

  const latest = useApiResource(() => getLatestMatches(rid), rid, { enabled: Boolean(rid) && !runId });
  const chosen = useApiResource(() => getMatchRun(runId), runId, { enabled: Boolean(rid) && Boolean(runId) });
  const history = useApiResource(() => getMatchHistory(rid), rid, { enabled: Boolean(rid) });
  const current = runId ? chosen : latest;

  useEffect(() => {
    const previous = document.title;
    document.title = "Matches · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const onRun = (run) => {
    setParams({});
    latest.setData(run);
    history.reload();
  };

  let results;
  if (current.status === "loading" || current.status === "idle") results = <CardSkeleton label="your matches" lines={5} />;
  else if (current.status === "error") {
    results =
      runId && current.error.status === 404 ? (
        <CardEmpty title="Match run not found" action={<Button variant="secondary" onClick={() => setParams({})}>Show latest run</Button>} />
      ) : (
        <CardError error={current.error} onRetry={current.reload} label="your matches" />
      );
  } else if (!current.data) {
    results = <CardEmpty title="No matches yet" message="Run matching to rank active internships against your resume." />;
  } else {
    const run = current.data;
    const items = orderedResults(run);
    results = (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
          <span>Run {formatDateTime(run.created_at)}</span>
          <span>{run.candidates_considered} internships considered</span>
          {Object.entries(run.filters || {}).filter(([, v]) => v !== null && v !== undefined && v !== "").map(([key, value]) => (
            <span key={key}>
              {key.replace(/_/g, " ")}: <span className="font-medium text-slate-700">{String(value)}</span>
            </span>
          ))}
          {runId && <Badge tone="warning">Earlier run</Badge>}
        </div>
        {!run.semantic_available && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Semantic similarity was unavailable for this run, so scores rely on skills, education and location only.
          </p>
        )}
        {items.length ? (
          <ol className="flex flex-col gap-3" aria-label="Match results">
            {items.map((item) => (
              <ResultItem key={item.internship.internship_id} item={item} />
            ))}
          </ol>
        ) : (
          <CardEmpty title="No internships matched" message="Try a different work mode or location, or update your resume." />
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Matches</h1>
        <p className="mt-1 text-sm text-slate-600">
          <strong>For my resume</strong> ranks internships by the evidence in your latest parsed resume. <strong>Explore any job</strong> lets you browse every
          open opportunity and still see your skill match, eligibility and readiness for each.
        </p>
      </header>

      <div role="tablist" aria-label="Matching mode" className="flex gap-2">
        {[
          ["resume", "For my resume"],
          ["explore", "Explore any job"],
        ].map(([value, label]) => {
          const active = (params.get("mode") === "explore" ? "explore" : "resume") === value;
          return (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setParams(value === "explore" ? { mode: "explore" } : {})}
              className={`rounded-full border px-4 py-1.5 text-sm font-medium ${active ? "border-brand-400 bg-brand-50 text-brand-800" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {params.get("mode") === "explore" ? (
        <section aria-label="Explore opportunities" className={panel}>
          {resumes.status === "loading" || resumes.status === "idle" ? (
            <CardSkeleton label="your resume" lines={2} />
          ) : (
            <ExploreJobs resumeId={rid || null} />
          )}
        </section>
      ) : resumes.status === "loading" || resumes.status === "idle" ? (
        <div className={panel}>
          <CardSkeleton label="your resume" lines={2} />
        </div>
      ) : resumes.status === "error" ? (
        <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />
      ) : !resume ? (
        <CardEmpty
          title="Upload a resume to get matches"
          message="Matching uses your latest successfully parsed resume."
          action={<Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">Go to resumes</Link>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
          <div className="flex min-w-0 flex-col gap-6">
            <section aria-labelledby="run-title" className={panel}>
              <h2 id="run-title" className="text-base font-semibold text-slate-900">
                Run matching
              </h2>
              <p className="mb-4 mt-0.5 text-sm text-slate-600">Using {resume.filename}.</p>
              <RunForm resumeId={rid} onRun={onRun} />
            </section>
            <section aria-label="Match results" className={panel}>
              {results}
            </section>
          </div>
          <aside aria-labelledby="history-title" className={`${panel} min-w-0 self-start`}>
            <h2 id="history-title" className="mb-3 text-base font-semibold text-slate-900">
              Run history
            </h2>
            {history.status === "loading" || history.status === "idle" ? (
              <CardSkeleton label="run history" lines={3} />
            ) : history.status === "error" ? (
              <CardError error={history.error} onRetry={history.reload} label="run history" />
            ) : !history.data.length ? (
              <p className="text-sm text-slate-500">No runs yet.</p>
            ) : (
              <ul className="flex flex-col gap-2" aria-label="Previous runs">
                {history.data.map((h, index) => {
                  const isCurrent = runId ? h.run_id === runId : index === 0;
                  return (
                    <li key={h.run_id}>
                      <button
                        type="button"
                        onClick={() => setParams(index === 0 ? {} : { run: h.run_id })}
                        aria-current={isCurrent ? "true" : undefined}
                        className={`w-full rounded-lg border px-3 py-2 text-left text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                          isCurrent ? "border-brand-300 bg-brand-50/60" : "border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        <span className="block font-medium text-slate-900">{formatDateTime(h.created_at)}</span>
                        <span className="block text-xs text-slate-500">
                          {h.result_count} result{h.result_count === 1 ? "" : "s"}
                          {h.top_score != null ? ` · top ${Math.round(h.top_score)}%` : ""}
                          {h.top_label ? ` (${h.top_label})` : ""}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
