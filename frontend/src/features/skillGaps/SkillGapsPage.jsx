import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { normalizeError } from "../../api/errors";
import { getResumeSkills, listResumes } from "../../api/resumes";
import { generateRecommendations, GENERATE_TOP_K, listRecommendations } from "../../api/skillGaps";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import Select from "../../components/ui/Select";
import useApiResource from "../../hooks/useApiResource";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import { latestParsed } from "../resumes/resumeData";
import RecommendationCard from "./components/RecommendationCard";
import RoleAnalysis from "./components/RoleAnalysis";
import { countByStatus } from "./gapFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";
const FILTERS = [
  { id: "open", label: "To learn", match: (r) => r.status === "pending" || r.status === "in_progress" },
  { id: "completed", label: "Completed", match: (r) => r.status === "completed" },
  { id: "dismissed", label: "Dismissed", match: (r) => r.status === "dismissed" },
  { id: "all", label: "All", match: () => true },
];
const TOP_K_OPTIONS = [3, 5, 10, GENERATE_TOP_K.max];

function SkillsYouHave({ skills }) {
  return (
    <section aria-labelledby="have-title" className={panel}>
      <h2 id="have-title" className="text-base font-semibold text-slate-900">
        Skills on your resume
      </h2>
      <div className="mt-3">
        {skills.status === "loading" || skills.status === "idle" ? (
          <CardSkeleton label="your skills" lines={2} />
        ) : skills.status === "error" ? (
          <CardError error={skills.error} onRetry={skills.reload} label="your skills" />
        ) : !skills.data.skills.length ? (
          <CardEmpty title="No recognised skills" message="Add a skills section to your resume and re-parse it." />
        ) : (
          <>
            <p className="text-sm text-slate-600">
              <span className="text-2xl font-semibold tabular-nums text-slate-900">{skills.data.skills.length}</span> recognised skills
            </p>
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Skills you have">
              {skills.data.skills.map((s) => (
                <li key={s.skill_id} className="rounded-full bg-mint-50 px-2.5 py-0.5 text-xs font-medium text-mint-800">
                  {s.name}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}

// Generates (or refreshes) the current recommendation set from the latest match run.
function AnalysePanel({ resumeId, onGenerated }) {
  const [topK, setTopK] = useState(String(GENERATE_TOP_K.default));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { tone, text, link? }

  const run = async () => {
    if (busy) return;
    setBusy(true);
    setResult(null);
    try {
      const response = await generateRecommendations(resumeId, { top_k: Number(topK) });
      onGenerated(response.recommendations);
      const parts = [`Analysed ${response.internships.length} internship${response.internships.length === 1 ? "" : "s"} from your latest matches.`];
      if (response.newly_acquired_skills?.length) parts.push(`Now on your resume: ${response.newly_acquired_skills.join(", ")}.`);
      if (response.skipped_internship_ids?.length) parts.push(`${response.skipped_internship_ids.length} closed internship(s) were skipped.`);
      setResult({ tone: "success", text: parts.join(" ") });
    } catch (failure) {
      const err = normalizeError(failure);
      setResult({ tone: "error", text: err.message, link: err.status === 409 ? "/matches" : null });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="analyse-title" className={panel}>
      <h2 id="analyse-title" className="text-base font-semibold text-slate-900">
        Update my learning plan
      </h2>
      <p className="mt-0.5 text-sm text-slate-600">
        Compares your resume with your best-matching internships and lists the skills to learn. Progress you've already recorded is kept.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <Select
          label="Internships to analyse"
          value={topK}
          onChange={(e) => setTopK(e.target.value)}
          options={TOP_K_OPTIONS.map((n) => ({ value: String(n), label: `Top ${n} matches` }))}
        />
        <Button onClick={run} loading={busy}>
          {!busy && <Icon name="sparkles" className="h-4 w-4" />}
          {busy ? "Analysing…" : "Analyse my top matches"}
        </Button>
      </div>
      {result && (
        <p role={result.tone === "error" ? "alert" : "status"} className={`mt-3 rounded-lg px-3 py-2 text-sm ${result.tone === "error" ? "bg-red-50 text-red-800" : "bg-mint-50 text-mint-800"}`}>
          {result.text}{" "}
          {result.link && (
            <Link to={result.link} className="font-medium underline">
              Go to matches
            </Link>
          )}
        </p>
      )}
    </section>
  );
}

export default function SkillGapsPage() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.find((f) => f.id === params.get("status")) || FILTERS[0];
  const resumes = useApiResource(listResumes, "resumes");
  const resume = resumes.status === "success" ? latestParsed(resumes.data) : null;
  const rid = resume?.resume_id ?? null;
  const skills = useApiResource(() => getResumeSkills(rid), rid, { enabled: Boolean(rid) });
  const recs = useApiResource(() => listRecommendations(rid), rid, { enabled: Boolean(rid) });

  useEffect(() => {
    const previous = document.title;
    document.title = "Skill gaps · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  // Replace one record with the persisted version returned by the backend.
  const onUpdated = (updated) =>
    recs.setData((recs.data || []).map((r) => (r.recommendation_id === updated.recommendation_id ? updated : r)));

  const header = (
    <header>
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Skill gaps</h1>
      <p className="mt-1 text-sm text-slate-600">
        How your skills compare with a target role, and the skills your best-matching internships ask for that aren't on your resume yet - with a learning plan for each.
      </p>
    </header>
  );

  if (resumes.status === "loading" || resumes.status === "idle") {
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        {header}
        <div className={panel}>
          <CardSkeleton label="your resume" lines={3} />
        </div>
      </div>
    );
  }
  if (resumes.status === "error") {
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        {header}
        <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />
      </div>
    );
  }
  if (!resume) {
    return (
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        {header}
        <CardEmpty
          title="Upload a resume to see your skill gaps"
          message="Skill gaps compare your latest successfully parsed resume with internships."
          action={<Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">Go to resumes</Link>}
        />
      </div>
    );
  }

  const all = recs.data || [];
  const counts = countByStatus(all);
  const visible = all.filter(filter.match);
  // Gaps still open (to do / in progress); completed and dismissed skills are not counted as gaps.
  const open = all.filter(FILTERS[0].match);
  const missing = open.filter((r) => r.gap_level === "missing").length;
  const partial = open.filter((r) => r.gap_level === "partial").length;

  let list;
  if ((recs.status === "loading" || recs.status === "idle") && !recs.data) list = <CardSkeleton label="your learning plan" lines={5} />;
  else if (recs.status === "error") list = <CardError error={recs.error} onRetry={recs.reload} label="your learning plan" />;
  else if (!all.length) {
    list = (
      <CardEmpty
        title="No skill gaps yet"
        message="Use “Analyse my top matches” to compare your resume with your best internship matches. If nothing appears afterwards, your resume already covers the skills they ask for."
      />
    );
  } else if (!visible.length) {
    list = <CardEmpty title={`Nothing under “${filter.label}”`} message="Choose another filter to see the rest of your learning plan." />;
  } else {
    list = (
      <ol className="grid grid-cols-1 gap-4 xl:grid-cols-2" aria-label="Learning recommendations">
        {visible.map((rec) => (
          <li key={rec.recommendation_id} className="flex min-w-0 [&>article]:w-full">
            <RecommendationCard rec={rec} onUpdated={onUpdated} rank={all.indexOf(rec) + 1} />
          </li>
        ))}
      </ol>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {header}
      <p className="text-xs text-slate-500">Using {resume.filename}, your latest parsed resume.</p>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SkillsYouHave skills={skills} />
        <AnalysePanel resumeId={rid} onGenerated={(items) => recs.setData(items)} />
      </div>

      <RoleAnalysis
        resumeId={rid}
        role={params.get("role") || ""}
        onRoleChange={(value) =>
          setParams((p) => {
            const next = new URLSearchParams(p);
            if (value) next.set("role", value);
            else next.delete("role");
            return next;
          })
        }
      />

      <section aria-labelledby="plan-title" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="plan-title" className="text-lg font-semibold text-slate-900">
              Your learning plan
            </h2>
            {all.length > 0 && (
              <p className="text-sm text-slate-600">
                {`${missing} missing and ${partial} partly-covered skill${missing + partial === 1 ? "" : "s"} to learn · ${counts.completed || 0} completed`}
              </p>
            )}
          </div>
          <div role="group" aria-label="Filter recommendations" className="inline-flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
            {FILTERS.map((f) => {
              const n = f.id === "all" ? all.length : all.filter(f.match).length;
              return (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={filter.id === f.id}
                  onClick={() => setParams(f.id === "open" ? {} : { status: f.id })}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                    filter.id === f.id ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {f.label} <span className="tabular-nums text-slate-400">{n}</span>
                </button>
              );
            })}
          </div>
        </div>
        {list}
      </section>
    </div>
  );
}
