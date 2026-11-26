import { useEffect } from "react";
import Avatar from "../../components/ui/Avatar";
import { Link } from "react-router-dom";
import {
  getApplicationSummary, getAtsReport, getInterviewProgress, getLatestMatches, getResumeSkills, getSkillGap,
  listConversations, listInterviewSessions, listRecentApplications, listResumes, listSkillGapRecommendations,
} from "../../api/dashboard";
import { getResumeReadiness } from "../../api/resumes";
import Icon from "../../components/ui/Icon";
import { APP_TAGLINE, pageTitle } from "../../config/brand";
import { useAuth } from "../../context/AuthContext";
import useApiResource from "../../hooks/useApiResource";
import ApplicationsCard from "./components/ApplicationsCard";
import AssistantCard from "./components/AssistantCard";
import AtsCard from "./components/AtsCard";
import HeroStats from "./components/HeroStats";
import InterviewCard from "./components/InterviewCard";
import MatchCard from "./components/MatchCard";
import ResumeCard from "./components/ResumeCard";
import SkillsCard from "./components/SkillsCard";
import { latestParsed } from "../resumes/resumeData";
import { bestMatch, greeting } from "./format";

const heroLink =
  "inline-flex min-h-[2.5rem] items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white";

// The one most useful next step, decided only from the student's real data.
function nextStep({ resumes, latest, matches, best, appSummary }) {
  if (resumes.status !== "success") return null;
  if (!latest) return { text: "Upload your resume to unlock matches, ATS checks and skill plans.", to: "/resumes", action: "Upload resume" };
  if (latest.status !== "completed") return { text: "Your latest resume couldn't be read. Upload a PDF or DOCX version.", to: "/resumes", action: "Open resumes" };
  if (matches.status === "success" && !best) return { text: "Find the internships that fit your resume best.", to: "/matches", action: "Find matches" };
  if (best && appSummary.status === "success" && appSummary.data?.total_applications === 0) {
    return { text: `Tailor your resume for ${best.internship.title} and start your first application.`, to: `/internships/${best.internship.internship_id}`, action: "View internship" };
  }
  if (best) return { text: "Close your skill gap for your best match with a step-by-step roadmap.", to: `/skill-gaps/internships/${best.internship.internship_id}`, action: "Open roadmap" };
  return null;
}

