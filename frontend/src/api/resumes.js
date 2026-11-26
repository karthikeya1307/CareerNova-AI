// Resume endpoints (backend/routes/resumes.py). Every route resolves the resume through
// get_owned_resume(), so another user's resume id answers 404 exactly like a missing one.
import { api } from "./client";
import { normalizeError } from "./errors";

// Upload limits enforced by the backend (MAX_FILE_SIZE, PDF/DOCX content checks).
export const RESUME_MAX_BYTES = 5 * 1024 * 1024;
export const RESUME_EXTENSIONS = [".pdf", ".docx", ".odt"];
export const RESUME_ACCEPT =
  ".pdf,.docx,.odt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.oasis.opendocument.text";

// GET /resumes/ -> ResumeListItem[] { resume_id, filename, file_type, status, uploaded_at }, newest first.
export async function listResumes() {
  const { data } = await api.get("/resumes/");
  return data;
}

// POST /resumes/upload (multipart "file") -> ResumeUploadResponse (201). Parsing happens inside
// this request: 422 means the file was rejected/unparseable and nothing was stored.
// `onProgress(percent)` reports bytes sent (0-100); parsing continues after 100%.
export async function uploadResume(file, { onProgress } = {}) {
  const form = new FormData();
  // Pass the name explicitly: the backend requires a filename and stores it with the resume.
  form.append("file", file, file.name);
  const { data } = await api.post("/resumes/upload", form, {
    onUploadProgress: onProgress
      ? (event) => {
          if (event.total) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
        }
      : undefined,
  });
  return data;
}

// GET /resumes/{id} -> ResumeDetailResponse (latest *completed* extraction).
// 404 "Parsed resume information not found" when no extraction succeeded yet.
export async function getResumeDetail(resumeId) {
  const { data } = await api.get(`/resumes/${resumeId}`);
  return data;
}

// GET /resumes/{id}/skills -> { resume_id, skills: [{ skill_id, name, category, source }] }
export async function getResumeSkills(resumeId) {
  const { data } = await api.get(`/resumes/${resumeId}/skills`);
  return data;
}

// POST /resumes/{id}/reparse -> ResumeDetailResponse. 422 = parsing failed (the earlier extraction
// stays in use); 404 = stored file missing.
export async function reparseResume(resumeId) {
  const { data } = await api.post(`/resumes/${resumeId}/reparse`);
  return data;
}

// GET /resumes/{id}/readiness -> general resume readiness (0-100, readiness-v1): {score, label, categories,
// strengths, weaknesses, recommendations, parsing, disclaimer, corrected}. 409 when nothing was parsed yet.
export async function getResumeReadiness(resumeId) {
  const { data } = await api.get(`/resumes/${resumeId}/readiness`);
  return data;
}

// GET /resumes/{id}/analysis -> parsing confidence per section, missing fields, dates, warnings.
export async function getResumeAnalysis(resumeId) {
  const { data } = await api.get(`/resumes/${resumeId}/analysis`);
  return data;
}

// PUT /resumes/{id}/extracted-data (ResumeParsedData) -> ResumeDetailResponse with corrected=true.
// Saved as a new extraction; a later re-parse returns to the parser's version.
export async function saveResumeCorrections(resumeId, data) {
  const { data: body } = await api.put(`/resumes/${resumeId}/extracted-data`, data);
  return body;
}

// RFC 6266 filename from Content-Disposition (filename*=UTF-8'' preferred over filename=).
export function filenameFromDisposition(header) {
  if (!header) return null;
  const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* fall through */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

// GET /resumes/{id}/download -> the original file (owner only). Returns { blob, filename }.
// Blob.text() where available, FileReader otherwise (older engines / jsdom).
function blobText(blob) {
  if (typeof blob?.text === "function") return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

// With responseType "blob" an error body (FastAPI JSON) also arrives as a Blob. Every status except
// 401 is returned to this function (401 still goes through the client's refresh-and-retry), so the
// JSON can be decoded and the backend's message ("Stored resume file not found") reaches the user.
export async function downloadResume(resumeId, fallbackName) {
  const response = await api.get(`/resumes/${resumeId}/download`, {
    responseType: "blob",
    validateStatus: (status) => status !== 401,
  });
  if (response.status >= 400) {
    let data = null;
    try {
      data = JSON.parse(await blobText(response.data));
    } catch {
      /* not JSON: fall back to the default message for the status */
    }
    throw normalizeError({ response: { status: response.status, data, headers: response.headers } });
  }
  const filename = filenameFromDisposition(response.headers?.["content-disposition"]) || fallbackName || "resume";
  return { blob: response.data, filename };
}

// DELETE /resumes/{id} -> 204. Permanent; callers must confirm with the user first.
export async function deleteResume(resumeId) {
  await api.delete(`/resumes/${resumeId}`);
}

// PATCH /resumes/{id} { label?, is_preferred? } -> ResumeListItem (with version, label, is_preferred).
// Marking one version preferred un-marks the others; only parsed resumes can be preferred (409 otherwise).
export async function updateResumeVersion(resumeId, changes) {
  const { data } = await api.patch(`/resumes/${resumeId}`, changes);
  return data;
}

// GET /resumes/compare?a=&b=&role=&internship_id= -> comparison of two of my versions (compare-v1):
// contact, skills, sections (added/removed/modified/unchanged), keywords, metrics (readiness, role fit,
// ATS for one internship), verdict with measured reasons, improvements, weaknesses and recommendations.
export async function compareResumes({ a, b, role, internshipId }) {
  const params = { a, b };
  if (role) params.role = role;
  if (internshipId) params.internship_id = internshipId;
  const { data } = await api.get("/resumes/compare", { params });
  return data;
}

// "V2 · Internship-focused" / "V2 · cv.pdf"
export function versionName(resume) {
  if (!resume) return "";
  return `${resume.version ? `V${resume.version} · ` : ""}${resume.label || resume.filename}`;
}
