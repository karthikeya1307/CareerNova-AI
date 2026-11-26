import { useEffect, useRef, useState } from "react";
import { getIndexStatus, rebuildIndex } from "../../api/admin";
import { normalizeError } from "../../api/errors";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useConfirm } from "../../context/ConfirmContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardSkeleton } from "../dashboard/components/DashboardCard";
import { humanize } from "../dashboard/format";
import { AdminError, AdminHeader, adminPanel } from "./adminShared";

function Row({ label, children }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-slate-100 py-2 sm:flex-row sm:justify-between sm:gap-4">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="break-all text-sm font-medium text-slate-900 sm:text-right">{children}</dd>
    </div>
  );
}

// FAISS search index: GET /admin/index/status (read-only) and POST /admin/index/rebuild.
// The rebuild runs synchronously on the server; the backend reports no progress, only the result.
export default function AdminIndexPage() {
  const confirm = useConfirm();
  const status = useApiResource(getIndexStatus, "admin-index-status");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const lock = useRef(false);

  useEffect(() => {
    const previous = document.title;
    document.title = "Search index · Admin · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const rebuild = async () => {
    if (lock.current) return;
    const ok = await confirm({
      title: "Rebuild the search index?",
      message:
        "This re-reads every active internship, computes new embeddings and replaces the FAISS index used by semantic search, " +
        "matching and the assistant. It can take several minutes and uses significant server resources. Deactivated internships are removed " +
        "from the index. The request waits until it finishes; there is no progress indicator. Internship data itself is not changed.",
      confirmLabel: "Rebuild index",
      tone: "danger",
      requireText: "REBUILD",
    });
    if (!ok || lock.current) return;
    lock.current = true;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await rebuildIndex());
      status.reload();
    } catch (failure) {
      setError(normalizeError(failure));
    } finally {
      lock.current = false;
      setRunning(false);
    }
  };

  const s = status.data;
  const counts = Object.entries(s?.document_status_counts || {});
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <AdminHeader title="Search index" description="Status of the FAISS index behind semantic internship search, matching and the assistant." />

      <section aria-labelledby="index-status-title" className={adminPanel}>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id="index-status-title" className="text-base font-semibold text-slate-900">
            Current status
          </h2>
          <Button variant="ghost" onClick={status.reload} disabled={status.status === "loading"} className="px-2 py-1 text-xs">
            <Icon name="refresh" className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
        {status.status === "error" ? (
          <AdminError error={status.error} onRetry={status.reload} label="the index status" />
        ) : !s ? (
          <CardSkeleton label="the index status" lines={5} />
        ) : (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              <Badge tone={s.built ? "success" : "danger"}>{s.built ? "Built" : "Not built"}</Badge>
              <Badge tone={s.stale ? "warning" : "success"}>{s.stale ? "Out of date" : "Up to date"}</Badge>
              <Badge tone={s.model_matches_configuration ? "success" : "warning"}>
                {s.model_matches_configuration ? "Model matches configuration" : "Model differs from configuration"}
              </Badge>
            </div>
            <dl>
              <Row label="Last built">{s.built_at ? formatDateTime(s.built_at) : "Never"}</Row>
              <Row label="Indexed vectors">{s.indexed_vectors}</Row>
              <Row label="Active internships">{s.active_internships}</Row>
              <Row label="Index model">{s.model_name ? `${s.model_name}${s.model_revision ? ` (${s.model_revision})` : ""}` : "—"}</Row>
              <Row label="Configured model">{s.configured_model}</Row>
              <Row label="Vector dimension">{s.dimension ?? "—"}</Row>
            </dl>
            {counts.length > 0 && (
              <div className="mt-3">
                <h3 className="text-sm font-medium text-slate-700">Knowledge-base documents by status</h3>
                <ul className="mt-2 flex flex-wrap gap-2" aria-label="Documents by status">
                  {counts.map(([k, v]) => (
                    <li key={k}>
                      <Badge>
                        {humanize(k)}: {v}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="rebuild-title" className={adminPanel}>
        <h2 id="rebuild-title" className="text-base font-semibold text-slate-900">
          Rebuild
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Rebuild after adding, editing, deactivating or reactivating internships, or when the status says the index is out of date. You'll be asked to type
          REBUILD to confirm.
        </p>
        <div className="mt-3">
          <Button variant="danger" onClick={rebuild} loading={running}>
            {running ? "Rebuilding… (this can take a while)" : "Rebuild search index"}
          </Button>
        </div>
        {running && (
          <p role="status" className="mt-3 text-sm text-slate-600">
            The server is rebuilding the index. Keep this page open; the result appears when it finishes.
          </p>
        )}
        {error && (
          <div role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            <p className="font-medium">
              {error.status === 409 ? "A rebuild is already running." : error.status === 503 ? "Embeddings are unavailable." : "The rebuild failed."}
            </p>
            <p>{error.message}</p>
            {error.status === 409 && <p className="mt-0.5">Wait for it to finish, then refresh the status.</p>}
          </div>
        )}
        {result && (
          <div role="status" className="mt-3 rounded-lg bg-mint-50 px-3 py-2 text-sm text-mint-900">
            <p className="font-medium">Index rebuilt.</p>
            <p>
              {result.indexed} internships indexed, {result.deactivated_documents} deactivated documents removed. Model {result.model_name} ({result.dimension}{" "}
              dimensions), built {formatDateTime(result.built_at)}.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
