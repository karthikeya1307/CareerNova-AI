import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { WORK_MODES } from "../../api/internships";
import { exploreJobs } from "../../api/matches";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import useApiResource from "../../hooks/useApiResource";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import JobInsights, { CATEGORY, CategoryBadge } from "./JobInsights";

const PAGE = 20;
const field = "cn-input";

function JobCard({ item }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const it = item.internship;
  return (
    <li className="rounded-xl border border-slate-200/80 bg-white">
      <div className="flex flex-wrap items-center gap-3 p-4">
        <div className="w-full min-w-0 sm:w-auto sm:flex-1">
          <Link to={`/internships/${it.internship_id}`} className="font-medium text-slate-900 hover:text-brand-700 hover:underline">
            {it.title}
          </Link>
          <p className="truncate text-xs text-slate-500">{[it.company, it.location, it.work_mode, it.domain].filter(Boolean).join(" · ")}</p>
        </div>
        {item.insights && (
          <div className="flex items-center gap-2">
            <CategoryBadge insights={item.insights} />
            <span className="text-sm tabular-nums text-slate-700">
              Skill Match <strong>{item.insights.skill_match == null ? "—" : `${item.insights.skill_match}%`}</strong>
            </span>
          </div>
        )}
        {item.insights && (
          <Button variant="ghost" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)} className="px-2 py-1 text-xs">
            {open ? "Hide details" : "Show details"}
            <span className="sr-only"> for {it.title}</span>
            <Icon name="chevronDown" className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
          </Button>
        )}
      </div>
      {open && item.insights && (
        <div id={panelId} className="border-t border-slate-100 p-4">
          <JobInsights insights={item.insights} />
        </div>
      )}
    </li>
  );
}

// Explore Any Job: every open opportunity, not limited to the resume's best matches. With a parsed
// resume each job also shows insights (skill match, eligibility, readiness, category).
export default function ExploreJobs({ resumeId }) {
  const [draft, setDraft] = useState({ q: "", location: "", workMode: "" });
  const [query, setQuery] = useState({ q: "", location: "", workMode: "" });
  const [category, setCategory] = useState("");
  const [skip, setSkip] = useState(0);
  const key = `explore:${resumeId || "none"}:${query.q}:${query.location}:${query.workMode}:${category}:${skip}`;
  const page = useApiResource(() => exploreJobs({ resumeId, ...query, category, skip, limit: PAGE }), key);
  const data = page.data;

  const submit = (event) => {
    event.preventDefault();
    setSkip(0);
    setQuery(draft);
  };

  return (
    <div className="flex flex-col gap-4">
      <form role="search" onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor="explore-q" className="text-sm font-medium text-slate-700">
            Search role, company or domain
          </label>
          <input id="explore-q" type="search" value={draft.q} maxLength={100} onChange={(e) => setDraft({ ...draft, q: e.target.value })} className={field} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="explore-location" className="text-sm font-medium text-slate-700">
            Location
          </label>
          <input id="explore-location" value={draft.location} maxLength={150} onChange={(e) => setDraft({ ...draft, location: e.target.value })} className={field} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="explore-mode" className="text-sm font-medium text-slate-700">
            Work mode
          </label>
          <select id="explore-mode" value={draft.workMode} onChange={(e) => setDraft({ ...draft, workMode: e.target.value })} className={field}>
            <option value="">Any</option>
            {WORK_MODES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>

      {resumeId && data?.category_counts && (
        <div role="group" aria-label="Filter by category" className="flex flex-wrap gap-2">
          {[["", "All", null], ...Object.entries(CATEGORY).map(([k, v]) => [k, v.label, data.category_counts[k]])].map(
            ([value, label, count]) => (
              <button
                key={value || "all"}
                type="button"
                aria-pressed={category === value}
                onClick={() => {
                  setSkip(0);
                  setCategory(value);
                }}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${category === value ? "border-brand-400 bg-brand-50 text-brand-800" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
              >
                {label}
                {value && count != null ? ` (${count})` : ""}
              </button>
            ),
          )}
        </div>
      )}
      {!resumeId && (
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Upload a resume to see your skill match, eligibility and readiness for each job. You can still browse every opening.
        </p>
      )}

      {(page.status === "loading" || page.status === "idle") && !data ? (
        <CardSkeleton label="opportunities" lines={4} />
      ) : page.status === "error" ? (
        <CardError error={page.error} onRetry={page.reload} label="opportunities" />
      ) : !data.items.length ? (
        <CardEmpty title="No opportunities found" message="Try a different search or clear the filters." />
      ) : (
        <>
          <p className="text-xs text-slate-500">
            {data.total} open opportunit{data.total === 1 ? "y" : "ies"} · listings come from the curated dataset <Badge>sample data</Badge>
          </p>
          <ul className="flex flex-col gap-3" aria-label="Opportunities">
            {data.items.map((item) => (
              <JobCard key={item.internship.internship_id} item={item} />
            ))}
          </ul>
          <nav aria-label="Opportunity pages" className="flex items-center justify-between text-sm text-slate-600">
            <span>
              {skip + 1}–{skip + data.items.length} of {data.total}
            </span>
            <span className="flex gap-2">
              <Button variant="secondary" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - PAGE))}>
                Previous
              </Button>
              <Button variant="secondary" disabled={skip + data.items.length >= data.total} onClick={() => setSkip(skip + PAGE)}>
                Next
              </Button>
            </span>
          </nav>
        </>
      )}
    </div>
  );
}
