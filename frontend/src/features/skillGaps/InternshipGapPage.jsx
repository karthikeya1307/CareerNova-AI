import { useEffect, useId, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { normalizeError } from "../../api/errors";
import { scoreInternship } from "../../api/matches";
import { listResumes } from "../../api/resumes";
import { generateRecommendations, getInternshipGap } from "../../api/skillGaps";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useConfirm } from "../../context/ConfirmContext";
import useApiResource from "../../hooks/useApiResource";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import MatchBreakdown from "../matches/MatchBreakdown";
import { latestParsed } from "../resumes/resumeData";
import JobRoadmap from "./components/JobRoadmap";
import LearningPlan from "./components/LearningPlan";
import { gapLevel, IMPORTANCE } from "./gapFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

// Coverage straight from the backend summary counts (no derived score).
function Coverage({ label, total, matched, partial, missing }) {
  if (!total) {
    return (
      <div>
        <p className="text-sm font-medium text-slate-800">{label}</p>
        <p className="text-xs text-slate-500">None listed for this internship.</p>
      </div>
    );
  }
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-slate-800">{label}</p>
        <p className="text-sm text-slate-600">
          <span className="font-semibold tabular-nums text-slate-900">
            {matched} of {total}
          </span>{" "}
          ({Math.round((matched / total) * 100)}%)
        </p>
      </div>
      <div
        className="mt-1.5 flex h-2.5 overflow-hidden rounded-full bg-slate-100"
        role="img"
        aria-label={`${label}: ${matched} have, ${partial} partly, ${missing} missing of ${total}`}
      >
        {matched > 0 && <div className="bg-mint-500" style={{ width: `${(matched / total) * 100}%` }} />}
        {partial > 0 && <div className="bg-amber-400" style={{ width: `${(partial / total) * 100}%` }} />}
        {missing > 0 && <div className="bg-red-400" style={{ width: `${(missing / total) * 100}%` }} />}
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Have {matched} · Partly {partial} · Missing {missing}
      </p>
    </div>
  );
}

