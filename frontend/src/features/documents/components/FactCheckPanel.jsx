import Badge from "../../../components/ui/Badge";
import Icon from "../../../components/ui/Icon";
import { factCheckWarnings, problemLabel } from "../documentFormat";

// The backend's fact-check record for the current version:
// { checked_statements, warnings[{code, detail}], rejected_statements[{location, text, problems[]}], llm{used, accepted, rejected} }
export default function FactCheckPanel({ factCheck }) {
  if (!factCheck) {
    return <p className="text-sm text-slate-500">No fact-check record was stored for this version.</p>;
  }
  const total = factCheckWarnings(factCheck);
  const warnings = factCheck.warnings || [];
  const rejected = factCheck.rejected_statements || [];
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        {total === 0 ? (
          <Badge tone="success">No problems found</Badge>
        ) : (
          <Badge tone="warning">
            {total} item{total === 1 ? "" : "s"} to review
          </Badge>
        )}
        <span className="text-xs text-slate-500">{factCheck.checked_statements ?? 0} statements checked against your resume</span>
      </p>
      {factCheck.llm?.used && (
        <p className="text-xs text-slate-600">
          AI suggestions: {factCheck.llm.accepted} accepted, {factCheck.llm.rejected} rejected by the fact check.
        </p>
      )}
      {warnings.length > 0 && (
        <ul className="flex flex-col gap-1.5" aria-label="Fact-check warnings">
          {warnings.map((w, i) => (
            <li key={i} className="flex gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                <span className="font-medium">{problemLabel(w.code)}.</span> {w.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
      {rejected.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">Removed because they weren't supported by your resume</p>
          <ul className="mt-1.5 flex flex-col gap-1.5" aria-label="Rejected statements">
            {rejected.map((r, i) => (
              <li key={i} className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
                <p className="text-slate-500">{r.location}</p>
                <p className="mt-0.5 line-through decoration-slate-400">{r.text}</p>
                <p className="mt-0.5 text-red-700">{(r.problems || []).map((p) => `${problemLabel(p.code)}: ${p.detail}`).join("; ")}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
