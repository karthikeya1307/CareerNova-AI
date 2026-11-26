import { useId, useRef, useState } from "react";
import { RESUME_ACCEPT, uploadResume } from "../../../api/resumes";
import { errorMessage } from "../../../api/errors";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";
import { formatBytes, validateResumeFile } from "../resumeFile";

// Drag-and-drop or browse resume upload.
//   * Validates type/size like the backend before sending anything.
//   * One upload at a time: further drops/clicks are ignored while uploading.
//   * Shows real byte progress, then "Reading your resume…" while the backend parses (the parse
//     happens inside the same request, so there is no separate server-side processing state).
export default function ResumeUploader({ onUploaded, compact = false, label = "Upload resume" }) {
  const input = useRef(null);
  const busy = useRef(false);
  const hintId = useId();
  const [dragging, setDragging] = useState(false);
  // { phase: "idle" | "uploading" | "success" | "error", file?, progress?, message? }
  const [state, setState] = useState({ phase: "idle" });
  const uploading = state.phase === "uploading";

  const start = async (file) => {
    if (busy.current) return; // prevent duplicate submissions
    const problem = validateResumeFile(file);
    if (problem) {
      setState({ phase: "error", message: problem });
      return;
    }
    busy.current = true;
    setState({ phase: "uploading", file, progress: 0 });
    try {
      const uploaded = await uploadResume(file, {
        onProgress: (progress) => setState((s) => (s.phase === "uploading" ? { ...s, progress } : s)),
      });
      setState({ phase: "success", message: `${uploaded.filename} was uploaded and parsed.` });
      onUploaded?.(uploaded);
    } catch (failure) {
      setState({ phase: "error", message: errorMessage(failure) });
    } finally {
      busy.current = false;
    }
  };

  const onInput = (event) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow choosing the same file again
    if (file) start(file);
  };

  const onDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    if (uploading) return;
    const files = event.dataTransfer?.files;
    if (files?.length > 1) {
      setState({ phase: "error", message: "Drop one resume at a time." });
      return;
    }
    if (files?.[0]) start(files[0]);
  };

  const onDragOver = (event) => {
    event.preventDefault();
    if (!uploading) setDragging(true);
  };

  const parsing = uploading && state.progress >= 100;

  return (
    <div className="flex flex-col gap-3">
      <div
        data-testid="resume-dropzone"
        onDragOver={onDragOver}
        onDragEnter={onDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        aria-busy={uploading || undefined}
        className={`flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed text-center transition-colors ${
          compact ? "px-4 py-5" : "px-6 py-10"
        } ${dragging ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-slate-50/60"}`}
      >
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white text-brand-600 shadow-sm ring-1 ring-slate-200">
          <Icon name="upload" className="h-5 w-5" />
        </span>
        {!compact && (
          <p className="text-sm text-slate-700">
            <span className="font-medium text-slate-900">Drag and drop your resume here</span>, or browse your files.
          </p>
        )}
        <input
          ref={input}
          type="file"
          accept={RESUME_ACCEPT}
          className="sr-only"
          tabIndex={-1}
          aria-label="Resume file"
          onChange={onInput}
          data-testid="resume-file-input"
        />
        <Button onClick={() => input.current?.click()} disabled={uploading} aria-describedby={hintId}>
          <Icon name="document" className="h-4 w-4" />
          {compact ? label : "Browse files"}
        </Button>
        <p id={hintId} className="text-xs text-slate-500">
          PDF, DOCX or ODT · up to 5 MB · one file at a time
        </p>
      </div>

      {uploading && (
        <div className="rounded-lg border border-slate-200 bg-white p-3" role="status" aria-live="polite">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate font-medium text-slate-800">{state.file.name}</span>
            <span className="shrink-0 text-xs text-slate-500">{formatBytes(state.file.size)}</span>
          </div>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={parsing ? undefined : state.progress}
            aria-valuetext={parsing ? "Reading your resume" : `${state.progress}% uploaded`}
          >
            <div
              className={`h-full rounded-full bg-brand-500 transition-all ${parsing ? "animate-pulse" : ""}`}
              style={{ width: `${parsing ? 100 : Math.max(state.progress, 4)}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-slate-600">
            {parsing ? "Reading your resume… this can take a few seconds." : `Uploading… ${state.progress}%`}
          </p>
        </div>
      )}
      {state.phase === "success" && (
        <p role="status" className="flex items-center gap-2 rounded-lg bg-mint-50 px-3 py-2 text-sm text-mint-800">
          <Icon name="check" className="h-4 w-4 shrink-0" />
          {state.message}
        </p>
      )}
      {state.phase === "error" && (
        <p role="alert" className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <span className="font-medium">Upload failed.</span> {state.message}
          </span>
        </p>
      )}
    </div>
  );
}
