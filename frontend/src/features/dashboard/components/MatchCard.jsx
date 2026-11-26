import { useState } from "react";
import { Link } from "react-router-dom";
import { runMatching } from "../../../api/dashboard";
import { errorMessage } from "../../../api/errors";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";
import { formatDate } from "../../../utils/dates";
import { bestMatch } from "../format";
import DashboardCard, { CardEmpty, ResourceState } from "./DashboardCard";
import ScoreRing from "./ScoreRing";

// Best internship match from the latest match run (compatibility score 0-100 from the matching
// engine). This is NOT an ATS score; the ATS check has its own card.
export default function MatchCard({ resume, matches, onMatched }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      onMatched(await runMatching(resume.resume_id));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setRunning(false);
    }
  };

  const runButton = (label) => (
    <Button onClick={run} loading={running}>
      {!running && <Icon name="sparkles" className="h-4 w-4" />}
      {running ? "Matching…" : label}
    </Button>
  );

  let body;
  if (!resume) {
    body = <CardEmpty title="Upload a resume first" message="Matches are calculated from your latest parsed resume." />;
  } else if (resume.status !== "completed") {
    body = <CardEmpty title="Resume not ready" message="Matching needs a successfully parsed resume." />;
  } else {
    body = (
      <ResourceState resource={matches} label="your best match" lines={3}>
        {(runData) => {
          const best = bestMatch(runData);
          if (!best) {
            return (
              <CardEmpty
                title={runData ? "No matching internships found" : "No matches yet"}
                message={
                  runData
                    ? "The last run found no active internships for your resume. Try again after updating it."
                    : "Run matching to rank active internships against your resume."
                }
                action={runButton(runData ? "Run matching again" : "Find my matches")}
              />
            );
          }
          const internship = best.internship;
          const coverage = best.required_skill_coverage;
          return (
            <div className="flex flex-1 flex-col gap-4">
              <div className="flex items-center gap-4">
                <ScoreRing value={best.score} label="compatibility" />
                <div className="min-w-0">
                  <Badge tone="info">{best.label}</Badge>
                  <p className="mt-1.5 text-base font-semibold leading-snug text-slate-900">{internship.title}</p>
                  <p className="flex items-center gap-1 text-sm text-slate-600">
                    <Icon name="building" className="h-4 w-4 shrink-0 text-slate-400" />
                    <span className="truncate">{internship.company}</span>
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {[internship.location, internship.work_mode, internship.domain].filter(Boolean).join(" · ")}
                  </p>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <dt className="text-xs text-slate-500">Compatibility</dt>
                  <dd className="font-semibold text-slate-900">{Math.round(best.score)}%</dd>
                </div>
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <dt className="text-xs text-slate-500">Required skills covered</dt>
                  <dd className="font-semibold text-slate-900">{coverage == null ? "—" : `${Math.round(coverage * 100)}%`}</dd>
                </div>
              </dl>
              {best.missing_required_skills?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500">Missing required skills</p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Missing required skills">
                    {best.missing_required_skills.slice(0, 5).map((skill) => (
                      <li key={skill} className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800">
                        {skill}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Link
                to={`/documents?type=resume&internship=${internship.internship_id}`}
                className="inline-flex w-fit items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
              >
                <Icon name="edit" className="h-4 w-4" />
                Tailor my resume for this internship
              </Link>
              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                <span>
                  Best of {runData.results.length} result{runData.results.length === 1 ? "" : "s"} · run {formatDate(runData.created_at)}
                </span>
                <Button variant="ghost" onClick={run} loading={running} className="px-2 py-1 text-xs">
                  {!running && <Icon name="refresh" className="h-3.5 w-3.5" />}
                  Re-run
                </Button>
              </div>
            </div>
          );
        }}
      </ResourceState>
    );
  }

  return (
    <DashboardCard title="Best internship match" icon="target" link="/matches">
      {body}
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      )}
    </DashboardCard>
  );
}
