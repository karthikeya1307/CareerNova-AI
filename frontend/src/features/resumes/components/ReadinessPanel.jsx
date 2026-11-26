import { useId, useState } from "react";
import { getResumeReadiness } from "../../../api/resumes";
import Badge from "../../../components/ui/Badge";
import useApiResource from "../../../hooks/useApiResource";
import { CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";

const LABEL_TONE = { Excellent: "success", Good: "success", Fair: "warning", "Needs work": "danger" };

function CategoryRow({ category }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const pct = category.max ? Math.round((category.score / category.max) * 100) : 0;
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="w-full rounded-md text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
      >
        <span className="flex justify-between text-sm">
          <span className="text-slate-700">{category.label}</span>
          <span className="font-medium tabular-nums text-slate-900">
            {category.score}/{category.max}
          </span>
        </span>
        <span className="mt-1 block h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
          <span className={`block h-full rounded-full ${pct >= 80 ? "bg-mint-500" : pct >= 50 ? "bg-amber-400" : "bg-red-400"}`} style={{ width: `${pct}%` }} />
        </span>
      </button>
      {open && (
        <ul id={id} className="mt-2 flex flex-col gap-1 pl-1 text-xs">
          {category.points.map((p, i) => (
            <li key={i} className={p.earned ? "text-mint-800" : "text-slate-500"}>
              {p.earned ? "+" : "−"}
              {p.points} · {p.reason}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

// General Resume Readiness (backend readiness-v1). Separate from job-specific compatibility.
export default function ReadinessPanel({ resumeId, version }) {
  const report = useApiResource(() => getResumeReadiness(resumeId), `readiness:${resumeId}:${version}`);
  if ((report.status === "loading" || report.status === "idle") && !report.data) return <CardSkeleton label="resume readiness" lines={4} />;
  if (report.status === "error") return <CardError error={report.error} onRetry={report.reload} label="resume readiness" />;
  const r = report.data;
  const parsing = r.parsing || {};
  return (
    <section aria-labelledby="readiness-title" className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 id="readiness-title" className="text-sm font-semibold text-slate-900">
            Resume readiness
          </h3>
          <p className="text-xs text-slate-500">General quality of this resume, not tied to any job.</p>
          {r.version && (
            <p className="text-xs text-slate-500">
              Scored version: V{r.version} · {r.version_label || r.filename}
            </p>
          )}
        </div>
        <p className="flex items-center gap-2">
          <span className="text-3xl font-semibold tabular-nums text-slate-900" aria-label={`Readiness score ${r.score} out of 100`}>
            {r.score}
            <span className="text-base font-normal text-slate-500">/100</span>
          </span>
          <Badge tone={LABEL_TONE[r.label] || "neutral"}>{r.label}</Badge>
        </p>
      </div>
      <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2" aria-label="Score by category">
        {r.categories.map((c) => (
          <CategoryRow key={c.key} category={c} />
        ))}
      </ul>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-medium text-slate-500">Strengths</p>
          {r.strengths.length ? (
            <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
              {r.strengths.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-sm text-slate-500">None yet.</p>
          )}
        </div>
        <div>
          <p className="text-xs font-medium text-slate-500">Needs attention</p>
          {r.weaknesses.length ? (
            <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
              {r.weaknesses.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-sm text-slate-500">No weak areas.</p>
          )}
        </div>
      </div>
      {r.recommendations.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-slate-500">Recommended improvements</p>
          <ol className="mt-1 list-inside list-decimal text-sm text-slate-700" aria-label="Recommended improvements">
            {r.recommendations.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
      )}
      <div className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <p>
          Parsing confidence: <strong>{Math.round((parsing.overall_confidence || 0) * 100)}%</strong>
          {parsing.missing_core_fields?.length ? ` · Missing: ${parsing.missing_core_fields.join(", ")}` : ""}
        </p>
        {parsing.missing_recommended_sections?.length > 0 && <p>Not found (recommended): {parsing.missing_recommended_sections.join(", ")}</p>}
        {parsing.warnings?.length > 0 && (
          <ul className="mt-1 list-inside list-disc" aria-label="Parsing warnings">
            {parsing.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
        <p className="mt-1">If something was read incorrectly, use “Edit details” to correct it.</p>
      </div>
      <div className="mt-3 text-xs text-slate-500" aria-label="How this score is calculated">
        <p>
          Calculated from this resume&apos;s extracted content only (contact, sections, skills and the evidence for them,
          dates, formatting). Your profile details don&apos;t change it. It is recalculated whenever you correct the
          extracted details or re-parse this version.
        </p>
        {r.same_content_as?.length > 0 && (
          <p className="mt-1 font-medium text-amber-800">
            {r.same_content_as.map((s) => `V${s.version}`).join(", ")}{" "}
            {r.same_content_as.length === 1 ? "has" : "have"} exactly the same extracted content as this version, so the
            score is the same. Uploading the same resume again doesn&apos;t change the score; improving its content does.
          </p>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-400">{r.disclaimer}</p>
    </section>
  );
}