// Student dashboard. Every section loads independently (its own loading / empty / error + retry),
// so one failing endpoint never blanks the page. Resume-dependent sections wait for the latest
// parsed resume; ATS and skill-gap sections also wait for the best match.
export default function DashboardPage() {
  const { user } = useAuth();

  const resumes = useApiResource(listResumes, "resumes");
  // Matching, skills, ATS and skill gaps use the latest *successfully parsed* resume.
  const latest = resumes.status === "success" ? latestParsed(resumes.data) || resumes.data?.[0] || null : null;
  const resumeId = latest?.status === "completed" ? latest.resume_id : null;

  const skills = useApiResource(() => getResumeSkills(resumeId), resumeId, { enabled: Boolean(resumeId) });
  const matches = useApiResource(() => getLatestMatches(resumeId), resumeId, { enabled: Boolean(resumeId) });
  const recommendations = useApiResource(() => listSkillGapRecommendations(resumeId), resumeId, { enabled: Boolean(resumeId) });
  const readiness = useApiResource(() => getResumeReadiness(resumeId), resumeId ? `readiness:${resumeId}` : null, { enabled: Boolean(resumeId) });

  const best = matches.status === "success" ? bestMatch(matches.data) : null;
  const internshipId = best?.internship?.internship_id ?? null;
  const pairKey = resumeId && internshipId ? `${resumeId}:${internshipId}` : null;
  const ats = useApiResource(() => getAtsReport(resumeId, internshipId), pairKey, { enabled: Boolean(pairKey) });
  const gap = useApiResource(() => getSkillGap(resumeId, internshipId), pairKey, { enabled: Boolean(pairKey) });

  const progress = useApiResource(getInterviewProgress, "progress");
  const interviewSessions = useApiResource(listInterviewSessions, "interview-sessions");
  const appSummary = useApiResource(getApplicationSummary, "applications-summary");
  const recentApps = useApiResource(() => listRecentApplications(5), "applications-recent");
  const conversations = useApiResource(() => listConversations(3), "conversations");

  useEffect(() => {
    const previous = document.title;
    document.title = pageTitle("Dashboard");
    return () => {
      document.title = previous;
    };
  }, []);

  const firstName = user?.first_name || "there";
  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  const step = nextStep({ resumes, latest, matches, best, appSummary });

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 lg:gap-8">
      <section aria-labelledby="dashboard-greeting" className="cn-hero px-5 py-7 sm:px-8 sm:py-9">
        <div aria-hidden="true" className="cn-grid-pattern pointer-events-none absolute inset-0 -z-10" />
        <div aria-hidden="true" className="pointer-events-none absolute -right-20 -top-24 -z-10 h-72 w-72 rounded-full bg-brand-500/30 blur-3xl motion-safe:animate-float" />

        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-brand-200">
              <Icon name="sparkles" className="h-3.5 w-3.5" />
              Your career command center
            </p>
            <div className="mt-4 flex items-center gap-3">
              <Avatar user={user} size="lg" className="ring-2 ring-white/30" />
              <h1 id="dashboard-greeting" className="text-2xl font-bold tracking-tight text-white sm:text-4xl">
                {greeting()}, {firstName}
              </h1>
            </div>
            <p className="mt-2 text-base font-medium sm:text-lg">
              <span className="cn-gradient-text">{APP_TAGLINE}</span>
            </p>
            <p className="mt-2 max-w-xl text-sm text-slate-300">
              Your resume, best match, skills, interview practice and applications — all in one place.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {isAdmin && (
              <Link to="/admin" className={`${heroLink} border border-white/20 text-white hover:bg-white/10`}>
                <Icon name="chart" className="h-4 w-4" />
                Admin overview
              </Link>
            )}
            <Link to="/internships" className={`${heroLink} border border-white/20 text-white hover:bg-white/10`}>
              <Icon name="briefcase" className="h-4 w-4" />
              Browse internships
            </Link>
            <Link to="/interview-prep" className={`${heroLink} bg-white text-navy-900 shadow-sm hover:bg-brand-50`}>
              <Icon name="mic" className="h-4 w-4" />
              Practise interviews
            </Link>
          </div>
        </div>

        <HeroStats readiness={readiness} resumeId={resumeId} best={best} matches={matches} appSummary={appSummary} progress={progress} />

        {step && (
          <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-mint-300/20 bg-mint-400/10 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-start gap-2.5 text-sm text-mint-50">
              <Icon name="arrowRight" className="mt-0.5 h-4 w-4 shrink-0 text-mint-300" />
              <span>
                <span className="font-semibold text-white">Next step: </span>
                {step.text}
              </span>
            </p>
            <Link to={step.to} className={`${heroLink} w-fit shrink-0 bg-mint-300 py-1.5 text-navy-900 hover:bg-mint-200`}>
              {step.action}
            </Link>
          </div>
        )}
      </section>

      {/* Ordered by importance. Explicit minmax(0,1fr) columns + min-w-0 cards: long names truncate instead of widening the page. */}
      <div className="grid grid-cols-1 gap-6 md:grid-flow-row-dense md:grid-cols-2 xl:grid-cols-3">
        <ResumeCard resumes={resumes} onUploaded={resumes.reload} />
        <MatchCard resume={latest} matches={matches} onMatched={matches.setData} />
        <AtsCard resume={latest} best={best} ats={ats} />
        <div className="min-w-0 md:col-span-2 xl:col-span-2 [&>section]:h-full">
          <SkillsCard resume={latest} skills={skills} best={best} gap={gap} recommendations={recommendations} />
        </div>
        <InterviewCard progress={progress} sessions={interviewSessions} />
        <div className="min-w-0 md:col-span-2 xl:col-span-2 [&>section]:h-full">
          <ApplicationsCard summary={appSummary} recent={recentApps} />
        </div>
        <AssistantCard conversations={conversations} />
      </div>
    </div>
  );
}
