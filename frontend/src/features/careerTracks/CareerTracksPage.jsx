import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { getCareerTrack, getCareerTrackJobs, listCareerTracks } from "../../api/careerTracks";
import { listResumes } from "../../api/resumes";
import Badge from "../../components/ui/Badge";
import useApiResource from "../../hooks/useApiResource";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import { latestParsed, safeExternalUrl } from "../resumes/resumeData";
import ProgressSelect from "../skillGaps/components/ProgressSelect";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

function List({ title, items, ordered = false }) {
  const Tag = ordered ? "ol" : "ul";
  return (
    <section aria-label={title} className={panel}>
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      <Tag className={`mt-3 flex flex-col gap-1.5 text-sm text-slate-700 ${ordered ? "list-inside list-decimal" : "list-inside list-disc"}`}>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </Tag>
    </section>
  );
}

function TrackList() {
  const tracks = useApiResource(listCareerTracks, "career-tracks");
  if ((tracks.status === "loading" || tracks.status === "idle") && !tracks.data) return <CardSkeleton label="career tracks" lines={6} />;
  if (tracks.status === "error") return <CardError error={tracks.error} onRetry={tracks.reload} label="career tracks" />;
  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Career tracks">
      {tracks.data.map((t) => (
        <li key={t.slug} className={`${panel} flex flex-col gap-2`}>
          <Link to={`/career-tracks/${t.slug}`} className="text-lg font-semibold text-slate-900 hover:text-brand-700 hover:underline">
            {t.title}
          </Link>
          <p className="text-sm text-slate-600">{t.summary}</p>
          <p className="text-xs text-slate-500">Core skills: {t.core_skills.join(", ")}</p>
        </li>
      ))}
    </ul>
  );
}

function TrackDetail({ slug }) {
  const resumes = useApiResource(listResumes, "resumes");
  const resume = resumes.status === "success" ? latestParsed(resumes.data) : null;
  const ready = resumes.status === "success" || resumes.status === "error";
  const track = useApiResource(() => getCareerTrack(slug, resume?.resume_id), `career-track:${slug}:${resume?.resume_id ?? "none"}`, { enabled: ready });
  const jobs = useApiResource(() => getCareerTrackJobs(slug), `career-track-jobs:${slug}`);

  if (!ready || ((track.status === "loading" || track.status === "idle") && !track.data)) return <CardSkeleton label="the career track" lines={8} />;
  if (track.status === "error" && track.error?.status === 404) return <CardEmpty title="Career track not found" message="Choose a track from the list." action={<Link to="/career-tracks" className="text-sm font-medium text-brand-700 hover:underline">All career tracks</Link>} />;
  if (track.status === "error") return <CardError error={track.error} onRetry={track.reload} label="the career track" />;
  const t = track.data;

  return (
    <div className="flex flex-col gap-6">
      <header className={panel}>
        <Link to="/career-tracks" className="text-sm font-medium text-brand-700 hover:underline">
          ← All career tracks
        </Link>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{t.title}</h1>
        <p className="mt-1 text-sm text-slate-600">{t.summary}</p>
        {t.coverage ? (
          <p className="mt-3 text-sm text-slate-700">
            Your resume shows <strong>{t.coverage.on_resume}</strong> of {t.coverage.total} track skills ({t.coverage.percent}%).
          </p>
        ) : (
          <p className="mt-3 text-sm text-slate-500">Upload a resume to see which of these skills you already show.</p>
        )}
      </header>

      <section aria-labelledby="track-skills" className={panel}>
        <h2 id="track-skills" className="text-base font-semibold text-slate-900">
          Skills and progress
        </h2>
        <ul className="mt-3 flex flex-col divide-y divide-slate-100" aria-label="Track skills">
          {t.skills.map((s) => {
            const url = safeExternalUrl(s.resource?.url);
            return (
              <li key={s.skill} className="flex flex-wrap items-center gap-2 py-3">
                <span className="font-medium text-slate-900">{s.skill}</span>
                <Badge tone={s.tier === "core" ? "info" : "neutral"}>{s.tier}</Badge>
                {s.on_resume && <Badge tone="success">on your resume</Badge>}
                {s.estimated_hours && <span className="text-xs text-slate-500">about {s.estimated_hours} h</span>}
                {url && (
                  <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-700 hover:underline">
                    {s.resource.title}
                  </a>
                )}
                <span className="ml-auto">
                  <ProgressSelect skill={s.skill} status={s.status} />
                </span>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-xs text-slate-400">{t.resources_note}</p>
      </section>

      <section aria-label="Learning roadmap" className={panel}>
        <h2 className="text-base font-semibold text-slate-900">Learning roadmap</h2>
        <ol className="mt-3 flex flex-col gap-3">
          {t.roadmap.map((stage, i) => (
            <li key={stage.stage} className="rounded-lg bg-slate-50 px-4 py-3">
              <p className="text-sm font-medium text-slate-900">
                {i + 1}. {stage.stage}
              </p>
              <p className="text-sm text-slate-600">{stage.goal}</p>
              <p className="mt-1 text-xs text-slate-500">{stage.skills.join(" · ")}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <List title="Practice exercises" items={t.exercises} />
        <List title="Project ideas" items={t.projects} />
        <List title="Resume advice" items={t.resume_advice} />
        <section aria-label="Interview questions" className={panel}>
          <h2 className="text-base font-semibold text-slate-900">Interview questions</h2>
          <ul className="mt-3 flex flex-col gap-2 text-sm text-slate-700">
            {t.interview_questions.map((q) => (
              <li key={q.question}>
                <span className="text-xs text-slate-500">{q.skill}{q.difficulty ? ` · ${q.difficulty}` : ""} — </span>
                {q.question}
              </li>
            ))}
          </ul>
          <Link to="/interview-prep" className="mt-3 inline-block text-sm font-medium text-brand-700 hover:underline">
            Practise with feedback
          </Link>
        </section>
      </div>

      <section aria-label="Relevant opportunities" className={panel}>
        <h2 className="text-base font-semibold text-slate-900">Relevant opportunities</h2>
        {(jobs.status === "loading" || jobs.status === "idle") && !jobs.data ? (
          <CardSkeleton label="opportunities" lines={3} />
        ) : jobs.status === "error" ? (
          <CardError error={jobs.error} onRetry={jobs.reload} label="opportunities" />
        ) : !jobs.data.items.length ? (
          <p className="mt-2 text-sm text-slate-500">No open listings ask for this track's skills right now.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {jobs.data.items.map(({ internship: it, track_skill_overlap: overlap }) => (
              <li key={it.internship_id} className="flex flex-wrap items-center gap-2 text-sm">
                <Link to={`/internships/${it.internship_id}`} className="font-medium text-slate-900 hover:text-brand-700 hover:underline">
                  {it.title}
                </Link>
                <span className="text-slate-500">{it.company}</span>
                <span className="text-xs text-slate-500">· {overlap} matching track skill{overlap === 1 ? "" : "s"}</span>
                {it.source_label && <Badge>{it.source_label}</Badge>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default function CareerTracksPage() {
  const { slug } = useParams();
  useEffect(() => {
    const previous = document.title;
    document.title = "Career tracks · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {!slug && (
        <header>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Career tracks</h1>
          <p className="mt-1 text-sm text-slate-600">
            Roadmaps, skills, interview questions, exercises and projects for each role, from frontend and backend development to data, AI, cloud and security. Track your progress skill by skill.
          </p>
        </header>
      )}
      {slug ? <TrackDetail slug={slug} /> : <TrackList />}
    </div>
  );
}
