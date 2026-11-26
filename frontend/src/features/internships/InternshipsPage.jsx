import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import Icon from "../../components/ui/Icon";
import BrowseInternships from "./BrowseInternships";
import SemanticSearch from "./SemanticSearch";

const VIEWS = [
  { id: "browse", label: "Browse & filter", icon: "briefcase" },
  { id: "search", label: "AI search", icon: "sparkles" },
];

// Internship discovery: keyword/filter browsing and semantic (RAG retrieval) search.
export default function InternshipsPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "search" ? "search" : "browse";

  useEffect(() => {
    const previous = document.title;
    document.title = "Internships · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const switchTo = (id) => setParams(id === "search" ? { view: "search" } : {});

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Internships</h1>
          <p className="mt-1 text-sm text-slate-600">Browse active internships, or describe what you want and let AI search find it.</p>
        </div>
        <div role="tablist" aria-label="Discovery mode" className="inline-flex rounded-lg bg-slate-100 p-1">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              role="tab"
              id={`tab-${v.id}`}
              aria-selected={view === v.id}
              aria-controls={`panel-${v.id}`}
              tabIndex={view === v.id ? 0 : -1}
              onClick={() => switchTo(v.id)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                  e.preventDefault();
                  const next = VIEWS[(VIEWS.findIndex((x) => x.id === view) + 1) % VIEWS.length];
                  switchTo(next.id);
                  requestAnimationFrame(() => document.getElementById(`tab-${next.id}`)?.focus());
                }
              }}
              className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                view === v.id ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Icon name={v.icon} className="h-4 w-4" />
              {v.label}
            </button>
          ))}
        </div>
      </header>
      <div role="tabpanel" id={`panel-${view}`} aria-labelledby={`tab-${view}`}>
        {view === "search" ? <SemanticSearch /> : <BrowseInternships />}
      </div>
    </div>
  );
}
