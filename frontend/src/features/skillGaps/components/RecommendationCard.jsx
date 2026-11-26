import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../../../api/errors";
import { updateRecommendationStatus } from "../../../api/skillGaps";
import Badge from "../../../components/ui/Badge";
import Icon from "../../../components/ui/Icon";
import { formatDate } from "../../../utils/dates";
import { completedViaLabel, gapLevel, IMPORTANCE, statusMeta } from "../gapFormat";
import LearningPlan from "./LearningPlan";

const ACTIONS = [
  { status: "pending", label: "To do" },
  { status: "in_progress", label: "In progress" },
  { status: "completed", label: "Completed" },
  { status: "dismissed", label: "Dismiss" },
];

// One backend RecommendationItem with a persisted progress control (PATCH /skill-gaps/{id}).
export default function RecommendationCard({ rec, onUpdated, rank }) {
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const planId = useId();
  const status = statusMeta(rec.status);
  const level = gapLevel(rec.gap_level);
  const via = rec.status === "completed" ? completedViaLabel(rec.completed_via) : null;

  const change = async (next) => {
    if (saving || next === rec.status) return; // one request at a time
    setSaving(next);
    setError(null);
    try {
      onUpdated(await updateRecommendationStatus(rec.recommendation_id, next));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setSaving(null);
    }
  };

  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-base font-semibold text-slate-900">
            {rank != null && <span className="text-sm font-medium text-slate-400">#{rank}</span>}
            {rec.skill}
          </h3>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Badge tone={level.tone}>{level.label}</Badge>
            {rec.importance && <Badge>{IMPORTANCE[rec.importance] || rec.importance}</Badge>}
            {rec.category && <Badge>{rec.category.replace(/_/g, " ")}</Badge>}
          </div>
        </div>
        <div className="text-right">
          <Badge tone={status.tone}>{status.label}</Badge>
          {rec.priority_score != null && (
            <p className="mt-1 text-xs text-slate-500">
              Priority <span className="font-semibold tabular-nums text-slate-800">{Math.round(rec.priority_score)}</span>/100
            </p>
          )}
        </div>
      </header>

      {rec.recommended_action && <p className="text-sm text-slate-700">{rec.recommended_action}</p>}
      {rec.demand_count != null && (
        <p className="text-xs text-slate-500">
          Needed by {rec.demand_count} of the analysed internship{rec.demand_count === 1 ? "" : "s"}
          {rec.top_internship && (
            <>
              {" "}· e.g.{" "}
              <Link to={`/internships/${rec.top_internship.internship_id}`} className="font-medium text-brand-700 hover:underline">
                {rec.top_internship.title} at {rec.top_internship.company}
              </Link>
            </>
          )}
        </p>
      )}
      {rec.related_skills?.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-xs text-slate-600" aria-label={`Related skills for ${rec.skill}`}>
          {rec.related_skills.map((r) => (
            <li key={r.skill}>
              <span className="font-medium text-slate-800">{r.skill}</span>: {r.reason}
            </li>
          ))}
        </ul>
      )}

      <div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={planId}
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1 rounded text-sm font-medium text-brand-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
        >
          {open ? "Hide learning plan" : "Show learning plan"}
          <span className="sr-only"> for {rec.skill}</span>
          <Icon name="chevronDown" className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {open && (
          <div id={planId} className="mt-3 rounded-xl bg-slate-50 p-4">
            <LearningPlan plan={rec.learning_plan} />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2 border-t border-slate-100 pt-3">
        <div role="group" aria-label={`Progress for ${rec.skill}`} className="flex flex-wrap gap-1.5">
          {ACTIONS.map((a) => {
            const current = rec.status === a.status;
            return (
              <button
                key={a.status}
                type="button"
                aria-pressed={current}
                disabled={Boolean(saving)}
                onClick={() => change(a.status)}
                className={`rounded-md border px-3 py-1.5 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:opacity-60 ${
                  current ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {saving === a.status ? "Saving…" : a.label}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-slate-500" aria-live="polite">
          {via && `${via}. `}
          {rec.started_at && `Started ${formatDate(rec.started_at)}. `}
          {rec.completed_at && `Completed ${formatDate(rec.completed_at)}.`}
        </p>
        {error && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800">
            Couldn't update progress. {error}
          </p>
        )}
      </div>
    </article>
  );
}
