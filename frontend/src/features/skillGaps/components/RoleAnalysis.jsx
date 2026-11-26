import { getRoleAnalysis } from "../../../api/skillGaps";
import Badge from "../../../components/ui/Badge";
import Select from "../../../components/ui/Select";
import useApiResource from "../../../hooks/useApiResource";
import { CardEmpty, CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";
const STATUS = {
  demonstrated: { label: "Shown in a project/experience", tone: "success" },
  listed: { label: "Listed only", tone: "warning" },
  not_found: { label: "Not found in resume", tone: "neutral" },
};
const PRIORITY_TONE = { high: "danger", medium: "warning", low: "neutral" };

function Bar({ value, total, label }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div>
      <p className="flex justify-between text-xs text-slate-600">
        <span>{label}</span>
        <span className="tabular-nums">
          {value} of {total}
        </span>
      </p>
      <span className="mt-1 block h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
        <span className="block h-full rounded-full bg-brand-500" style={{ width: `${pct}%` }} />
      </span>
    </div>
  );
}

function SkillGroups({ groups }) {
  if (!groups?.length) return <p className="text-sm text-slate-500">No technical skills were found in this resume.</p>;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {groups.map((g) => (
        <div key={g.group} className="rounded-xl bg-slate-50 p-3">
          <p className="text-xs font-semibold text-slate-700">{g.group}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={`${g.group} skills`}>
            {g.skills.map((s) => (
              <li key={s.skill} title={s.where?.length ? `Shown in: ${s.where.join(", ")}` : STATUS[s.status].label}>
                <Badge tone={STATUS[s.status].tone}>
                  {s.skill}
                  <span className="sr-only"> – {STATUS[s.status].label}</span>
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function GapCard({ gap }) {
  return (
    <article className="flex h-full flex-col gap-2 rounded-xl border border-slate-200 p-4" aria-label={`Gap: ${gap.skill}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-slate-900">{gap.skill}</h4>
        <Badge tone={PRIORITY_TONE[gap.priority]}>{gap.priority} priority</Badge>
        <Badge tone="neutral">{gap.importance === "core" ? "Core skill" : "Advanced skill"}</Badge>
      </div>
      <p className="text-xs font-medium text-slate-500">{gap.headline}</p>
      <dl className="flex flex-col gap-1.5 text-sm text-slate-700">
        <div>
          <dt className="inline font-medium">Why it matters: </dt>
          <dd className="inline">{gap.why}</dd>
        </div>
        <div>
          <dt className="inline font-medium">What to learn: </dt>
          <dd className="inline">{gap.learn}</dd>
        </div>
        {gap.practice && (
          <div>
            <dt className="inline font-medium">Practical task: </dt>
            <dd className="inline">{gap.practice}</dd>
          </div>
        )}
        <div>
          <dt className="inline font-medium">On your resume: </dt>
          <dd className="inline">{gap.resume_tip}</dd>
        </div>
      </dl>
    </article>
  );
}

// Role-specific skills analysis: grouped skills with evidence, the role's requirements and prioritised gaps.
export default function RoleAnalysis({ resumeId, role, onRoleChange }) {
  const report = useApiResource(() => getRoleAnalysis(role, resumeId), `role-analysis:${resumeId}:${role || "general"}`, {
    enabled: Boolean(resumeId),
  });
  const data = report.data;
  const roles = data?.roles || [];

  return (
    <section aria-labelledby="role-analysis-title" className={panel}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="role-analysis-title" className="text-base font-semibold text-slate-900">
            Skills analysis for a target role
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Compare your resume with what a role needs. Skills are marked by how your resume shows them.
          </p>
        </div>
        <Select
          label="Target role"
          className="sm:w-64"
          value={role || ""}
          onChange={(e) => onRoleChange(e.target.value)}
          options={[{ value: "", label: "General analysis (no role)" }, ...roles.map((r) => ({ value: r.slug, label: r.title }))]}
        />
      </div>

      <div className="mt-5" aria-live="polite">
        {(report.status === "loading" || report.status === "idle") && !data ? (
          <CardSkeleton label="the skills analysis" lines={5} />
        ) : report.status === "error" ? (
          <CardError error={report.error} onRetry={report.reload} label="the skills analysis" />
        ) : !data ? null : (
          <div className="flex flex-col gap-6">
            {data.mode === "role" && data.fit && (
              <div className="grid grid-cols-1 gap-4 rounded-xl bg-brand-50/50 p-4 md:grid-cols-[auto_1fr]">
                <div>
                  <p className="text-xs font-medium text-slate-500">{data.role.title} fit</p>
                  <p className="text-3xl font-semibold tabular-nums text-slate-900">
                    {data.fit.score}
                    <span className="text-base font-normal text-slate-500">/100</span>
                  </p>
                  <p className="max-w-xs text-xs text-slate-500">{data.fit.basis}</p>
                </div>
                <div className="flex flex-col justify-center gap-2">
                  <Bar label="Core skills found in your resume" value={data.fit.core_found} total={data.fit.core_total} />
                  <Bar label="Core skills shown in a project or experience" value={data.fit.core_demonstrated} total={data.fit.core_total} />
                  <Bar label="Advanced skills found" value={data.fit.advanced_found} total={data.fit.advanced_total} />
                </div>
              </div>
            )}

            <div>
              <h3 className="text-sm font-semibold text-slate-900">Your current skills</h3>
              <p className="mb-2 mt-0.5 flex flex-wrap gap-2 text-xs text-slate-500">
                {Object.entries(STATUS)
                  .filter(([k]) => k !== "not_found")
                  .map(([k, v]) => (
                    <Badge key={k} tone={v.tone}>
                      {v.label}
                    </Badge>
                  ))}
              </p>
              <SkillGroups groups={data.current_skills} />
            </div>

            {data.mode === "general" ? (
              <CardEmpty title="Choose a target role" message={data.note} />
            ) : (
              <>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">What a {data.role.title} needs</h3>
                  <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Role requirements">
                    {data.requirements.map((r) => (
                      <li key={r.skill}>
                        <Badge tone={STATUS[r.status].tone}>
                          {r.skill}
                          <span className="opacity-70"> · {r.importance}</span>
                          <span className="sr-only"> – {STATUS[r.status].label}</span>
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">Gaps and what to do ({data.gaps.length})</h3>
                  <p className="mt-0.5 text-xs text-slate-500">{data.note}</p>
                  {data.gaps.length === 0 ? (
                    <p className="mt-2 text-sm text-mint-800">Your resume shows every skill this role lists in a project or experience entry.</p>
                  ) : (
                    <ol className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2" aria-label="Skill gaps for this role">
                      {data.gaps.map((g) => (
                        <li key={g.skill} className="min-w-0">
                          <GapCard gap={g} />
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
                {data.learning_priorities?.length > 0 && (
                  <p className="text-sm text-slate-700">
                    <span className="font-medium">Learning order: </span>
                    {data.learning_priorities.join(" → ")}
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
