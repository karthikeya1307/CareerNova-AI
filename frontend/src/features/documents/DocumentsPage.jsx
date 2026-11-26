import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listDocuments } from "../../api/documents";
import Badge from "../../components/ui/Badge";
import Icon from "../../components/ui/Icon";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import CreateDocumentForm from "./components/CreateDocumentForm";
import { documentTypeLabel, generationLabel } from "./documentFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";
const FILTERS = [
  { id: "", label: "All" },
  { id: "resume", label: "Resumes" },
  { id: "cover_letter", label: "Cover letters" },
];

function History({ filter, onFilter }) {
  const docs = useApiResource(() => listDocuments({ type: filter || undefined }), `docs:${filter}`);
  return (
    <section aria-labelledby="history-title" className={panel}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 id="history-title" className="text-base font-semibold text-slate-900">
          Your documents
        </h2>
        <div role="group" aria-label="Filter documents" className="inline-flex gap-1 rounded-lg bg-slate-100 p-1">
          {FILTERS.map((f) => (
            <button
              key={f.id || "all"}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => onFilter(f.id)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                filter === f.id ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {docs.status === "loading" || docs.status === "idle" ? (
        <CardSkeleton label="your documents" lines={4} />
      ) : docs.status === "error" ? (
        <CardError error={docs.error} onRetry={docs.reload} label="your documents" />
      ) : !docs.data.length ? (
        <CardEmpty title="No documents yet" message="Generated resumes and cover letters will appear here." />
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Generated documents">
          {docs.data.map((d) => (
            <li key={d.document_id}>
              <Link
                to={`/documents/${d.document_id}`}
                className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
              >
                {/* Stacked at every width: the history sits in a narrow side column on large screens. */}
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-slate-900">{d.title || documentTypeLabel(d.document_type)}</span>
                  <span className="block text-xs text-slate-500">
                    {d.internship ? `${d.internship.title} at ${d.internship.company}` : "Internship no longer linked"} · updated {formatDateTime(d.updated_at)}
                  </span>
                </span>
                <span className="flex flex-wrap gap-1.5">
                  <Badge tone="info">{documentTypeLabel(d.document_type)}</Badge>
                  <Badge>{generationLabel(d.generation_method)}</Badge>
                  <Badge>v{d.current_version}</Badge>
                  {d.warning_count > 0 ? <Badge tone="warning">{d.warning_count} to review</Badge> : <Badge tone="success">No warnings</Badge>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Document workspace: create tailored resumes / cover letters and browse generated documents.
// Query: ?type=resume|cover_letter&internship=ID&resume=ID pre-fill the form; ?show= filters the list.
export default function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.some((f) => f.id === params.get("show")) ? params.get("show") || "" : "";

  useEffect(() => {
    const previous = document.title;
    document.title = "Documents · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const onFilter = (value) => {
    const next = new URLSearchParams(params);
    if (value) next.set("show", value);
    else next.delete("show");
    setParams(next);
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Documents</h1>
        <p className="mt-1 text-sm text-slate-600">
          Tailor your resume and write cover letters for a specific internship. Everything comes from your own resume — nothing is invented — and you
          review each document before downloading it.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="create-title" className={`${panel} min-w-0`}>
          <h2 id="create-title" className="mb-4 flex items-center gap-2 text-base font-semibold text-slate-900">
            <Icon name="sparkles" className="h-5 w-5 text-brand-600" />
            Create a document
          </h2>
          <CreateDocumentForm
            key={`${params.get("type")}|${params.get("internship")}|${params.get("resume")}`}
            initialType={params.get("type")}
            initialInternshipId={params.get("internship")}
            initialResumeId={params.get("resume")}
          />
        </section>
        <div className="min-w-0">
          <History filter={filter} onFilter={onFilter} />
        </div>
      </div>
    </div>
  );
}
