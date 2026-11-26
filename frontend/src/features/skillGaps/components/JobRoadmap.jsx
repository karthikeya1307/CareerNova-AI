import { useState } from "react";
import { getJobRoadmap } from "../../../api/skillGaps";
import Badge from "../../../components/ui/Badge";
import useApiResource from "../../../hooks/useApiResource";
import { CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import { safeExternalUrl } from "../../resumes/resumeData";
import ProgressSelect from "./ProgressSelect";

function Step({ step, onSaved }) {
  const [open, setOpen] = useState(false);
  const url = safeExternalUrl(step.resource?.url);
  return (
    <li className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">{step.step}</span>
        <span className="font-medium text-slate-900">{step.skill}</span>
        <Badge tone={step.importance === "required" ? "warning" : "neutral"}>{step.importance}</Badge>
        {step.gap === "partial" && <Badge tone="info">partly covered</Badge>}
        <span className="ml-auto">
          <ProgressSelect skill={step.skill} status={step.status} onChange={onSaved} />
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-600">{step.why}</p>
      <p className="mt-1 text-xs text-slate-500">{step.evidence.join(" ")}</p>
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="mt-2 text-xs font-medium text-brand-700 hover:underline">
        {open ? "Hide learning plan" : "Show learning plan"}
        <span className="sr-only"> for {step.skill}</span>
      </button>
      {open && (
        <div className="mt-3 flex flex-col gap-3 text-sm text-slate-700">
          <div>
            <p className="text-xs font-medium text-slate-500">
              Topics{step.learning.estimated_hours ? ` · about ${step.learning.estimated_hours} hours` : ""}
              {step.learning.level ? ` · ${step.learning.level}` : ""}
            </p>
            <ul className="mt-1 list-inside list-disc">
              {step.learning.topics.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            {!step.learning.curated && <p className="mt-1 text-xs text-slate-500">General outline (no curated plan for this skill yet).</p>}
          </div>
          {url && (
            <p>
              <span className="text-xs font-medium text-slate-500">Official documentation: </span>
              <a href={url} target="_blank" rel="noopener noreferrer" className="text-brand-700 hover:underline">
                {step.resource.title}
              </a>
            </p>
          )}
          {step.interview_questions.length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-500">Interview questions to practise</p>
              <ul className="mt-1 list-inside list-disc">
                {step.interview_questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </div>
          )}
          <p>
            <span className="text-xs font-medium text-slate-500">Practice project: </span>
            {step.project}
          </p>
        </div>
      )}
    </li>
  );
}

// Ordered roadmap for one job (GET /skill-gaps/resumes/{rid}/internships/{iid}/roadmap) with progress tracking.
export default function JobRoadmap({ resumeId, internshipId }) {
  const roadmap = useApiResource(() => getJobRoadmap(resumeId, internshipId), `roadmap:${resumeId}:${internshipId}`);
  if ((roadmap.status === "loading" || roadmap.status === "idle") && !roadmap.data) return <CardSkeleton label="your learning roadmap" lines={4} />;
  if (roadmap.status === "error") return <CardError error={roadmap.error} onRetry={roadmap.reload} label="your learning roadmap" />;
  const r = roadmap.data;
  const onSaved = (saved) =>
    roadmap.setData({
      ...r,
      steps: r.steps.map((s) => (s.skill === saved.skill ? { ...s, status: saved.status, status_label: saved.status_label } : s)),
      progress: (() => {
        const steps = r.steps.map((s) => (s.skill === saved.skill ? saved.status : s.status));
        const completed = steps.filter((s) => s === "completed").length;
        return { ...r.progress, completed, percent: steps.length ? Math.round((100 * completed) / steps.length) : 100 };
      })(),
    });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
        {r.skill_match != null && (
          <span>
            Skill match <strong className="text-slate-900">{r.skill_match}%</strong>
          </span>
        )}
        <span aria-label="Roadmap progress">
          {r.progress.completed} of {r.progress.total} skills completed ({r.progress.percent}%)
        </span>
      </div>
      {r.steps.length === 0 ? (
        <p className="text-sm text-slate-500">You already have every skill this internship lists.</p>
      ) : (
        <ol className="flex flex-col gap-3" aria-label="Learning roadmap">
          {r.steps.map((step) => (
            <Step key={step.skill} step={step} onSaved={onSaved} />
          ))}
        </ol>
      )}
    </div>
  );
}
