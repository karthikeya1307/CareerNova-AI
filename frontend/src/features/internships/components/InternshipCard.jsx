import { Link } from "react-router-dom";
import Badge from "../../../components/ui/Badge";
import Icon from "../../../components/ui/Icon";
import { deadlineInfo, formatDuration, formatStipend } from "../internshipFormat";

// One internship in a list. `badge` lets callers add a real score (semantic similarity, match score).
export default function InternshipCard({ internship, badge }) {
  const deadline = deadlineInfo(internship.deadline);
  const facts = [
    internship.location,
    internship.work_mode,
    formatDuration(internship.duration_weeks),
    formatStipend(internship.stipend_per_month, internship.stipend_currency),
  ].filter(Boolean);
  const skills = internship.required_skills || [];

  return (
    <article className="relative flex w-full min-w-0 flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card transition-shadow hover:shadow-card-hover">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold leading-snug text-slate-900">
            <Link
              to={`/internships/${internship.internship_id}`}
              className="rounded after:absolute after:inset-0 hover:text-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
            >
              {internship.title}
            </Link>
          </h3>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-slate-600">
            <Icon name="building" className="h-4 w-4 shrink-0 text-slate-400" />
            <span className="truncate">{internship.company}</span>
          </p>
        </div>
        {badge}
      </div>
      {facts.length > 0 && <p className="text-xs text-slate-600">{facts.join(" · ")}</p>}
      {skills.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label={`Required skills for ${internship.title}`}>
          {skills.slice(0, 4).map((skill) => (
            <li key={skill} className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700">
              {skill}
            </li>
          ))}
          {skills.length > 4 && <li className="px-1 text-xs text-slate-500">+{skills.length - 4}</li>}
        </ul>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
        {internship.domain && <Badge>{internship.domain}</Badge>}
        {deadline && <Badge tone={deadline.tone}>{deadline.label}</Badge>}
      </div>
    </article>
  );
}
