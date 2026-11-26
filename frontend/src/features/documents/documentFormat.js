// Labels for backend document values (backend/routes/documents.py, services/document*.py).

export const DOCUMENT_TYPE = { resume: "Tailored resume", cover_letter: "Cover letter" };

export function documentTypeLabel(type) {
  return DOCUMENT_TYPE[type] || type;
}

// generation_method: "deterministic" (fact-based, no AI) or "llm" (AI-assisted, fact-checked).
export function generationLabel(method, provider, model) {
  if (method === "llm") return `AI-assisted${provider ? ` (${provider}${model ? `, ${model}` : ""})` : ""}`;
  if (method === "deterministic") return "Fact-based (no AI)";
  return method || "Unknown method";
}

// Version sources recorded by the backend.
export const VERSION_SOURCE = { generated: "Generated", edited: "Edited by you", restored: "Restored" };

// Problem codes from the backend fact checker, in plain words.
export const PROBLEM_CODES = {
  unsupported_skill: "Skill not on your resume",
  unsupported_number: "Number not on your resume",
  unsupported_term: "Term not on your resume",
  unknown_fact: "Refers to unknown resume facts",
  no_citation: "Not linked to resume facts",
  invalid_output: "Invalid AI output",
  privacy_placeholder: "Repeats removed personal details",
  privacy_guard: "Blocked to protect personal details",
  llm_invalid: "AI response unusable",
  llm_unavailable: "AI unavailable — fact-based text used",
  source_unavailable: "Source resume unavailable",
  duplicate: "Duplicate",
};

export function problemLabel(code) {
  return PROBLEM_CODES[code] || code;
}

// Total problems the way the backend counts them (warnings + rejected statements).
export function factCheckWarnings(factCheck) {
  if (!factCheck) return 0;
  return (factCheck.warnings?.length || 0) + (factCheck.rejected_statements?.length || 0);
}
