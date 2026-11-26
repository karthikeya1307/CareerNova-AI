import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getApplicationDashboard, SORT_FIELDS, STATUSES } from "../../api/applications";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import useApiResource from "../../hooks/useApiResource";
import ApplicationList from "./components/ApplicationList";
import ApplicationSummary from "./components/ApplicationSummary";
import NewApplicationForm from "./components/NewApplicationForm";
import RemindersPanel from "./components/RemindersPanel";
import SavedInternships from "./components/SavedInternships";
import TrashPanel from "./components/TrashPanel";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";
const TABS = [
  { id: "applications", label: "Applications" },
  { id: "saved", label: "Saved internships" },
  { id: "reminders", label: "Reminders" },
  { id: "trash", label: "Trash" },
];

// Filters live in the URL: ?tab=&status=A&status=B&q=&sort=&order=&skip=
function readFilters(params) {
  const sort = params.get("sort");
  const skip = Number(params.get("skip"));
  return {
    statuses: params.getAll("status").filter((s) => STATUSES.includes(s)),
    q: params.get("q") || "",
    sort: SORT_FIELDS.includes(sort) ? sort : "updated_at",
    order: params.get("order") === "asc" ? "asc" : "desc",
    skip: Number.isInteger(skip) && skip > 0 ? skip : 0,
  };
}

export default function ApplicationsPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.id === params.get("tab")) ? params.get("tab") : "applications";
  const filters = readFilters(params);
  const summary = useApiResource(getApplicationDashboard, "applications-dashboard");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    const previous = document.title;
    document.title = "Applications · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const setTab = (id) => {
    const next = new URLSearchParams();
    if (id !== "applications") next.set("tab", id);
    setParams(next);
  };
  const setFilters = (change) => {
    const merged = { ...filters, ...change };
    const next = new URLSearchParams();
    for (const s of merged.statuses) next.append("status", s);
    if (merged.q) next.set("q", merged.q);
    if (merged.sort !== "updated_at") next.set("sort", merged.sort);
    if (merged.order !== "desc") next.set("order", merged.order);
    if (merged.skip) next.set("skip", String(merged.skip));
    setParams(next);
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Applications</h1>
          <p className="mt-1 text-sm text-slate-600">Track where you applied, each status change, company interview rounds and your reminders.</p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)}>
            <Icon name="edit" className="h-4 w-4" />
            Add an application
          </Button>
        )}
      </header>

      {adding && (
        <section aria-labelledby="new-app-title" className={panel}>
          <h2 id="new-app-title" className="mb-3 text-base font-semibold text-slate-900">
            Add an application
          </h2>
          <NewApplicationForm onCancel={() => setAdding(false)} />
        </section>
      )}

      <section aria-labelledby="summary-title" className={panel}>
        <h2 id="summary-title" className="mb-4 text-base font-semibold text-slate-900">
          Overview
        </h2>
        <ApplicationSummary summary={summary} onStatus={(status) => setFilters({ statuses: [status], q: "", skip: 0 })} />
      </section>

      <section className={panel} aria-label="Your applications and saved internships">
        <div role="tablist" aria-label="Application sections" className="mb-5 flex flex-wrap gap-1 border-b border-slate-200">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                tab === t.id ? "border-brand-600 text-brand-700" : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === "applications" && <ApplicationList key={`${filters.q}`} filters={filters} onFilters={setFilters} />}
          {tab === "saved" && <SavedInternships onChanged={summary.reload} />}
          {tab === "reminders" && <RemindersPanel onChanged={summary.reload} />}
          {tab === "trash" && <TrashPanel onChanged={summary.reload} />}
        </div>
      </section>
    </div>
  );
}
