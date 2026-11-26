import { Link } from "react-router-dom";
import Icon from "../../../components/ui/Icon";
import DashboardCard, { CardEmpty, ResourceState } from "./DashboardCard";

function Meter({ label, present, total }) {
  const pct = total > 0 ? Math.round((present / total) * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="text-slate-600">{label}</span>
        <span className="font-medium tabular-nums text-slate-900">
          {present}/{total}
        </span>
      </div>
      <div
        className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={present}
      >
        <div
          className="h-full origin-left rounded-full bg-gradient-to-r from-brand-500 to-violet-500 motion-safe:animate-grow-x"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// The backend provides an ATS *report* for one resume + internship pair (keyword coverage and
// resume checks), not an overall ATS score. This card shows that report for the best match and
// says so explicitly; it never presents the match score as an ATS score.
export default function AtsCard({ resume, best, ats }) {
  let body;
  if (!resume || resume.status !== "completed") {
    body = <CardEmpty title="Not available yet" message="Upload and parse a resume to run an ATS check." />;
  } else if (!best) {
    body = <CardEmpty title="Not available yet" message="Run internship matching first; the ATS check uses your best match." />;
  } else {
    body = (
      <ResourceState resource={ats} label="the ATS check" lines={4}>
        {(report) => {
          const checks = report.checks || [];
          const passed = checks.filter((c) => c.passed).length;
          const failing = checks.filter((c) => !c.passed);
          return (
            <div className="flex flex-1 flex-col gap-4">
              <p className="text-xs text-slate-500">
                Against <span className="font-medium text-slate-700">{report.internship?.title || best.internship.title}</span> at{" "}
                {report.internship?.company || best.internship.company}
              </p>
              <div className="flex flex-col gap-3">
                <Meter label="Resume checks passed" present={passed} total={checks.length} />
                <Meter label="Required keywords found" present={report.required_coverage.present} total={report.required_coverage.total} />
                <Meter label="Preferred keywords found" present={report.preferred_coverage.present} total={report.preferred_coverage.total} />
              </div>
              {report.missing_keywords?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500">Keywords this posting asks for that your resume doesn't show</p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Missing keywords">
                    {report.missing_keywords.slice(0, 6).map((k) => (
                      <li key={k} className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-100">
                        {k}
                      </li>
                    ))}
                    {report.missing_keywords.length > 6 && (
                      <li className="px-1 text-xs text-slate-500">+{report.missing_keywords.length - 6} more</li>
                    )}
                  </ul>
                </div>
              )}
              {failing.length > 0 && (
                <ul className="flex flex-col gap-1 text-xs text-slate-600" aria-label="Checks to fix">
                  {failing.slice(0, 3).map((c) => (
                    <li key={c.check} className="flex items-start gap-1.5">
                      <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                      {c.detail}
                    </li>
                  ))}
                </ul>
              )}
              <p className="rounded-lg bg-brand-50/70 px-3 py-2 text-xs text-brand-900">
                <span className="font-semibold">How to improve:</span> fix the checks above, then add missing keywords only where you
                genuinely have the skill.{" "}
                <Link
                  to={`/documents?type=resume&internship=${report.internship?.internship_id ?? best.internship.internship_id}`}
                  className="font-semibold text-brand-700 underline-offset-2 hover:underline"
                >
                  Tailor your resume
                </Link>
              </p>
            </div>
          );
        }}
      </ResourceState>
    );
  }

  return (
    <DashboardCard title="ATS check" icon="clipboard" link="/documents" linkLabel="Documents">
      {body}
      <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
        Overall ATS score: <span className="font-medium text-slate-700">not provided by the backend</span>. These are its ATS
        checks for one posting.
      </p>
    </DashboardCard>
  );
}
