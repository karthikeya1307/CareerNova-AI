import { humanize } from "../../dashboard/format";

// Renders a backend learning plan ({ curated, level, estimated_hours, prerequisites,
// missing_prerequisites, topics, note }). Only fields the backend supplies are shown; the backend
// provides no resource links, so none are displayed.
export default function LearningPlan({ plan }) {
  if (!plan) return <p className="text-xs text-slate-500">No learning plan was provided for this skill.</p>;
  const facts = [
    plan.level ? ["Level", humanize(plan.level)] : null,
    plan.estimated_hours != null ? ["Estimated effort", `About ${plan.estimated_hours} hours`] : null,
  ].filter(Boolean);

  return (
    <div className="flex flex-col gap-3 text-sm">
      {facts.length > 0 && (
        <dl className="flex flex-wrap gap-x-6 gap-y-1">
          {facts.map(([label, value]) => (
            <div key={label} className="flex gap-1.5">
              <dt className="text-slate-500">{label}:</dt>
              <dd className="font-medium text-slate-800">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {plan.missing_prerequisites?.length > 0 && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Learn first: <span className="font-medium">{plan.missing_prerequisites.join(", ")}</span>
        </p>
      )}
      {plan.prerequisites?.length > 0 && (
        <p className="text-xs text-slate-600">
          Prerequisites: <span className="font-medium text-slate-800">{plan.prerequisites.join(", ")}</span>
        </p>
      )}
      {plan.topics?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">{plan.curated === false ? "General outline" : "Topics, in order"}</p>
          <ol className="mt-1 list-inside list-decimal text-slate-700">
            {plan.topics.map((topic, i) => (
              <li key={i}>{topic}</li>
            ))}
          </ol>
        </div>
      )}
      {plan.curated === false && (
        <p className="text-xs text-slate-500">No curated plan exists for this skill yet, so this is a general outline without a time estimate.</p>
      )}
      {plan.note && <p className="text-xs text-slate-600">{plan.note}</p>}
    </div>
  );
}
