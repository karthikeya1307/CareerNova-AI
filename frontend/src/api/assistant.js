// Career assistant (backend/routes/assistant.py, schemas/assistant_schema.py).
// Every conversation belongs to the signed-in student; another student's id answers 404.
// The assistant only reads data. Its suggested actions are never performed by the backend.
import { api } from "./client";

export const MESSAGE_MAX = 2000; // MessageCreate.message (also reported by /capabilities limits.message_chars)
export const TITLE_MAX = 120;

// GET /assistant/capabilities -> { intents, llm{available, provider, model, disclosure, assistant_disclosure}, limits, notes }
export async function getCapabilities() {
  const { data } = await api.get("/assistant/capabilities");
  return data;
}

// GET /assistant/conversations?skip=&limit= -> { total, skip, limit, items } (most recently updated first)
export async function listConversations({ skip = 0, limit = 20, assistant } = {}) {
  const params = { skip, limit };
  if (assistant) params.assistant = assistant; // "application" | "interview": only that assistant's chats
  const { data } = await api.get("/assistant/conversations", { params });
  return data;
}

// POST /assistant/conversations { resume_id?, title? } -> ConversationOut (201, messages: [])
export async function createConversation({ resumeId, title, assistant } = {}) {
  const body = {};
  if (assistant) body.assistant = assistant;
  if (resumeId) body.resume_id = resumeId;
  if (title) body.title = title;
  const { data } = await api.post("/assistant/conversations", body);
  return data;
}

// GET /assistant/conversations/{id} -> ConversationOut with its 50 most recent messages (oldest first)
export async function getConversation(conversationId) {
  const { data } = await api.get(`/assistant/conversations/${conversationId}`);
  return data;
}

// GET /assistant/conversations/{id}/messages?before_id=&limit= -> MessageOut[] (oldest first, older than before_id)
export async function listMessages(conversationId, { beforeId, limit = 50 } = {}) {
  const params = { limit };
  if (beforeId) params.before_id = beforeId;
  const { data } = await api.get(`/assistant/conversations/${conversationId}/messages`, { params });
  return data;
}

// PATCH /assistant/conversations/{id} { title?, resume_id? } -> ConversationOut
export async function updateConversation(conversationId, body) {
  const { data } = await api.patch(`/assistant/conversations/${conversationId}`, body);
  return data;
}

// DELETE /assistant/conversations/{id}?confirm=true -> 204 (permanent, with all messages)
export async function deleteConversation(conversationId) {
  await api.delete(`/assistant/conversations/${conversationId}`, { params: { confirm: true } });
}

// POST /assistant/conversations/{id}/messages { message, use_llm, llm_consent }
//   -> { conversation_id, user_message, assistant_message } (201). 429 with Retry-After when rate limited.
export async function sendMessage(conversationId, { message, useLlm = false, consent = false }) {
  const body = useLlm ? { message, use_llm: true, llm_consent: Boolean(consent) } : { message, use_llm: false, llm_consent: false };
  const { data } = await api.post(`/assistant/conversations/${conversationId}/messages`, body);
  return data;
}
