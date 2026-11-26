import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { deleteDocument, downloadDocument, getDocument, listVersions, restoreVersion } from "../../api/documents";
import { errorMessage } from "../../api/errors";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import saveBlob from "../../utils/saveBlob";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import DocumentEditor from "./components/DocumentEditor";
import DocumentPreview from "./components/DocumentPreview";
import FactCheckPanel from "./components/FactCheckPanel";
import { documentTypeLabel, factCheckWarnings, generationLabel, VERSION_SOURCE } from "./documentFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

function AtsSummary({ report }) {
  if (!report) return null;
  const checks = report.checks || [];
  const passed = checks.filter((c) => c.passed).length;
  return (
    <section aria-labelledby="doc-ats-title" className={panel}>
      <h2 id="doc-ats-title" className="text-base font-semibold text-slate-900">
        ATS check
      </h2>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-slate-500">Resume checks passed</dt>
          <dd className="font-semibold tabular-nums">
            {passed}/{checks.length}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Required keywords found</dt>
          <dd className="font-semibold tabular-nums">
            {report.required_coverage?.present}/{report.required_coverage?.total}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Preferred keywords found</dt>
          <dd className="font-semibold tabular-nums">
            {report.preferred_coverage?.present}/{report.preferred_coverage?.total}
          </dd>
        </div>
      </dl>
      {report.suggestions?.length > 0 && (
        <ul className="mt-3 list-inside list-disc text-xs text-slate-600">
          {report.suggestions.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Versions({ documentId, currentVersion, onRestored, refreshKey }) {
  const versions = useApiResource(() => listVersions(documentId), `${documentId}:${refreshKey}`);
  const confirm = useConfirm();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const restore = async (version) => {
    if (busy) return;
    const ok = await confirm({
      title: `Restore version ${version}?`,
      message: "Its content becomes the current version. Nothing is deleted: this is added as a new version.",
      confirmLabel: "Restore",
      tone: "primary",
    });
    if (!ok) return;
    setBusy(version);
    setError(null);
    try {
      onRestored(await restoreVersion(documentId, version));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-labelledby="versions-title" className={panel}>
      <h2 id="versions-title" className="mb-3 text-base font-semibold text-slate-900">
        Versions
      </h2>
      {versions.status === "loading" || versions.status === "idle" ? (
        <CardSkeleton label="versions" lines={2} />
      ) : versions.status === "error" ? (
        <CardError error={versions.error} onRetry={versions.reload} label="versions" />
      ) : (
        <ol className="flex flex-col gap-2" aria-label="Document versions">
          {[...versions.data].reverse().map((v) => (
            <li key={v.version} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <span>
                <span className="font-medium text-slate-900">v{v.version}</span> · {VERSION_SOURCE[v.source] || v.source}
                <span className="block text-xs text-slate-500">
                  {formatDateTime(v.created_at)} · {v.warning_count} warning{v.warning_count === 1 ? "" : "s"}
                </span>
              </span>
              {v.version === currentVersion ? (
                <Badge tone="success">Current</Badge>
              ) : (
                <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => restore(v.version)} loading={busy === v.version} disabled={Boolean(busy)}>
                  Restore<span className="sr-only"> version {v.version}</span>
                </Button>
              )}
            </li>
          ))}
        </ol>
      )}
      {error && (
        <p role="alert" className="mt-2 text-xs text-red-700">
          {error}
        </p>
      )}
    </section>
  );
}

// Review a generated document: content (with resume provenance), fact check, ATS report (resumes),
// edit -> new version, version history, download (DOCX/TXT) and delete.
export default function DocumentDetailPage() {
  const { documentId } = useParams();
  const id = Number(documentId);
  const valid = Number.isInteger(id) && id > 0;
  const location = useLocation();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();
  const doc = useApiResource(() => getDocument(id), valid ? id : null, { enabled: valid });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [versionKey, setVersionKey] = useState(0);
  const justCreated = Boolean(location.state?.created);

  useEffect(() => {
    const previous = document.title;
    document.title = `${doc.data?.title || "Document"} · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [doc.data?.title]);

  const replace = (updated) => {
    doc.setData(updated);
    setEditing(false);
    setVersionKey((k) => k + 1);
  };

  const download = async (format) => {
    if (busy) return;
    setBusy(format);
    setActionError(null);
    try {
      const { blob, filename } = await downloadDocument(id, format);
      saveBlob(blob, filename);
    } catch (failure) {
      setActionError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (busy) return;
    const ok = await confirm({
      title: "Delete this document?",
      message: "The document and all its versions are permanently deleted. Your resume is not affected. This cannot be undone.",
      confirmLabel: "Delete document",
      tone: "danger",
    });
    if (!ok) return;
    setBusy("delete");
    try {
      await deleteDocument(id);
      toast.success("Document deleted.");
      navigate("/documents", { replace: true });
    } catch (failure) {
      setActionError(errorMessage(failure));
      setBusy(null);
    }
  };

  const back = (
    <Link to="/documents" className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
      <Icon name="arrowRight" className="h-4 w-4 rotate-180" />
      All documents
    </Link>
  );

  if (!valid || (doc.status === "error" && doc.error.status === 404)) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {back}
        <h1 className="text-2xl font-semibold text-slate-900">Document</h1>
        <CardEmpty title="Document not found" message="It may have been deleted." />
      </div>
    );
  }
  if (doc.status !== "success") {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {back}
        <h1 className="text-2xl font-semibold text-slate-900">Document</h1>
        {doc.status === "error" ? <CardError error={doc.error} onRetry={doc.reload} label="this document" /> : <div className={panel}><CardSkeleton label="the document" lines={8} /></div>}
      </div>
    );
  }

  const d = doc.data;
  const warnings = factCheckWarnings(d.fact_check);
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {back}
      <header className={panel}>
        <div className="flex flex-wrap gap-2">
          <Badge tone="info">{documentTypeLabel(d.document_type)}</Badge>
          <Badge>{generationLabel(d.generation_method, d.llm_provider, d.llm_model)}</Badge>
          <Badge>Version {d.current_version}</Badge>
        </div>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{d.title || documentTypeLabel(d.document_type)}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {d.internship ? (
            <>
              For{" "}
              <Link to={`/internships/${d.internship.internship_id}`} className="font-medium text-brand-700 hover:underline">
                {d.internship.title} at {d.internship.company}
              </Link>
              {!d.internship.is_active && " (no longer listed)"}
            </>
          ) : (
            "The target internship is no longer linked."
          )}
          {" · "}created {formatDateTime(d.created_at)} · updated {formatDateTime(d.updated_at)}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Built from{" "}
          {d.resume_id ? (
            <Link to={`/resumes/${d.resume_id}`} className="font-medium text-brand-700 hover:underline">
              your original resume
            </Link>
          ) : (
            "a resume that has since been deleted"
          )}
          . {d.generation_method === "deterministic" ? "Generated with the fact-based method; no AI was used." : null}
        </p>
        {(justCreated || warnings > 0) && (
          <p role="status" className={`mt-4 rounded-lg px-3 py-2 text-sm ${warnings ? "bg-amber-50 text-amber-900" : "bg-brand-50 text-brand-900"}`}>
            {justCreated ? "Draft ready. " : ""}
            {warnings
              ? `Review the ${warnings} fact-check item${warnings === 1 ? "" : "s"} below before you use this document.`
              : "Read it through and adjust the wording before you download it."}
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => download("docx")} loading={busy === "docx"} disabled={Boolean(busy) || editing}>
            Download DOCX
          </Button>
          <Button variant="secondary" onClick={() => download("txt")} loading={busy === "txt"} disabled={Boolean(busy) || editing}>
            Download TXT
          </Button>
          {d.content_json && !editing && (
            <Button variant="secondary" onClick={() => setEditing(true)} disabled={Boolean(busy)}>
              <Icon name="edit" className="h-4 w-4" />
              Edit wording
            </Button>
          )}
          <Button variant="danger" onClick={remove} loading={busy === "delete"} disabled={Boolean(busy)}>
            Delete
          </Button>
        </div>
        {actionError && (
          <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            {actionError}
          </p>
        )}
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="content-title" className={`${panel} min-w-0`}>
          <h2 id="content-title" className="mb-4 text-base font-semibold text-slate-900">
            {editing ? "Edit wording" : "Preview"}
          </h2>
          {editing ? <DocumentEditor document={d} onSaved={(updated) => { replace(updated); toast.success("Saved as a new version."); }} onCancel={() => setEditing(false)} /> : <DocumentPreview document={d} />}
        </section>
        <div className="flex min-w-0 flex-col gap-6">
          <section aria-labelledby="fact-title" className={panel}>
            <h2 id="fact-title" className="mb-3 text-base font-semibold text-slate-900">
              Fact check
            </h2>
            <FactCheckPanel factCheck={d.fact_check} />
          </section>
          {d.document_type === "resume" && <AtsSummary report={d.ats_report} />}
          <Versions documentId={id} currentVersion={d.current_version} onRestored={(updated) => { replace(updated); toast.success("Version restored."); }} refreshKey={versionKey} />
        </div>
      </div>
    </div>
  );
}
