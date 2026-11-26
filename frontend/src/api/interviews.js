// Interview preparation (backend/routes/interviews.py, schemas/interview_schema.py).
// Every endpoint is authenticated and scoped to the signed-in student by the backend; another
// student's session answers 404 "Interview session not found".
import { api } from "./client";

// CreateSessionRequest options (the backend has no endpoint listing them; these mirror the schema).
export const MODES = [
  { id: "practice", label: "Practice", hint: "Model answers and key points are visible while you answer." },
  { id: "mock", label: "Mock interview", hint: "Model answers stay hidden until you answer or reveal them. Optional time limit per question." },
];
export const DIFFICULTIES = ["mixed", "easy", "medium", "hard"];
// QuestionMix: per-category limits; the total must be 1-15.
export const MIX = {
  technical: { label: "Technical", min: 0, max: 10, default: 3 },
  project: { label: "Project / experience", min: 0, max: 5, default: 2 },
  behavioral: { label: "Behavioural", min: 0, max: 5, default: 2 },
  internship: { label: "Internship-specific", min: 0, max: 5, default: 1 },
};
export const MIX_TOTAL = { min: 1, max: 15 };
export const TIME_LIMIT = { min: 30, max: 900 }; // seconds per question, mock mode only
export const ANSWER_MAX = 5000;
export const SESSION_STATUSES = ["started", "in_progress", "completed", "abandoned"];

const aiFields = (useLlm, consent) => (useLlm ? { use_llm: true, llm_consent: Boolean(consent) } : { use_llm: false, llm_consent: false });

// GET /interviews/question-bank/version -> bank statistics (versions, skills covered, counts by difficulty).
export async function getQuestionBankInfo() {
  const { data } = await api.get("/interviews/question-bank/version");
  return data;
}

// POST /interviews/sessions -> SessionOut (201)
export async function createSession({ resumeId, internshipId = null, targetRole = null, mode, mix, difficulty, timeLimitSeconds = null, useLlm = false, consent = false }) {
  const { data } = await api.post("/interviews/sessions", {
    resume_id: resumeId,
    internship_id: internshipId,
    ...(targetRole ? { target_role: targetRole } : {}),
    mode,
    mix,
    difficulty,
    time_limit_seconds: mode === "mock" ? timeLimitSeconds : null,
    ...aiFields(useLlm, consent),
  });
  return data;
}

// GET /interviews/sessions?status= -> SessionListItem[] (newest first)
export async function listSessions({ status } = {}) {
  const { data } = await api.get("/interviews/sessions", { params: status ? { status } : {} });
  return data;
}

// GET /interviews/sessions/{id} -> SessionOut
export async function getSession(sessionId) {
  const { data } = await api.get(`/interviews/sessions/${sessionId}`);
  return data;
}

// POST /interviews/sessions/{id}/questions/{qid}/answers -> AnswerOut (201). 409 when the session is closed.
export async function submitAnswer(sessionId, questionId, { answerText, timeTakenSeconds = null, useLlm = false, consent = false }) {
  const body = { answer_text: answerText, time_taken_seconds: timeTakenSeconds };
  Object.assign(body, useLlm ? { use_llm_feedback: true, llm_consent: Boolean(consent) } : { use_llm_feedback: false, llm_consent: false });
  const { data } = await api.post(`/interviews/sessions/${sessionId}/questions/${questionId}/answers`, body);
  return data;
}

// GET /interviews/sessions/{id}/questions/{qid}/answers -> AnswerOut[] (every attempt)
export async function listAnswers(sessionId, questionId) {
  const { data } = await api.get(`/interviews/sessions/${sessionId}/questions/${questionId}/answers`);
  return data;
}

// POST /interviews/sessions/{id}/questions/{qid}/reveal -> QuestionOut (mock mode: shows the model answer)
export async function revealQuestion(sessionId, questionId) {
  const { data } = await api.post(`/interviews/sessions/${sessionId}/questions/${questionId}/reveal`);
  return data;
}

// POST /interviews/sessions/{id}/complete -> SessionOut with the backend's summary. 409 if already closed.
export async function completeSession(sessionId) {
  const { data } = await api.post(`/interviews/sessions/${sessionId}/complete`);
  return data;
}

// DELETE /interviews/sessions/{id} -> 204
export async function deleteSession(sessionId) {
  await api.delete(`/interviews/sessions/${sessionId}`);
}

// AI availability and the privacy disclosure come from GET /documents/llm-status (the backend's
// consent error points there for interviews too).
export { getLlmStatus } from "./documents";
