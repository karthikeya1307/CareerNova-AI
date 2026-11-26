import Badge from "../../components/ui/Badge";
import ScoreRing from "../dashboard/components/ScoreRing";
import { humanize } from "../dashboard/format";

// Score component names from backend/schemas/match_schema.py ScoreComponent.
const COMPONENT_LABELS = { skills: "Skills", semantic: "Semantic similarity", education: "Education", location: "Location" };
const STATUS = {
  assessed: { label: "Assessed", tone: "success" },
  unknown: { label: "Unknown", tone: "warning" },
  not_stated: { label: "Not stated", tone: "neutral" },
  unavailable: { label: "Unavailable", tone: "neutral" },
};

function SkillList({ title, items, tone }) {
  if (!items?.length) return null;
  const cls = tone === "good" ? "bg-mint-50 text-mint-800" : tone === "bad" ? "bg-amber-50 text-amber-800" : "bg-slate-100 text-slate-700";
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label={title}>
        {items.map((s) => (
          <li key={s} className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
            {s}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Explains one MatchItem exactly as the backend computed it (score, components, skills, explanations).
export default function MatchBreakdown({ match, compact = false }) {
  const coverage = match.required_skill_coverage;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-4">
        <ScoreRing value={match.score} label="compatibility" />
        <div className="min-w-0">
          <Badge tone="info">{match.label}</Badge>
          <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <dt className="text-slate-500">Compatibility</dt>
            <dd className="font-semibold tabular-nums text-slate-900">{Math.round(match.score)}%</dd>
            <dt className="text-slate-500">Required skills covered</dt>
            <dd className="font-semibold tabular-nums text-slate-900">{coverage == null ? "—" : `${Math.round(coverage * 100)}%`}</dd>
            <dt className="text-slate-500">Data completeness</dt>
            <dd className="font-semibold tabular-nums text-slate-900">{Math.round((match.data_completeness ?? 0) * 100)}%</dd>
          </dl>
        </div>
      </div>

      {!compact && match.components?.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-slate-500">How the score was built</p>
          <ul className="flex flex-col gap-3" aria-label="Score components">
            {match.components.map((c) => {
              const status = STATUS[c.status] || { label: humanize(c.status), tone: "neutral" };
              return (
                <li key={c.name}>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="font-medium text-slate-800">
                      {COMPONENT_LABELS[c.name] || humanize(c.name)}
                      <span className="ml-2 text-xs font-normal text-slate-500">weight {Math.round(c.weight * 100)}%</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge tone={status.tone}>{status.label}</Badge>
                      <span className="tabular-nums text-slate-900">{Math.round(c.score * 100)}%</span>
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
                    <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.round(c.score * 100)}%` }} />
                  </div>
                  {c.detail && <p className="mt-1 text-xs text-slate-600">{c.detail}</p>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SkillList title="Required skills you have" items={match.matched_required_skills} tone="good" />
        <SkillList title="Required skills missing" items={match.missing_required_skills} tone="bad" />
        {!compact && <SkillList title="Preferred skills you have" items={match.matched_preferred_skills} tone="good" />}
        {!compact && <SkillList title="Preferred skills missing" items={match.missing_preferred_skills} tone="neutral" />}
      </div>

      {!compact && match.explanation?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">Why this score</p>
          <ul className="mt-1.5 list-inside list-disc text-sm text-slate-700">
            {match.explanation.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {!compact && (match.caps_applied?.length > 0 || match.missing_information?.length > 0) && (
        <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {match.caps_applied?.length > 0 && <p>Score limits applied: {match.caps_applied.map(humanize).join(", ")}.</p>}
          {match.missing_information?.length > 0 && <p>Missing information: {match.missing_information.map(humanize).join(", ")}.</p>}
        </div>
      )}
    </div>
  );
}
