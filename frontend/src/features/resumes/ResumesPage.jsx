import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { deleteResume, downloadResume, getResumeDetail, listResumes, reparseResume, updateResumeVersion, versionName } from "../../api/resumes";
import { errorMessage, normalizeError } from "../../api/errors";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDate } from "../../utils/dates";
import saveBlob from "../../utils/saveBlob";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import { resumeStatus } from "../dashboard/format";
import ReadinessPanel from "./components/ReadinessPanel";
import ResumeDetail from "./components/ResumeDetail";
import ResumeEditor from "./components/ResumeEditor";
import ResumeUploader from "./components/ResumeUploader";
import { latestParsed } from "./resumeData";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card";

export const DELETE_MESSAGE =
  "This permanently deletes the file, its extracted information and skills, and the match results, " +
  "skill-gap recommendations and career-assistant messages based on it. Generated documents, interview " +
  "sessions and conversations are kept but no longer linked to this resume. This cannot be undone.";

function ResumeList({ resumes, selectedId }) {
  const parsed = latestParsed(resumes);
  return (
    <ul className="flex flex-col gap-2" aria-label="Your resumes">
      {resumes.map((resume, index) => {
        const status = resumeStatus(resume.status);
        const selected = resume.resume_id === selectedId;
        return (
          <li key={resume.resume_id}>
            <Link
              to={`/resumes/${resume.resume_id}`}
              aria-current={selected ? "page" : undefined}
              className={`flex items-start gap-3 rounded-xl border p-3 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                selected ? "border-brand-300 bg-brand-50/60" : "border-slate-200 bg-white hover:bg-slate-50"
              }`}
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white text-xs font-semibold uppercase text-brand-700 ring-1 ring-slate-200">
                {resume.file_type}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-slate-900" title={resume.filename}>
                  {resume.version ? <span className="mr-1 text-brand-700">V{resume.version}</span> : null}
                  {resume.label || resume.filename}
                </span>
                <span className="block truncate text-xs text-slate-500">
                  {resume.label ? `${resume.filename} · ` : ""}Uploaded {formatDate(resume.uploaded_at)}
                </span>
                <span className="mt-1.5 flex flex-wrap gap-1.5">
                  <Badge tone={status.tone}>{status.label}</Badge>
                  {resume.is_preferred && <Badge tone="ai">Preferred</Badge>}
                  {index === 0 && <Badge tone="info">Latest</Badge>}
                  {parsed?.resume_id === resume.resume_id && <Badge tone="success">Used for matching</Badge>}
                </span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export default function ResumesPage() {
  const { resumeId: param } = useParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();
  const resumes = useApiResource(listResumes, "resumes");
  // The previous list stays in use while it reloads (after upload/re-parse/delete), so the selected
  // resume and its details are not torn down and re-fetched.
  const list = resumes.status === "error" ? null : resumes.data;
  const firstLoad = (resumes.status === "loading" || resumes.status === "idle") && !resumes.data;
  const requestedId = param ? Number(param) : null;
  const selected = list ? (requestedId ? list.find((r) => r.resume_id === requestedId) : list[0]) || null : null;
  const selectedId = selected?.resume_id ?? null;

  const detail = useApiResource(() => getResumeDetail(selectedId), selectedId, { enabled: Boolean(selectedId) });
  const [action, setAction] = useState(null); // "download" | "reparse" | "delete" while running
  const [actionError, setActionError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [renaming, setRenaming] = useState(null);       // label being edited
  const [versionBusy, setVersionBusy] = useState(null); // "label" | "preferred"
  // Bumped whenever the extracted data changes (re-parse, corrections) so readiness is recalculated.
  const [dataVersion, setDataVersion] = useState(0);

  useEffect(() => {
    setActionError(null);
    setEditing(false);
    setRenaming(null);
  }, [selectedId]);

  // Rename this version and/or make it the preferred (current) resume. Older versions are always kept.
  const saveVersion = async (changes, kind) => {
    setVersionBusy(kind);
    setActionError(null);
    try {
      await updateResumeVersion(selectedId, changes);
      setRenaming(null);
      resumes.reload();
      toast.success(kind === "preferred" ? "Preferred resume updated. Matching and the assistants use it now." : "Version name saved.");
    } catch (failure) {
      setActionError(normalizeError(failure));
    } finally {
      setVersionBusy(null);
    }
  };

  useEffect(() => {
    const previous = document.title;
    document.title = "Resumes · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const onUploaded = (uploaded) => {
    if (uploaded.duplicate_of?.length) {
      const which = uploaded.duplicate_of.map((id) => `#${id}`).join(", ");
      toast.error(
        uploaded.duplicate_kind === "identical_file"
          ? `${uploaded.filename} is the same file as resume ${which}. It was uploaded again; delete the copy you don't need.`
          : `${uploaded.filename} has the same content as resume ${which}. It was uploaded again; delete the copy you don't need.`,
      );
    } else {
      toast.success(`${uploaded.filename} uploaded and parsed.`);
    }
    resumes.reload();
    navigate(`/resumes/${uploaded.resume_id}`);
  };

  const run = async (name, task) => {
    if (action) return;
    setAction(name);
    setActionError(null);
    try {
      await task();
    } catch (failure) {
      setActionError({ name, message: failure?.userMessage || errorMessage(failure) });
    } finally {
      setAction(null);
    }
  };

  const onDownload = () =>
    run("download", async () => {
      const { blob, filename } = await downloadResume(selected.resume_id, selected.filename);
      saveBlob(blob, filename);
    });

  const onReparse = async () => {
    // Re-parsing replaces the student's saved corrections with the parser's reading of the file.
    if (detail.data?.corrected) {
      const ok = await confirm({
        title: "Re-parse and replace your corrections?",
        message:
          "This resume uses details you corrected. Re-parsing reads the original file again and the parser's version replaces your corrections. The original file is not changed.",
        confirmLabel: "Re-parse anyway",
        tone: "danger",
      });
      if (!ok) return;
    }
    await reparse();
  };

  const reparse = () =>
    run("reparse", async () => {
      try {
        const updated = await reparseResume(selected.resume_id);
        detail.setData(updated);
        setEditing(false);
        setDataVersion((v) => v + 1);
        resumes.reload();
        toast.success("Resume re-parsed. The extracted information is up to date.");
      } catch (failure) {
        const err = normalizeError(failure);
        if (err.status === 422) {
          throw Object.assign(new Error("reparse failed"), {
            userMessage: `Re-parsing failed: ${err.message} Your previously extracted information is still in use.`,
          });
        }
        throw failure;
      }
    });

  const onDelete = async () => {
    const ok = await confirm({
      title: `Delete ${selected.filename}?`,
      message: DELETE_MESSAGE,
      confirmLabel: "Delete resume",
      tone: "danger",
      requireText: "DELETE",
    });
    if (!ok) return;
    await run("delete", async () => {
      await deleteResume(selected.resume_id);
      toast.success(`${selected.filename} was deleted.`);
      resumes.reload();
      navigate("/resumes", { replace: true });
    });
  };

  let detailPanel;
  if (!list) {
    detailPanel = null;
  } else if (!list.length) {
    detailPanel = null;
  } else if (!selected) {
    detailPanel = (
      <CardEmpty
        title="Resume not found"
        message="This resume doesn't exist or has been deleted."
        action={
          <Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">
            Show my latest resume
          </Link>
        }
      />
    );
  } else {
    // 404 "Parsed resume information not found" = no successful extraction yet (re-parse can help);
    // 404 "Resume not found" = deleted or not this user's resume.
    const notFound = detail.status === "error" && detail.error?.status === 404;
    const parsedMissing = notFound && /parsed/i.test(detail.error.message);
    detailPanel = (
      <>
        <header className="flex flex-col gap-3 border-b border-slate-100 pb-4 2xl:flex-row 2xl:items-start 2xl:justify-between">
          <div className="min-w-0">
            {renaming !== null ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  saveVersion({ label: renaming.trim() || null }, "label");
                }}
                className="flex flex-wrap items-center gap-2"
                aria-label="Rename this version"
              >
                <label htmlFor="version-label" className="sr-only">Version name</label>
                <input
                  id="version-label"
                  value={renaming}
                  maxLength={120}
                  placeholder="e.g. Internship-focused"
                  onChange={(e) => setRenaming(e.target.value)}
                  className="cn-input min-w-0 flex-1 py-1.5"
                />
                <Button type="submit" loading={versionBusy === "label"} className="py-1.5 text-xs">Save</Button>
                <Button variant="ghost" onClick={() => setRenaming(null)} className="py-1.5 text-xs">Cancel</Button>
              </form>
            ) : (
              <h2 className="truncate text-lg font-semibold text-slate-900" title={selected.filename}>
                {versionName(selected)}
              </h2>
            )}
            <p className="text-xs text-slate-500">
              {selected.filename} · Resume #{selected.resume_id}
              {selected.is_preferred ? " · your preferred version" : ""}
            </p>
            {renaming === null && (
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => setRenaming(selected.label || "")} className="min-h-0 px-2 py-1 text-xs">
                  <Icon name="edit" className="h-3.5 w-3.5" />
                  Rename version
                </Button>
                {selected.status === "completed" && !selected.is_preferred && (
                  <Button variant="ghost" onClick={() => saveVersion({ is_preferred: true }, "preferred")} loading={versionBusy === "preferred"} className="min-h-0 px-2 py-1 text-xs">
                    <Icon name="check" className="h-3.5 w-3.5" />
                    Set as preferred
                  </Button>
                )}
                {selected.is_preferred && (
                  <Button variant="ghost" onClick={() => saveVersion({ is_preferred: false }, "preferred")} loading={versionBusy === "preferred"} className="min-h-0 px-2 py-1 text-xs">
                    Unset preferred
                  </Button>
                )}
                {selected.status === "completed" && (list || []).filter((r) => r.status === "completed").length > 1 && (
                  <Link
                    to={`/resumes/compare?a=${(list.find((r) => r.status === "completed" && r.resume_id !== selected.resume_id) || {}).resume_id}&b=${selected.resume_id}`}
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-50"
                  >
                    <Icon name="chart" className="h-3.5 w-3.5" />
                    Compare with another version
                  </Link>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {selected.status === "completed" && (
              <Link
                to={`/documents?resume=${selected.resume_id}`}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
              >
                <Icon name="edit" className="h-4 w-4" />
                Tailor this resume
              </Link>
            )}
            <Button variant="secondary" onClick={onDownload} loading={action === "download"} disabled={Boolean(action)}>
              {action !== "download" && <Icon name="arrowRight" className="h-4 w-4 rotate-90" />}
              Download
            </Button>
            <Button variant="secondary" onClick={onReparse} loading={action === "reparse"} disabled={Boolean(action)}>
              {action !== "reparse" && <Icon name="refresh" className="h-4 w-4" />}
              {action === "reparse" ? "Re-parsing…" : "Re-parse"}
            </Button>
            <Button variant="danger" onClick={onDelete} loading={action === "delete"} disabled={Boolean(action)}>
              Delete
            </Button>
          </div>
        </header>
        {actionError && (
          <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            {actionError.message}
          </p>
        )}
        <div className="mt-5">
          {detail.status === "loading" || detail.status === "idle" ? (
            <CardSkeleton label="the extracted information" lines={6} />
          ) : parsedMissing ? (
            <CardEmpty
              title="No extracted information yet"
              message="This resume hasn't been parsed successfully. Use Re-parse to read the stored file again."
            />
          ) : notFound ? (
            <CardEmpty title="Resume not found" message="It may have been deleted. Refresh the list to see your current resumes." />
          ) : detail.status === "error" ? (
            <CardError error={detail.error} onRetry={detail.reload} label="the extracted information" />
          ) : editing ? (
            <ResumeEditor
              detail={detail.data}
              onCancel={() => setEditing(false)}
              onSaved={(updated) => {
                detail.setData(updated);
                setEditing(false);
                setDataVersion((v) => v + 1);
                toast.success("Corrections saved. Matching, documents and the assistant now use your version.");
              }}
            />
          ) : (
            <div className="flex flex-col gap-5">
              <ReadinessPanel resumeId={selected.resume_id} version={dataVersion} />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-slate-600">
                  {detail.data.corrected ? (
                    <Badge tone="info">Corrected by you</Badge>
                  ) : (
                    "Extracted from the file. Check it and correct anything that was read incorrectly."
                  )}
                </p>
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  <Icon name="edit" className="h-4 w-4" />
                  Edit details
                </Button>
              </div>
              <ResumeDetail detail={detail.data} />
            </div>
          )}
        </div>
      </>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Resumes</h1>
        <p className="mt-1 text-sm text-slate-600">
          Keep several versions of your resume, name them, choose your preferred one and compare any two. Your preferred version
          (or, without one, the latest successfully parsed resume) is used for matching, skill gaps and the assistants.
        </p>
      </header>

      <section aria-label="Upload a resume" className={panel}>
        <ResumeUploader onUploaded={onUploaded} />
      </section>

      {firstLoad ? (
        <div className={panel}>
          <CardSkeleton label="your resumes" lines={4} />
        </div>
      ) : resumes.status === "error" ? (
        <div className={panel}>
          <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />
        </div>
      ) : !list.length ? (
        <div className={panel}>
          <CardEmpty title="No resumes yet" message="Upload a PDF, DOCX or ODT resume above to see what we extract from it." />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <section aria-labelledby="resume-list-title" className={`${panel} min-w-0 self-start`}>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 id="resume-list-title" className="text-base font-semibold text-slate-900">
                Your versions <span className="text-sm font-normal text-slate-500">({list.length})</span>
              </h2>
              {list.filter((r) => r.status === "completed").length > 1 && (
                <Link to="/resumes/compare" className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-50">
                  <Icon name="chart" className="h-3.5 w-3.5" />
                  Compare versions
                </Link>
              )}
            </div>
            <ResumeList resumes={list} selectedId={selectedId} />
          </section>
          <section aria-label="Resume details" className={`${panel} min-w-0`}>
            {detailPanel}
          </section>
        </div>
      )}
    </div>
  );
}
