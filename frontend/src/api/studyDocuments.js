// Study documents for document Q&A (backend/routes/study_documents.py). Each student sees only their
// own documents; another student's id answers 404. Only extracted text is stored, never the file.
import { api } from "./client";

export const STUDY_EXTENSIONS = ["pdf", "docx"];
export const STUDY_MAX_BYTES = 10 * 1024 * 1024; // backend study_documents.MAX_BYTES

// Same checks the backend makes first (extension + size); the backend also checks the real content.
export function validateStudyFile(file) {
  if (!file) return "Choose a PDF or DOCX file.";
  const extension = file.name.toLowerCase().split(".").pop();
  if (!STUDY_EXTENSIONS.includes(extension)) return "Only PDF and DOCX files are supported.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > STUDY_MAX_BYTES) return "The file is larger than 10 MB.";
  return null;
}

// POST /study-documents (multipart "file") -> { document_id, filename, file_type, page_count, section_count,
//   char_count, chunk_count, title, warnings[], preview, created_at } (201). 409 duplicate, 413 too large,
//   415 unsupported type, 422 empty / corrupted / scanned (no OCR).
export async function uploadStudyDocument(file, { onProgress } = {}) {
  const form = new FormData();
  form.append("file", file, file.name);
  const { data } = await api.post("/study-documents", form, {
    onUploadProgress: onProgress
      ? (event) => {
          if (event.total) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
        }
      : undefined,
  });
  return data;
}

// GET /study-documents -> summaries, newest first
export async function listStudyDocuments() {
  const { data } = await api.get("/study-documents");
  return data;
}

// DELETE /study-documents/{id} -> 204
export async function deleteStudyDocument(documentId) {
  await api.delete(`/study-documents/${documentId}`);
}

// PUT /assistant/conversations/{id}/study-document { document_ids: [...] } -> ConversationOut
// Interview Preparation Assistant chats only; up to 5 documents; [] stops using documents.
export async function attachStudyDocuments(conversationId, documentIds) {
  const { data } = await api.put(`/assistant/conversations/${conversationId}/study-document`, { document_ids: documentIds });
  return data;
}
