import Badge from "../../../components/ui/Badge";
import { humanize } from "../../dashboard/format";
import { CAP_LABEL, FEEDBACK_SOURCE, formatScore, scoreTone, STAR_LABEL } from "../interviewFormat";

function List({ title, items, tone = "slate", label }) {
  if (!items?.length) return null;
  const colour = { slate: "text-slate-700", green: "text-mint-800", amber: "text-amber-900", red: "text-red-800" }[tone];
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <ul className={`mt-1 list-disc space-y-0.5 pl-5 text-sm ${colour}`} aria-label={label || title}>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

// Shows exactly what the backend returned for one evaluated answer (AnswerOut, or the latest
// evaluation stored on a QuestionOut). Fields the backend did not send are not shown.
export default function EvaluationView({ score, feedback, feedbackSource, evaluation }) {
  const e = evaluation || {};
  const label = e.label;
  const star = e.star && typeof e.star === "object" ? Object.entries(e.star) : [];
  const components = e.components && typeof e.components === "object" ? Object.entries(e.components) : [];
  return (
    <section aria-label="Evaluation" className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-lg font-semibold tabular-nums text-slate-900">
          {formatScore(score)}
          <span className="text-sm font-normal text-slate-500">/100</span>
        </p>
        {label && <Badge tone={scoreTone(score)}>{label}</Badge>}
        {feedbackSource && <Badge>{FEEDBACK_SOURCE[feedbackSource] || feedbackSource}</Badge>}
        {e.over_time_limit === true && <Badge tone="warning">Over the time limit</Badge>}
      </div>

      {feedback && <p className="whitespace-pre-line text-sm text-slate-700">{feedback}</p>}

      {star.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">STAR structure</p>
          <ul className="mt-1 flex flex-wrap gap-1.5" aria-label="STAR structure">
            {star.map(([part, found]) => (
              <li key={part}>
                <Badge tone={found ? "success" : "warning"}>
                  {STAR_LABEL[part] || humanize(part)}: {found ? "found" : "missing"}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      <List title="Strengths: key points covered" label="Key points covered" tone="green" items={(e.covered_points || []).map((p) => p.point)} />
      <List
        title="To improve: key points missed"
        label="Key points missed"
        tone="amber"
        items={(e.missed_points || []).filter((p) => p.reason !== "incorrect_statement").map((p) => p.point)}
      />
      <List
        title="Possible mistakes"
        tone="red"
        items={(e.incorrect_statements || []).map((s) => `${s.point}: ${(s.corrections || []).join(" ")}`)}
      />
      <List title="Tips" items={e.tips} />
      <List title="Check your claims" tone="amber" items={e.advisories} />
      <List title="Score caps" items={(e.caps_applied || []).map((c) => CAP_LABEL[c] || humanize(c))} />
      <List title="AI feedback notes" tone="amber" items={(e.llm_warnings || []).map((w) => w.detail || w.code)} />

      {(components.length > 0 || e.word_count != null || e.method) && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs font-medium text-slate-600">Evaluation details</summary>
          <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {components.map(([key, value]) => (
              <div key={key} className="flex justify-between gap-2">
                <dt className="text-slate-500">{humanize(key)}</dt>
                <dd className="tabular-nums text-slate-800">{typeof value === "number" ? `${Math.round(value * 100)}%` : String(value)}</dd>
              </div>
            ))}
            {e.word_count != null && (
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Words</dt>
                <dd className="tabular-nums text-slate-800">{e.word_count}</dd>
              </div>
            )}
            {e.method && (
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Method</dt>
                <dd className="text-slate-800">{e.method}</dd>
              </div>
            )}
          </dl>
        </details>
      )}
    </section>
  );
}
