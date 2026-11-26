import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getBookmarkStatus, removeBookmark, saveBookmark, trackInternshipApplication } from "../../api/applications";
import { errorMessage, normalizeError } from "../../api/errors";
import { getInternship } from "../../api/internships";
import { scoreInternship } from "../../api/matches";
import { listResumes } from "../../api/resumes";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDate } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import MatchBreakdown from "../matches/MatchBreakdown";
import { latestParsed, safeExternalUrl } from "../resumes/resumeData";
import { deadlineInfo, formatDuration, formatStipend } from "./internshipFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

function Skills({ title, items, tone }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      {items?.length ? (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={title}>
          {items.map((s) => (
            <li key={s} className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${tone === "brand" ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-700"}`}>
              {s}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-slate-500">None listed.</p>
      )}
    </div>
  );
}

function Actions({ internship }) {
  const toast = useToast();
  const bookmark = useApiResource(() => getBookmarkStatus(internship.internship_id), internship.internship_id);
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null); // { tone, text, link? }
  const applyUrl = safeExternalUrl(internship.application_url);
  const saved = bookmark.status === "success" && bookmark.data.saved;

  const toggleBookmark = async () => {
    setBusy("bookmark");
    setMessage(null);
    try {
      if (saved) {
        await removeBookmark(internship.internship_id);
        bookmark.setData({ saved: false, bookmark: null });
        toast.notify("Removed from saved internships.");
      } else {
        const created = await saveBookmark(internship.internship_id);
        bookmark.setData({ saved: true, bookmark: created });
        toast.success("Saved for later.");
      }
    } catch (failure) {
      setMessage({ tone: "error", text: errorMessage(failure) });
    } finally {
      setBusy(null);
    }
  };

  const markApplied = async () => {
    setBusy("apply");
    setMessage(null);
    try {
      await trackInternshipApplication(internship.internship_id, "APPLIED");
      setMessage({ tone: "success", text: "Added to your applications as Applied.", link: "/applications" });
    } catch (failure) {
      const err = normalizeError(failure);
      if (err.status === 409) setMessage({ tone: "info", text: err.message, link: "/applications" });
      else setMessage({ tone: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  };

  const tones = { success: "bg-mint-50 text-mint-800", info: "bg-brand-50 text-brand-800", error: "bg-red-50 text-red-800" };

  return (
    <section aria-labelledby="actions-title" className={panel}>
      <h2 id="actions-title" className="text-base font-semibold text-slate-900">
        Actions
      </h2>
      <div className="mt-4 flex flex-col gap-2">
        {applyUrl && (
          <a
            href={applyUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
          >
            Apply on company site
            <Icon name="arrowRight" className="h-4 w-4" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        )}
        <Button variant={applyUrl ? "secondary" : "primary"} onClick={markApplied} loading={busy === "apply"} disabled={Boolean(busy)}>
          <Icon name="clipboard" className="h-4 w-4" />
          Mark as applied
        </Button>
        <Link
          to={`/documents?type=resume&internship=${internship.internship_id}`}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
        >
          <Icon name="document" className="h-4 w-4" />
          Tailor my resume
        </Link>
        <Link
          to={`/documents?type=cover_letter&internship=${internship.internship_id}`}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
        >
          <Icon name="edit" className="h-4 w-4" />
          Write a cover letter
        </Link>
        <Link
          to={`/interview-prep?internship=${internship.internship_id}`}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
        >
          <Icon name="mic" className="h-4 w-4" />
          Practise interview questions
        </Link>
        {bookmark.status === "error" ? (
          <p className="text-xs text-red-700">
            Couldn't check whether this is saved.{" "}
            <button type="button" className="font-medium underline" onClick={bookmark.reload}>
              Retry
            </button>
          </p>
        ) : (
          <Button variant="secondary" onClick={toggleBookmark} loading={busy === "bookmark" || bookmark.status === "loading"} disabled={Boolean(busy) || bookmark.status !== "success"} aria-pressed={saved}>
            <Icon name={saved ? "check" : "document"} className="h-4 w-4" />
            {saved ? "Saved" : "Save for later"}
          </Button>
        )}
      </div>
      {message && (
        <p role={message.tone === "error" ? "alert" : "status"} className={`mt-3 rounded-lg px-3 py-2 text-sm ${tones[message.tone]}`}>
          {message.text}{" "}
          {message.link && (
            <Link to={message.link} className="font-medium underline">
              View applications
            </Link>
          )}
        </p>
      )}
    </section>
  );
}

function MatchPanel({ internship }) {
  const resumes = useApiResource(listResumes, "resumes");
  const resume = resumes.status === "success" ? latestParsed(resumes.data) : null;
  const [state, setState] = useState({ status: "idle" });

  const check = async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "success", data: await scoreInternship(resume.resume_id, internship.internship_id) });
    } catch (failure) {
      setState({ status: "error", error: normalizeError(failure) });
    }
  };

  let body;
  if (resumes.status === "loading" || resumes.status === "idle") body = <CardSkeleton label="your resume" lines={1} />;
  else if (resumes.status === "error") body = <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />;
  else if (!resume) {
    body = (
      <CardEmpty
        title="Upload a resume to check your match"
        message="Matching compares this internship with your latest parsed resume."
        action={<Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">Go to resumes</Link>}
      />
    );
  } else if (state.status === "success") {
    body = (
      <>
        <MatchBreakdown match={state.data} />
        <p className="mt-4 text-xs text-slate-500">Using {resume.filename}.</p>
      </>
    );
  } else {
    body = (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-slate-600">
          See how well <span className="font-medium text-slate-800">{resume.filename}</span> fits this internship, with the reasons behind the score.
        </p>
        <Button onClick={check} loading={state.status === "loading"}>
          {state.status !== "loading" && <Icon name="target" className="h-4 w-4" />}
          {state.status === "loading" ? "Checking…" : "Check my match"}
        </Button>
        {state.status === "error" && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            {state.error.status === 404 ? "Matching isn't available: this internship is closed or no longer listed." : state.error.message}
          </p>
        )}
      </div>
    );
  }

  return (
    <section aria-labelledby="match-title" className={panel}>
      <h2 id="match-title" className="mb-4 text-base font-semibold text-slate-900">
        Your match
      </h2>
      {body}
      {resume && (
        <Link
          to={`/skill-gaps/internships/${internship.internship_id}`}
          className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
        >
          <Icon name="chart" className="h-4 w-4" />
          View skill gap and learning plan
        </Link>
      )}
    </section>
  );
}

const FRESHNESS = { verified: ["Verified recently", "success"], stale: ["Last verified over 30 days ago", "warning"], unverified: ["Not verified", "neutral"], expired: ["Closed", "danger"] };

export default function InternshipDetailPage() {
  const { internshipId } = useParams();
  const id = Number(internshipId);
  const validId = Number.isInteger(id) && id > 0;
  const internship = useApiResource(() => getInternship(id), validId ? id : null, { enabled: validId });

  useEffect(() => {
    const previous = document.title;
    document.title = `${internship.data?.title || "Internship"} · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [internship.data?.title]);

  const back = (
    <Link to="/internships" className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
      <Icon name="arrowRight" className="h-4 w-4 rotate-180" />
      All internships
    </Link>
  );

  if (!validId || (internship.status === "error" && internship.error.status === 404)) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {back}
        <CardEmpty title="Internship not found" message="It may have closed or been removed." />
      </div>
    );
  }
  if (internship.status !== "success") {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {back}
        {internship.status === "error" ? (
          <CardError error={internship.error} onRetry={internship.reload} label="this internship" />
        ) : (
          <div className={panel}>
            <CardSkeleton label="the internship" lines={6} />
          </div>
        )}
      </div>
    );
  }

  const it = internship.data;
  const deadline = deadlineInfo(it.deadline);
  const facts = [
    ["Location", it.location],
    ["Work mode", it.work_mode],
    ["Duration", formatDuration(it.duration_weeks)],
    ["Stipend", formatStipend(it.stipend_per_month, it.stipend_currency)],
    ["Minimum education", it.min_education],
    ["Domain", it.domain],
    ["Deadline", deadline ? formatDate(it.deadline) : null],
    ["Posted", it.posted_at ? formatDate(it.posted_at) : null],
    ["Listed", formatDate(it.created_at)],
    ["Last verified", it.last_verified_at ? formatDate(it.last_verified_at) : null],
  ].filter(([, value]) => value);
  const sourceUrl = safeExternalUrl(it.source_url);
  const fresh = FRESHNESS[it.freshness];

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {back}
      <header className={panel}>
        <div className="flex flex-wrap gap-2">
          {it.domain && <Badge>{it.domain}</Badge>}
          {it.work_mode && <Badge tone="info">{it.work_mode}</Badge>}
          {deadline && <Badge tone={deadline.tone}>{deadline.label}</Badge>}
          {it.source_label && <Badge tone={it.source === "dataset" ? "warning" : "neutral"}>{it.source_label}</Badge>}
          {fresh && <Badge tone={fresh[1]}>{fresh[0]}</Badge>}
        </div>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{it.title}</h1>
        <p className="mt-1 flex items-center gap-1.5 text-slate-600">
          <Icon name="building" className="h-4 w-4 text-slate-400" />
          {it.company}
        </p>
        <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
          {facts.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-xs text-slate-500">{label}</dt>
              <dd className="mt-0.5 break-words font-medium text-slate-900">{value}</dd>
            </div>
          ))}
        </dl>
        {sourceUrl && (
          <p className="mt-3 text-xs text-slate-500">
            Source:{" "}
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-brand-700 hover:underline">
              original listing
            </a>
          </p>
        )}
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <section aria-labelledby="about-title" className={panel}>
            <h2 id="about-title" className="text-base font-semibold text-slate-900">
              About the internship
            </h2>
            <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-700">{it.description || "No description provided."}</p>
            {it.eligibility && (
              <>
                <h3 className="mt-5 text-sm font-semibold text-slate-900">Eligibility</h3>
                <p className="mt-1 whitespace-pre-line text-sm text-slate-700">{it.eligibility}</p>
              </>
            )}
            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Skills title="Required skills" items={it.required_skills} tone="brand" />
              <Skills title="Preferred skills" items={it.preferred_skills} />
            </div>
          </section>
          <MatchPanel internship={it} />
        </div>
        <div className="min-w-0">
          <Actions internship={it} />
        </div>
      </div>
    </div>
  );
}