function SkillGroup({ title, items, empty }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">
        {title} <span className="font-normal text-slate-400">({items.length})</span>
      </h3>
      {items.length ? (
        <ul className="mt-2 flex flex-col gap-2" aria-label={title}>
          {items.map((s) => {
            const level = gapLevel(s.status);
            return (
              <li key={s.skill} className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-900">{s.skill}</span>
                  <Badge tone={level.tone}>{level.label}</Badge>
                  <Badge>{IMPORTANCE[s.importance] || s.importance}</Badge>
                </div>
                {s.related_skills?.length > 0 && (
                  <ul className="mt-1 text-xs text-slate-600">
                    {s.related_skills.map((r) => (
                      <li key={r.skill}>
                        <span className="font-medium">{r.skill}</span>: {r.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-slate-500">{empty}</p>
      )}
    </div>
  );
}

function PlanItem({ item }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <li className="rounded-xl border border-slate-200">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-slate-900">{item.skill}</span>
          <Badge tone={gapLevel(item.status).tone}>{gapLevel(item.status).label}</Badge>
        </span>
        <Icon name="chevronDown" className={`h-4 w-4 shrink-0 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div id={id} className="border-t border-slate-100 px-4 py-3">
          <LearningPlan plan={item.plan} />
        </div>
      )}
    </li>
  );
}

// Skill-gap analysis for one internship (GET /skill-gaps/resumes/{rid}/internships/{iid}) against the
// latest parsed resume, plus the F4 match breakdown for the same pair.
export default function InternshipGapPage() {
  const { internshipId } = useParams();
  const iid = Number(internshipId);
  const validId = Number.isInteger(iid) && iid > 0;
  const confirm = useConfirm();
  const resumes = useApiResource(listResumes, "resumes");
  const resume = resumes.status === "success" ? latestParsed(resumes.data) : null;
  const rid = resume?.resume_id ?? null;
  const key = rid && validId ? `${rid}:${iid}` : null;
  const gap = useApiResource(() => getInternshipGap(rid, iid), key, { enabled: Boolean(key) });
  const match = useApiResource(() => scoreInternship(rid, iid), key, { enabled: Boolean(key) });
  const [target, setTarget] = useState({ busy: false, message: null });

  useEffect(() => {
    const previous = document.title;
    document.title = `Skill gap${gap.data ? `: ${gap.data.internship.title}` : ""} · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [gap.data]);

  const back = (
    <div className="flex flex-wrap gap-4 text-sm">
      <Link to="/skill-gaps" className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline">
        <Icon name="arrowRight" className="h-4 w-4 rotate-180" />
        All skill gaps
      </Link>
      {validId && (
        <Link to={`/internships/${iid}`} className="font-medium text-brand-700 hover:underline">
          View internship
        </Link>
      )}
    </div>
  );

  const useAsTarget = async () => {
    if (target.busy) return;
    const ok = await confirm({
      title: "Base your learning plan on this internship?",
      message:
        "Your current learning plan will be replaced by the skill gaps for this internship. Progress you've recorded on skills that are still needed is kept.",
      confirmLabel: "Update learning plan",
      tone: "primary",
    });
    if (!ok) return;
    setTarget({ busy: true, message: null });
    try {
      const response = await generateRecommendations(rid, { internship_ids: [iid] });
      const n = response.recommendations.length;
      setTarget({ busy: false, message: { tone: "success", text: `Learning plan updated: ${n} skill${n === 1 ? "" : "s"} to work on.` } });
    } catch (failure) {
      setTarget({ busy: false, message: { tone: "error", text: normalizeError(failure).message } });
    }
  };

  let body;
  if (!validId) body = <CardEmpty title="Internship not found" />;
  else if (resumes.status === "loading" || resumes.status === "idle") body = <div className={panel}><CardSkeleton label="your resume" lines={3} /></div>;
  else if (resumes.status === "error") body = <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />;
  else if (!resume) {
    body = (
      <CardEmpty
        title="Upload a resume to see this skill gap"
        message="The analysis compares this internship with your latest parsed resume."
        action={<Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">Go to resumes</Link>}
      />
    );
  } else if (gap.status === "loading" || gap.status === "idle") body = <div className={panel}><CardSkeleton label="the skill gap" lines={6} /></div>;
  else if (gap.status === "error" && gap.error.status === 404) {
    body = <CardEmpty title="Internship not found" message="It may have closed or been removed, so its skill gap can't be analysed." />;
  } else if (gap.status === "error") body = <CardError error={gap.error} onRetry={gap.reload} label="the skill gap" />;
  else {
    const g = gap.data;
    const s = g.summary || {};
    body = (
      <>
        <header className={panel}>
          <p className="text-sm font-medium text-brand-700">Skill gap</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{g.internship.title}</h1>
          <p className="text-slate-600">{g.internship.company}</p>
          <p className="mt-2 text-xs text-slate-500">Compared with {resume.filename}.</p>
          <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
            <Coverage label="Required skills you have" total={s.required_total} matched={s.required_matched} partial={s.required_partial} missing={s.required_missing} />
            <Coverage label="Preferred skills you have" total={s.preferred_total} matched={s.preferred_matched} partial={s.preferred_partial} missing={s.preferred_missing} />
          </div>
        </header>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="flex min-w-0 flex-col gap-6">
            <section aria-labelledby="skills-title" className={panel}>
              <h2 id="skills-title" className="mb-4 text-base font-semibold text-slate-900">
                Skills for this internship
              </h2>
              <div className="flex flex-col gap-5">
                <SkillGroup title="Missing skills" items={g.missing} empty="No missing skills — your resume covers everything this internship lists." />
                <SkillGroup title="Partly covered" items={g.partial} empty="None." />
                <SkillGroup title="Skills you have" items={g.matched} empty="None of the listed skills were found on your resume yet." />
              </div>
            </section>
            <section aria-labelledby="plans-title" className={panel}>
              <h2 id="plans-title" className="text-base font-semibold text-slate-900">
                What to learn, in order
              </h2>
              {g.learning_plans?.length ? (
                <>
                  {g.learning_order?.length > 0 && <p className="mt-1 text-sm text-slate-600">Suggested order: {g.learning_order.join(" → ")}</p>}
                  <ol className="mt-4 flex flex-col gap-2" aria-label="Learning plans">
                    {g.learning_plans.map((item) => (
                      <PlanItem key={item.skill} item={item} />
                    ))}
                  </ol>
                </>
              ) : (
                <p className="mt-2 text-sm text-slate-500">Nothing to learn for this internship — no missing or partial skills.</p>
              )}
            </section>
            <section aria-labelledby="roadmap-title" className={panel}>
              <h2 id="roadmap-title" className="text-base font-semibold text-slate-900">
                Your learning roadmap
              </h2>
              <p className="mb-4 mt-1 text-sm text-slate-600">
                Track each skill as Not Started, Learning, Practiced or Completed. Progress is saved and counts for every job that needs the skill.
              </p>
              <JobRoadmap resumeId={rid} internshipId={iid} />
            </section>
          </div>
          <div className="flex min-w-0 flex-col gap-6">
            <section aria-labelledby="gap-match-title" className={panel}>
              <h2 id="gap-match-title" className="mb-4 text-base font-semibold text-slate-900">
                Your match
              </h2>
              {match.status === "loading" || match.status === "idle" ? (
                <CardSkeleton label="your match" lines={3} />
              ) : match.status === "error" ? (
                <CardError error={match.error} onRetry={match.reload} label="your match" />
              ) : (
                <MatchBreakdown match={match.data} compact />
              )}
            </section>
            <section aria-labelledby="target-title" className={panel}>
              <h2 id="target-title" className="text-base font-semibold text-slate-900">
                Focus on this internship
              </h2>
              <p className="mt-1 text-sm text-slate-600">Turn these gaps into your learning plan and track your progress on the Skill gaps page.</p>
              <Button className="mt-4" onClick={useAsTarget} loading={target.busy}>
                Use for my learning plan
              </Button>
              {target.message && (
                <p role={target.message.tone === "error" ? "alert" : "status"} className={`mt-3 rounded-lg px-3 py-2 text-sm ${target.message.tone === "error" ? "bg-red-50 text-red-800" : "bg-mint-50 text-mint-800"}`}>
                  {target.message.text}{" "}
                  {target.message.tone === "success" && (
                    <Link to="/skill-gaps" className="font-medium underline">
                      Open learning plan
                    </Link>
                  )}
                </p>
              )}
            </section>
          </div>
        </div>
      </>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {back}
      {gap.status !== "success" && <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Skill gap</h1>}
      {body}
    </div>
  );
}
