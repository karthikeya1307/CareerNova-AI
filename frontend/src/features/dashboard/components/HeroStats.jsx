import { Link } from "react-router-dom";
import Icon from "../../../components/ui/Icon";

// Four headline numbers in the dashboard hero. Each comes straight from a backend response;
// while loading it shows a placeholder, and without data it shows "—" with the reason.
function Stat({ icon, label, value, hint, to, loading }) {
  const body = (
    <>
      <span className="flex items-center gap-2 text-xs font-medium text-slate-300">
        <Icon name={icon} className="h-4 w-4 text-brand-300" />
        {label}
      </span>
      {loading ? (
        <span aria-hidden="true" className="mt-2 block h-7 w-16 animate-pulse rounded-md bg-white/10" />
      ) : (
        <span className="mt-1.5 block font-display text-2xl font-bold tabular-nums text-white">{value}</span>
      )}
      <span className="mt-0.5 line-clamp-2 block text-xs text-slate-400">{loading ? "Loading…" : hint}</span>
    </>
  );
  const cls =
    "block min-w-0 rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm transition hover:border-white/20 hover:bg-white/[0.09] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white";
  return (
    <li className="min-w-0">
      {to ? (
        <Link to={to} className={cls}>
          {body}
        </Link>
      ) : (
        <div className={cls}>{body}</div>
      )}
    </li>
  );
}

// "idle" means the request is disabled (useApiResource), so only "loading" shows a placeholder.
const loadingOf = (resource) => resource.status === "loading";

export default function HeroStats({ readiness, resumeId, best, matches, appSummary, progress }) {
  const r = readiness.status === "success" ? readiness.data : null;
  const apps = appSummary.status === "success" ? appSummary.data : null;
  const p = progress.status === "success" ? progress.data : null;

  return (
    <ul aria-label="Your progress at a glance" className="mt-7 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat
        icon="document"
        label="Resume readiness"
        value={r ? `${Math.round(r.score)}/100` : "—"}
        hint={
          r
            ? `${r.label}${r.version ? ` · V${r.version} ${r.version_label || r.filename || ""}`.trimEnd() : ""}`
            : resumeId
              ? readiness.status === "error" ? "Not available" : "—"
              : "No parsed resume yet"
        }
        to={resumeId ? `/resumes/${resumeId}` : "/resumes"}
        loading={Boolean(resumeId) && (readiness.status === "loading" || readiness.status === "idle")}
      />
      <Stat
        icon="target"
        label="Best match"
        value={best ? `${Math.round(best.score)}%` : "—"}
        hint={best ? best.internship.title : resumeId ? "Run matching to see it" : "Needs a parsed resume"}
        to="/matches"
        loading={Boolean(resumeId) && (matches.status === "loading" || matches.status === "idle")}
      />
      <Stat
        icon="clipboard"
        label="Applications"
        value={apps ? apps.total_applications : "—"}
        hint={apps ? `${apps.upcoming_interviews} upcoming interview${apps.upcoming_interviews === 1 ? "" : "s"}` : "Not available"}
        to="/applications"
        loading={loadingOf(appSummary)}
      />
      <Stat
        icon="mic"
        label="Interview practice"
        value={p?.average_score != null ? `${Math.round(p.average_score)}/100` : "—"}
        hint={p ? `${p.questions_answered} question${p.questions_answered === 1 ? "" : "s"} answered` : "Not available"}
        to="/interview-prep"
        loading={loadingOf(progress)}
      />
    </ul>
  );
}
