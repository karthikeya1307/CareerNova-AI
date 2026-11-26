// Display helpers for interview sessions. Labels only; every score and label comes from the backend.

export const CATEGORY_LABEL = {
  technical: "Technical",
  project: "Project / experience",
  behavioral: "Behavioural",
  internship: "Internship-specific",
};
export const categoryLabel = (c) => CATEGORY_LABEL[c] || (c ? c.charAt(0).toUpperCase() + c.slice(1) : "Question");

export const difficultyLabel = (d) => (d ? d.charAt(0).toUpperCase() + d.slice(1) : null);

export const MODE_LABEL = { practice: "Practice", mock: "Mock interview" };
export const modeLabel = (m) => MODE_LABEL[m] || "Practice";

const STATUS = {
  started: { label: "Not started", tone: "neutral" },
  in_progress: { label: "In progress", tone: "info" },
  completed: { label: "Completed", tone: "success" },
  abandoned: { label: "Abandoned", tone: "neutral" },
};
export const sessionStatus = (s) => STATUS[s] || { label: s || "Unknown", tone: "neutral" };
export const isOpen = (s) => s === "started" || s === "in_progress";

// Backend score labels (answer_evaluator.LABELS): Excellent >= 80, Good >= 65, Fair >= 45, else Needs work.
// Only the tone is chosen here; the label text is always the backend's.
export function scoreTone(score) {
  if (score == null) return "neutral";
  if (score >= 65) return "success";
  if (score >= 45) return "warning";
  return "danger";
}
export const formatScore = (score) => (score == null ? "—" : `${Math.round(score * 10) / 10}`);

export const STAR_LABEL = { situation: "Situation", task: "Task", action: "Action", result: "Result" };

export const CAP_LABEL = {
  short_answer: "Score capped: the answer is very short",
  keyword_list: "Score capped: the answer reads like a list of keywords",
};

export const NOTICE_TITLE = {
  internship_questions_replaced: "Internship questions replaced",
  fewer_questions: "Fewer questions than requested",
};

export const FEEDBACK_SOURCE = { rubric: "Rubric feedback (no AI)", llm: "AI feedback (rubric score)" };
