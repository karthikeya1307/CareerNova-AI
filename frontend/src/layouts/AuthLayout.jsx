import { Link, Outlet } from "react-router-dom";
import BrandMark from "../components/brand/BrandMark";
import Icon from "../components/ui/Icon";
import { APP_DESCRIPTION, APP_TAGLINE } from "../config/brand";

// What the product actually does, shown beside the auth forms on large screens.
const HIGHLIGHTS = [
  { icon: "document", title: "Resume insights", text: "Parsing, a readiness score and ATS keyword checks for each role." },
  { icon: "target", title: "Matched opportunities", text: "Internships ranked by how well your skills fit, with the gaps explained." },
  { icon: "chart", title: "Skill roadmaps", text: "What to learn next, with official resources and progress you track." },
  { icon: "mic", title: "Interview practice", text: "Question sets, answer feedback and an application tracker in one place." },
];

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-slate-50 lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <aside className="relative isolate hidden overflow-hidden bg-navy-900 px-12 py-12 text-white lg:flex lg:flex-col lg:justify-between xl:px-16">
        {/* Decorative background: indigo/violet glows and a faint grid. */}
        <div aria-hidden="true" className="cn-grid-pattern pointer-events-none absolute inset-0 -z-10" />
        <div aria-hidden="true" className="pointer-events-none absolute -right-32 -top-32 -z-10 h-[28rem] w-[28rem] rounded-full bg-brand-600/40 blur-3xl motion-safe:animate-float" />
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-40 -left-24 -z-10 h-[30rem] w-[30rem] rounded-full bg-violet-600/25 blur-3xl" />

        <Link to="/" className="relative w-fit rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">
          <BrandMark inverted />
        </Link>

        <div className="relative max-w-lg">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-brand-200">
            <Icon name="sparkles" className="h-3.5 w-3.5" />
            AI-powered career companion
          </p>
          {/* A paragraph, not a heading: each page's own <h1> must be the first heading. */}
          <p className="mt-5 font-display text-4xl font-bold leading-[1.1] tracking-tight xl:text-5xl">
            <span className="cn-gradient-text">{APP_TAGLINE}</span>
          </p>
          <p className="mt-4 text-base leading-relaxed text-slate-300">{APP_DESCRIPTION}</p>
          <ul className="mt-10 grid gap-4 sm:grid-cols-2">
            {HIGHLIGHTS.map((item) => (
              <li key={item.title} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-sm">
                <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-500/25 text-brand-200">
                  <Icon name={item.icon} className="h-5 w-5" />
                </span>
                <span className="mt-3 block text-sm font-semibold">{item.title}</span>
                <span className="mt-1 block text-xs leading-relaxed text-slate-300">{item.text}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-slate-400">For students and job seekers building their careers.</p>
      </aside>

      <main className="flex min-h-screen flex-col items-center justify-center px-4 py-10 sm:px-6">
        <div className="w-full max-w-md motion-safe:animate-fade-in-up">
          <Link to="/" className="mb-8 inline-flex rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-600 lg:hidden">
            <BrandMark />
          </Link>
          <div className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-card-hover sm:p-8">
            <Outlet />
          </div>
          <p className="mt-6 text-center text-xs text-slate-500">
            Need to check the service?{" "}
            <Link to="/health" className="underline underline-offset-2 hover:text-slate-700">
              System status
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
