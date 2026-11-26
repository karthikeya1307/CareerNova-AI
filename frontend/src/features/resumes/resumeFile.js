import { RESUME_EXTENSIONS, RESUME_MAX_BYTES } from "../../api/resumes";

// Same rules as backend/routes/resumes.py, checked before anything is uploaded.
export function validateResumeFile(file) {
  if (!file) return "Choose a file to upload.";
  const name = file.name.toLowerCase();
  if (!RESUME_EXTENSIONS.some((ext) => name.endsWith(ext))) return "Upload a PDF, Word (.docx) or OpenDocument (.odt) file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > RESUME_MAX_BYTES) return "Resume files must be 5 MB or smaller.";
  return null;
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
