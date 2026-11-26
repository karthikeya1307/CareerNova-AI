// Resume and cover-letter customization endpoints (backend/routes/documents.py). Every document is
// owned by the signed-in user; another user's id answers 404. Generation happens on the backend:
// the browser never sends resume data to any AI provider.
import { api } from "./client";
import { normalizeError } from "./errors";
import { filenameFromDisposition } from "./resumes";

// backend/schemas/document_schema.py ResumeOptionsIn (defaults and bounds).
export const RESUME_OPTIONS = {
  max_skills: { default: 15, min: 5, max: 30, label: "Skills to include" },
  max_projects: { default: 3, min: 0, max: 6, label: "Projects to include" },
  max_experience: { default: 4, min: 0, max: 8, label: "Experience entries" },
  max_bullets: { default: 4, min: 1, max: 6, label: "Bullet points per entry" },
};
export const TONES = ["formal", "concise"]; // CreateCoverLetterRequest.tone
export const MAX_EMPHASIS = 10; // emphasize_skills max_length

// GET /documents/llm-status -> { available, provider, model, disclosure }
export async function getLlmStatus() {
  const { data } = await api.get("/documents/llm-status");
  return data;
}

// AI fields are only sent when the student opted in AND accepted the disclosure.
function llmFields(useLlm, consent) {
  return useLlm ? { use_llm: true, llm_consent: Boolean(consent) } : { use_llm: false, llm_consent: false };
}

// POST /documents/resume { resume_id, internship_id, options, use_llm, llm_consent } -> DocumentResponse (201)
export async function createResumeDocument({ resumeId, internshipId, options, useLlm = false, consent = false }) {
  const { data } = await api.post("/documents/resume", {
    resume_id: resumeId,
    internship_id: internshipId,
    options,
    ...llmFields(useLlm, consent),
  });
  return data;
}

// POST /documents/cover-letter { resume_id, internship_id, tone, emphasize_skills, use_llm, llm_consent }
export async function createCoverLetter({ resumeId, internshipId, tone = "formal", emphasizeSkills = [], useLlm = false, consent = false }) {
  const { data } = await api.post("/documents/cover-letter", {
    resume_id: resumeId,
    internship_id: internshipId,
    tone,
    emphasize_skills: emphasizeSkills,
    ...llmFields(useLlm, consent),
  });
  return data;
}

// GET /documents?type&resume_id&internship_id -> DocumentListItem[] (newest update first)
export async function listDocuments({ type, resumeId, internshipId } = {}) {
  const params = {};
  if (type) params.type = type;
  if (resumeId) params.resume_id = resumeId;
  if (internshipId) params.internship_id = internshipId;
  const { data } = await api.get("/documents", { params });
  return data;
}

// GET /documents/{id} -> DocumentResponse
export async function getDocument(documentId) {
  const { data } = await api.get(`/documents/${documentId}`);
  return data;
}

// PATCH /documents/{id} { title?, content } -> DocumentResponse. Saves a new "edited" version; the
// backend fact-checks the edit and returns warnings (edits are always saved).
export async function updateDocument(documentId, { title, content }) {
  const body = { content };
  if (title !== undefined) body.title = title;
  const { data } = await api.patch(`/documents/${documentId}`, body);
  return data;
}

// GET /documents/{id}/versions -> VersionItem[] { version, source, warning_count, created_at }
export async function listVersions(documentId) {
  const { data } = await api.get(`/documents/${documentId}/versions`);
  return data;
}

// POST /documents/{id}/versions/{v}/restore -> DocumentResponse (adds a "restored" version)
export async function restoreVersion(documentId, version) {
  const { data } = await api.post(`/documents/${documentId}/versions/${version}/restore`);
  return data;
}

// DELETE /documents/{id} -> 204 (permanent; confirm first)
export async function deleteDocument(documentId) {
  await api.delete(`/documents/${documentId}`);
}

function blobText(blob) {
  if (typeof blob?.text === "function") return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

// GET /documents/{id}/download?format=docx|txt -> file. Non-401 errors come back here so the JSON
// error body (a Blob) can be decoded; 401 still goes through the client's refresh-and-retry.
export async function downloadDocument(documentId, format = "docx") {
  const response = await api.get(`/documents/${documentId}/download`, {
    params: { format },
    responseType: "blob",
    validateStatus: (s) => s !== 401,
  });
  if (response.status >= 400) {
    let data = null;
    try {
      data = JSON.parse(await blobText(response.data));
    } catch {
      /* default message for the status */
    }
    throw normalizeError({ response: { status: response.status, data, headers: response.headers } });
  }
  const filename = filenameFromDisposition(response.headers?.["content-disposition"]) || `document.${format}`;
  return { blob: response.data, filename };
}
