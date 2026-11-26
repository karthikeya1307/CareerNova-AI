import { NavLink } from "react-router-dom";
import Icon from "../../../components/ui/Icon";
import { SUGGESTED_QUESTIONS } from "../assistantFormat";

// The two assistants: separate identities, responsibilities and conversations (the backend keeps their
// scopes apart: each points questions outside its scope to the other one).
export const ASSISTANTS = {
  application: {
    path: "/assistant",
    title: "Application Assistant",
    short: "Application Assistant",
    icon: "chat",
    tagline: "Help with using CareerNova AI and with your own data in it. Answers show where their facts come from.",
    greeting: "How can I help you use CareerNova AI?",
    intro:
      "Ask how features work (resume upload, ATS checks, matching, career tracks, applications) or about your own matches, skill gaps, documents and applications. Questions about how CareerNova AI works are answered from its product guide. I only answer questions about CareerNova AI, and I never change your data.",
    suggestions: SUGGESTED_QUESTIONS,
  },
  interview: {
    path: "/interview-assistant",
    title: "Interview Preparation Assistant",
    short: "Interview Prep Assistant",
    icon: "sparkles",
    tagline: "Uses your parsed resume to recommend roles and prepare you for interviews - plus Q&A on your study documents.",
    greeting: "Let's get you interview-ready",
    intro:
      "I read the resume you already uploaded - no need to upload it again. I recommend roles that fit, explain the gaps, generate technical and HR questions with answer guidance, build a preparation roadmap, set up mock interviews, and answer questions about study documents you upload (with page references).",
    suggestions: [
      "Which roles are suitable for my resume?",
      "What are my strongest technical skills?",
      "Am I suitable for a Java Developer role?",
      "What should I learn to become an AI Engineer?",
      "What are my weaknesses?",
      "Analyze my resume",
    ],
  },
};

export default function AssistantSwitch({ current }) {
  return (
    <nav aria-label="Assistants" className="flex w-full flex-wrap gap-1 rounded-2xl border border-slate-200/80 bg-white p-1 shadow-card sm:w-fit">
      {Object.entries(ASSISTANTS).map(([kind, a]) => (
        <NavLink
          key={kind}
          to={a.path}
          aria-current={current === kind ? "page" : undefined}
          className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3.5 py-2 text-sm font-semibold transition sm:flex-none ${
            current === kind ? "bg-navy-900 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          }`}
        >
          <Icon name={a.icon} className="h-4 w-4" />
          {a.short}
        </NavLink>
      ))}
    </nav>
  );
}
