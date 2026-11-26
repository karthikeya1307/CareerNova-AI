import Badge from "../../components/ui/Badge";
import { safeExternalUrl } from "../resumes/resumeData";

// backend/services/job_insights.py (insights-v1)
export const CATEGORY = {
  apply_now: { label: "Apply Now", tone: "success" },
  improve: { label: "Apply After Improvement", tone: "warning" },
  long_term: { label: "Long-Term Target", tone: "neutral" },
};
const ELIGIBILITY_TONE = { eligible: "success", open: "success", check: "warning", unknown: "neutral", not_eligible: "danger", closed: "danger" };

export function CategoryBadge({ insights }) {
  if (!insights) return null;
  const c = CATEGORY[insights.category] || { label: insights.category_label, tone: "neutral" };
  return <Badge tone={c.tone}>{c.label}</Badge>;
}

function Metric({ label, value, hint }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-slate-900">{value}</dd>
      {hint && <dd className="text-xs text-slate-500">{hint}</dd>}
    </div>
  );
}

function Chips({ title, items, tone }) {
  if (!items?.length) return null;
  const cls = { good: "bg-mint-50 text-mint-800", partial: "bg-sky-50 text-sky-800", bad: "bg-amber-50 text-amber-800" }[tone];
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label={title}>
        {items.map((s) => (
          <li key={s.skill} className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
            {s.skill}
            {s.importance === "preferred" && <span className="opacity-70"> (preferred)</span>}
            {s.related?.length ? <span className="opacity-70"> ~ {s.related.join(", ")}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Skill Match, Eligibility, Application Readiness, skills, reasons, improvements and the link for one job.
export default function JobInsights({ insights }) {
  if (!insights) return null;
  const url = safeExternalUrl(insights.application_url);
  const elig = insights.eligibility || {};
  return (
    <div className="flex flex-col gap-4" aria-label="Job insights">
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Metric label="Skill Match" value={insights.skill_match == null ? "—" : `${insights.skill_match}%`} hint={insights.skill_match == null ? "No skills listed" : null} />
        <div className="rounded-lg bg-slate-50 px-3 py-2">
          <dt className="text-xs text-slate-500">Eligibility</dt>
          <dd className="mt-1">
            <Badge tone={ELIGIBILITY_TONE[elig.status] || "neutral"}>{elig.label}</Badge>
          </dd>
          {elig.requirement && <dd className="mt-1 text-xs text-slate-500">Requires: {elig.requirement}</dd>}
        </div>
        <Metric label="Application Readiness" value={`${insights.application_readiness}%`} hint="Skills, resume readiness and eligibility" />
      </dl>
      <div className="flex flex-col gap-3">
        <Chips title="Matched skills" items={insights.matched_skills} tone="good" />
        <Chips title="Partially matched skills" items={insights.partial_skills} tone="partial" />
        <Chips title="Not found in your resume" items={insights.missing_skills} tone="bad" />
        {insights.missing_skills?.length > 0 && (
          <p className="text-xs text-slate-500">Not found in your resume does not mean you lack the skill — if you have it, show it in a project or experience entry.</p>
        )}
      </div>
      {insights.relevant_experience?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">Where your resume shows these skills</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-sm text-slate-700" aria-label="Relevant projects and experience">
            {insights.relevant_experience.map((e) => (
              <li key={e.skill}>
                <span className="font-medium">{e.skill}</span>: {e.where.join(" · ")}
              </li>
            ))}
          </ul>
          {insights.listed_only_skills?.length > 0 && (
            <p className="mt-1 text-xs text-slate-500">Only in your skills list (no project shows them yet): {insights.listed_only_skills.join(", ")}</p>
          )}
        </div>
      )}
      {insights.reasons?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">Why this job</p>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
            {insights.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {insights.improvements?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">How to improve your chances</p>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
            {insights.improvements.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-brand-700 hover:underline">
            Open application page
          </a>
        ) : (
          <span>No application link provided</span>
        )}
        <span>Source: {insights.source === "dataset" ? "curated dataset (sample listings)" : insights.source || "unknown"}</span>
      </p>
      <p className="text-xs text-slate-400">Guidance based on your resume and the posting; it does not guarantee an interview.</p>
    </div>
  );
}
