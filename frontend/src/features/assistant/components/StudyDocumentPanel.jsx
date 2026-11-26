import { useId, useRef, useState } from "react";
import { errorMessage } from "../../../api/errors";
import { deleteStudyDocument, uploadStudyDocument, validateStudyFile } from "../../../api/studyDocuments";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";

const describe = (d) =>
  [d.file_type?.toUpperCase(), d.page_count ? `${d.page_count} page${d.page_count === 1 ? "" : "s"}` : null,
   d.section_count ? `${d.section_count} section${d.section_count === 1 ? "" : "s"}` : null,
   `${(d.char_count ?? 0).toLocaleString()} characters`].filter(Boolean).join(" · ");

// Upload a PDF/DOCX and choose which document this chat answers from. Errors come from the backend's
// checks (type, real content, size, empty/corrupted/scanned) and are shown as returned.
export const MAX_ATTACHED = 5; // backend doc_agent.MAX_ATTACHED

// Upload PDF/DOCX files and choose which ones this chat answers from (up to MAX_ATTACHED, searched together).
// onAttach(ids) receives the full new list; [] stops using documents.
export default function StudyDocumentPanel({ documents, attachedIds = [], onAttach, onClose, busy }) {
  const inputId = useId();
  const input = useRef(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const list = documents.data || [];

  const choose = async (file) => {
    setError(null);
    setNotice(null);
    const problem = validateStudyFile(file);
    if (problem) return setError(problem);
    setProgress(0);
    try {
      const doc = await uploadStudyDocument(file, { onProgress: setProgress });
      setNotice(`Extracted ${describe(doc)} from ${doc.filename}.${doc.warnings?.length ? ` ${doc.warnings.join(" ")}` : ""}`);
      documents.reload();
      await onAttach([...attachedIds.filter((x) => x !== doc.document_id), doc.document_id].slice(-MAX_ATTACHED));
    } catch (failure) {
      const detail = failure?.response?.data?.detail;
      setError(typeof detail === "object" && detail?.message ? detail.message : errorMessage(failure));
    } finally {
      setProgress(null);
      if (input.current) input.current.value = "";
    }
    return undefined;
  };

  const remove = async (doc) => {
    setError(null);
    try {
      if (attachedIds.includes(doc.document_id)) await onAttach(attachedIds.filter((x) => x !== doc.document_id));
      await deleteStudyDocument(doc.document_id);
      documents.reload();
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };

  return (
    <section aria-label="Study documents" className="rounded-2xl border border-brand-100 bg-brand-50/40 p-3 motion-safe:animate-fade-in">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Ask questions about a document</h3>
          <p className="text-xs text-slate-600">
            Upload course notes or a job description (PDF or DOCX, up to 10 MB). Answers come only from the document, with page or section references.
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close study documents" className="rounded-lg p-1 text-slate-500 hover:bg-white hover:text-slate-800">
          <Icon name="close" className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label htmlFor={inputId} className="sr-only">
          Choose a PDF or DOCX file
        </label>
        <input
          ref={input}
          id={inputId}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="sr-only"
          onChange={(e) => choose(e.target.files?.[0])}
        />
        <Button onClick={() => input.current?.click()} loading={progress !== null} disabled={busy} className="py-1.5 text-xs">
          {progress === null && <Icon name="upload" className="h-3.5 w-3.5" />}
          {progress === null ? "Upload PDF or DOCX" : progress < 100 ? `Uploading ${progress}%` : "Extracting text…"}
        </Button>
        <span className="text-[11px] text-slate-500">Scanned PDFs (images) can't be read - OCR isn't available.</span>
      </div>

      {error && (
        <p role="alert" className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="mt-2 rounded-lg bg-mint-50 px-3 py-2 text-xs text-mint-800">
          {notice}
        </p>
      )}

      {documents.status === "success" && list.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5" aria-label="Your documents">
          {list.map((d) => {
            const active = attachedIds.includes(d.document_id);
            return (
              <li key={d.document_id} className={`flex flex-wrap items-center gap-2 rounded-xl border bg-white px-3 py-2 ${active ? "border-brand-300" : "border-slate-200"}`}>
                <Icon name="document" className="h-4 w-4 shrink-0 text-brand-600" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold text-slate-900" title={d.filename}>
                    {d.filename}
                  </span>
                  <span className="block text-[11px] text-slate-500">{describe(d)}</span>
                </span>
                {active ? (
                  <>
                    <Badge tone="info">In use</Badge>
                    <Button
                      variant="ghost"
                      onClick={() => onAttach(attachedIds.filter((x) => x !== d.document_id))}
                      disabled={busy}
                      className="min-h-0 px-2 py-1 text-xs"
                      aria-label={`Stop using ${d.filename} in this chat`}
                    >
                      Remove
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="secondary"
                    onClick={() => onAttach([...attachedIds, d.document_id])}
                    disabled={busy || attachedIds.length >= MAX_ATTACHED}
                    className="min-h-0 px-2.5 py-1 text-xs"
                  >
                    Use in this chat
                  </Button>
                )}
                <Button variant="ghost" onClick={() => remove(d)} disabled={busy} className="min-h-0 px-2 py-1 text-xs text-red-700" aria-label={`Delete ${d.filename}`}>
                  Delete
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
