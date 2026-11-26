// Display helpers for the career assistant. Every link points to an existing frontend page and uses
// ids exactly as the backend returned them; anything that cannot be mapped is shown without a link.

const positiveId = (value) => (/^\d+$/.test(String(value ?? "")) && Number(value) > 0 ? Number(value) : null);

export const SOURCE_TYPE_LABEL = {
  resume: "Resume",
  resume_fact: "Resume entry",
  internship: "Internship",
  match_result: "Match result",
  skill_gap_recommendation: "Skill-gap recommendation",
  learning_plan: "Learning plan",
  document: "Generated document",
  interview_session: "Practice interview",
  interview_progress: "Interview practice progress",
  question_bank: "Question bank",
  application: "Application",
  application_interview: "Company interview",
  application_reminder: "Reminder",
  dashboard: "Application dashboard",
  bookmark: "Saved internship",
  product_doc: "Product guide",
  career_track: "Career track",
  study_document: "Your document",
};
export const sourceTypeLabel = (type) => SOURCE_TYPE_LABEL[type] || "Source";

// SourceOut {type, id, label, available} -> frontend route, or null when there is no page for it.
// available === false means the record was deleted, closed or trashed since the answer: no link.
export function sourceLink(source) {
  if (!source || source.available === false) return null;
  const id = positiveId(source.id);
  switch (source.type) {
    case "resume":
      return id ? `/resumes/${id}` : "/resumes";
    case "resume_fact": {
      const resumeId = positiveId(String(source.id).split(":")[0]);
      return resumeId ? `/resumes/${resumeId}` : null;
    }
    case "internship":
      return id ? `/internships/${id}` : null;
    case "match_result":
      return "/matches";
    case "skill_gap_recommendation":
    case "learning_plan":
      return "/skill-gaps";
    case "document":
      return id ? `/documents/${id}` : null;
    case "interview_session":
      return id ? `/interview-prep/sessions/${id}` : null;
    case "interview_progress":
    case "question_bank":
      return "/interview-prep";
    case "application":
      return id ? `/applications/${id}` : null;
    case "application_reminder":
      return "/applications?tab=reminders";
    case "bookmark":
      return "/applications?tab=saved";
    case "dashboard":
      return "/applications";
    case "career_track":
      return /^[a-z0-9-]+$/.test(String(source.id)) ? `/career-tracks/${source.id}` : "/career-tracks";
    default:
      return null; // e.g. application_interview: its application id is not part of the source
  }
}

// Suggested actions are backend API calls ({label, method, endpoint, body, requires_confirmation}).
// The assistant never performs them; we send the student to the existing page where they can do it
// themselves (with that page's own checks and confirmations). Unknown endpoints get no link.
// Pages the Application Assistant's step-by-step guide may link to (exact paths only).
const GUIDE_PAGES = new Set(["/profile", "/resumes", "/matches", "/internships", "/skill-gaps", "/interview-prep", "/documents", "/career-tracks"]);

export function actionLink(action) {
  if (!action || typeof action.endpoint !== "string") return null;
  const e = action.endpoint;
  const body = action.body && typeof action.body === "object" ? action.body : {};
  // `type` is a fixed value; ids are included only when they are positive integers.
  const query = (pairs) => {
    const params = new URLSearchParams();
    for (const [k, v] of pairs) if (k === "type" || positiveId(v)) params.set(k, String(v));
    const s = params.toString();
    return s ? `?${s}` : "";
  };
  let m;
  if (e === "/assistant" || e === "/interview-assistant") return e; // switch to the other assistant
  if (GUIDE_PAGES.has(e)) return e; // step-by-step guidance: a fixed set of in-app pages, nothing else
  if (e === "/resumes/upload") return "/resumes";
  if (/^\/matches\/resumes\/\d+$/.test(e)) return "/matches";
  if ((m = e.match(/^\/applications\/bookmarks\/(\d+)$/))) return `/internships/${m[1]}`;
  if ((m = e.match(/^\/skill-gaps\/resumes\/\d+\/internships\/(\d+)$/))) return `/skill-gaps/internships/${m[1]}`;
  if (/^\/skill-gaps\/resumes\/\d+$/.test(e)) return "/skill-gaps";
  if (e === "/documents/resume") return `/documents${query([["type", "resume"], ["internship", body.internship_id], ["resume", body.resume_id]])}`;
  if (e === "/documents/cover-letter") return `/documents${query([["type", "cover_letter"], ["internship", body.internship_id], ["resume", body.resume_id]])}`;
  if (e === "/interviews/sessions" && /^[a-z0-9-]+$/.test(String(body.target_role || "")))
    return `/interview-prep?role=${body.target_role}${body.mode === "mock" ? "&mode=mock" : ""}`;
  if (e === "/interviews/sessions") return `/interview-prep${query([["internship", body.internship_id], ["resume", body.resume_id]])}`;
  if ((m = e.match(/^\/applications\/(\d+)$/))) return `/applications/${m[1]}`;
  if (e === "/applications") return positiveId(body.internship_id) ? `/internships/${body.internship_id}` : "/applications";
  return null;
}

export const WARNING_LABEL = {
  internship_closed: "Internship no longer open",
  closed_matches_hidden: "Closed internships hidden",
  generic_plan: "General learning plan",
  semantic_search_unavailable: "Semantic search unavailable",
  ai_rate_limited: "AI limit reached",
  llm_unverified: "AI answer not verified",
  llm_unavailable: "AI unavailable",
  llm_not_applicable: "Nothing for AI to reword",
  keyword_retrieval: "Keyword search",
};

// Where an answer's sources come from, for the "Based on N sources ..." summary.
export function sourcesOrigin(sources) {
  const list = sources || [];
  const guide = list.filter((s) => s?.type === "product_doc").length;
  const doc = list.filter((s) => s?.type === "study_document").length;
  if (doc && doc === list.length) {
    const docs = new Set(list.map((s) => String(s.id).split(":")[0]));
    return docs.size > 1 ? "from your documents" : "from your document";
  }
  if (guide && guide === list.length) return "from the product guide";
  if (guide) return "from your data and the product guide";
  return "from your data";
}

export const GENERATION_LABEL = { llm: "AI-reworded (fact-checked)", deterministic: "Standard answer" };

// The backend returns messages oldest first; keep that order and drop duplicates by message_id.
export function mergeMessages(...lists) {
  const byId = new Map();
  for (const list of lists) for (const m of list || []) byId.set(m.message_id, m);
  return [...byId.values()].sort((a, b) => a.message_id - b.message_id);
}

// A suggestion is either a question that is sent, or { label, to } - a link to the place that answers it.
// Interview preparation belongs to the Interview Preparation Assistant, so that suggestion opens it
// directly instead of sending a message here that would only be redirected.
export const SUGGESTED_QUESTIONS = [
  "What skills are missing from my resume?",
  "Which internships match my profile?",
  "How can I improve my resume for this internship?",
  { label: "Help me prepare for an interview", to: "/interview-assistant" },
  "What should I learn next?",
  "How can I improve my chances of getting selected?",
];

// Questions about the product itself, answered from the product guide (with the guide sections cited).
export const PRODUCT_QUESTIONS = [
  "How does internship matching work?",
  "How do I create a cover letter?",
  "What is mock mode in interview practice?",
  "Is my data private?",
];
