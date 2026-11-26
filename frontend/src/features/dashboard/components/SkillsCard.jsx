import { Link } from "react-router-dom";
import { nextRecommendation } from "../../skillGaps/gapFormat";
import DashboardCard, { CardEmpty, ResourceState } from "./DashboardCard";

function Segment({ value, total, className, label }) {
  if (!value) return null;
  return <div className={className} style={{ width: `${(value / total) * 100}%` }} title={`${label}: ${value}`} />;
}

function GapBreakdown({ gap }) {
  const s = gap.summary || {};
  const total = s.required_total || 0;
  const rows = [
    { key: "matched", label: "Have", value: s.required_matched || 0, dot: "bg-mint-500" },
    { key: "partial", label: "Partly", value: s.required_partial || 0, dot: "bg-amber-400" },
    { key: "missing", label: "Missing", value: s.required_missing || 0, dot: "bg-red-400" },
  ];
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">
        Required skills for <span className="text-slate-700">{gap.internship?.title}</span>
      </p>
      {total > 0 ? (
        <>
          <div className="mt-2 flex h-2.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
            <Segment value={rows[0].value} total={total} className="bg-mint-500" label="Have" />
            <Segment value={rows[1].value} total={total} className="bg-amber-400" label="Partly" />
            <Segment value={rows[2].value} total={total} className="bg-red-400" label="Missing" />
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600" aria-label="Required skill gap">
            {rows.map((r) => (
              <li key={r.key} className="flex items-center gap-1.5">
                <span aria-hidden="true" className={`h-2 w-2 rounded-full ${r.dot}`} />
                {r.label}: <span className="font-medium tabular-nums text-slate-900">{r.value}</span>
                <span className="sr-only"> of {total}</span>
              </li>
            ))}
          </ul>
          {gap.learning_order?.length > 0 && (
            <p className="mt-2 text-xs text-slate-600">
              Learn next: <span className="font-medium text-slate-800">{gap.learning_order.slice(0, 3).join(", ")}</span>
            </p>
          )}
        </>
      ) : (
        <p className="mt-1 text-xs text-slate-600">This internship lists no required skills.</p>
      )}
      {s.preferred_total > 0 && (
        <p className="mt-1 text-xs text-slate-600">
          Preferred skills missing: <span className="font-medium tabular-nums text-slate-900">{s.preferred_missing ?? 0}</span> of {s.preferred_total}
        </p>
      )}
      {gap.internship?.internship_id && (
        <Link to={`/skill-gaps/internships/${gap.internship.internship_id}`} className="mt-1 inline-block text-xs font-medium text-brand-700 hover:underline">
          See this skill gap
        </Link>
      )}
    </div>
  );
}

// Total parsed skills (resume) and the skill gap against the best match, plus learning-plan progress.
export default function SkillsCard({ resume, skills, best, gap, recommendations }) {
  if (!resume || resume.status !== "completed") {
    return (
      <DashboardCard title="Skills & gaps" icon="chart" link="/skill-gaps">
        <CardEmpty title="Not available yet" message="Your skills are read from your parsed resume." />
      </DashboardCard>
    );
  }

  return (
    <DashboardCard title="Skills & gaps" icon="chart" link="/skill-gaps">
      <div className="flex flex-1 flex-col gap-4">
        <ResourceState resource={skills} label="your skills" lines={1}>
          {(data) => {
            const list = data?.skills || [];
            return (
              <div>
                <p className="flex items-baseline gap-2">
                  <span className="text-3xl font-semibold tabular-nums text-slate-900">{list.length}</span>
                  <span className="text-sm text-slate-600">skills recognised on your resume</span>
                </p>
                {list.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Your skills">
                    {list.slice(0, 6).map((s) => (
                      <li key={s.skill_id} className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700">
                        {s.name}
                      </li>
                    ))}
                    {list.length > 6 && <li className="px-1 text-xs text-slate-500">+{list.length - 6} more</li>}
                  </ul>
                )}
              </div>
            );
          }}
        </ResourceState>

        {best ? (
          <ResourceState resource={gap} label="your skill gap" lines={2}>
            {(data) => <GapBreakdown gap={data} />}
          </ResourceState>
        ) : (
          <p className="text-xs text-slate-500">Run matching to see the skill gap for your best match.</p>
        )}

        <ResourceState resource={recommendations} label="your learning plan" lines={1}>
          {(items) => {
            const list = (items || []).filter((r) => r.status !== "dismissed");
            if (!list.length) return <p className="text-xs text-slate-500">No learning plan yet.</p>;
            const count = (status) => list.filter((r) => r.status === status).length;
            const next = nextRecommendation(list);
            return (
              <div className="mt-auto flex flex-col gap-1.5">
                {next && (
                  <p className="rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-900">
                    Next to learn: <span className="font-semibold">{next.skill}</span>
                    {next.status === "in_progress" ? " (in progress)" : ""}
                    {next.priority_score != null && <span className="text-brand-700"> · priority {Math.round(next.priority_score)}/100</span>}
                  </p>
                )}
                <p className="text-xs text-slate-600">
                  Learning plan: <span className="font-medium text-slate-900">{count("completed")}</span> done ·{" "}
                  <span className="font-medium text-slate-900">{count("in_progress")}</span> in progress ·{" "}
                  <span className="font-medium text-slate-900">{count("pending")}</span> to start
                </p>
              </div>
            );
          }}
        </ResourceState>
      </div>
    </DashboardCard>
  );
}
