import { Link } from "react-router-dom";
import Icon from "../../../components/ui/Icon";
import { formatDate } from "../../../utils/dates";
import { ResourceState } from "./DashboardCard";

// Entry points to the two AI assistants, with the student's latest conversations (each linked to its own assistant).
export default function AssistantCard({ conversations }) {
  return (
    <section
      aria-labelledby="assistant-card-title"
      className="relative flex min-w-0 flex-col overflow-hidden rounded-2xl bg-gradient-to-br from-brand-700 via-brand-600 to-indigo-700 p-5 text-white shadow-sm"
    >
      <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
      <div className="relative flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/15">
          <Icon name="chat" className="h-5 w-5" />
        </span>
        <h2 id="assistant-card-title" className="text-base font-semibold">
          AI assistants
        </h2>
      </div>
      <p className="relative mt-3 text-sm text-brand-50">
        The Application Assistant helps with CareerNova AI and your data; the Interview Preparation Assistant uses your resume to prepare you for interviews.
      </p>
      <div className="relative mt-4 flex-1 text-sm">
        <ResourceState resource={conversations} label="your conversations" lines={2}>
          {(data) => {
            const items = data?.items || [];
            if (!items.length) return <p className="text-brand-100">No conversations yet.</p>;
            return (
              <ul className="flex flex-col gap-1.5" aria-label="Recent conversations">
                {items.map((c) => (
                  <li key={c.conversation_id}>
                    <Link
                      to={`${c.assistant === "interview" ? "/interview-assistant" : "/assistant"}/${c.conversation_id}`}
                      aria-label={`Continue conversation: ${c.title || "Untitled conversation"}`}
                      className="flex items-center justify-between gap-3 rounded-lg bg-white/10 px-3 py-2 hover:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
                    >
                      <span className="truncate">{c.title || "Untitled conversation"}</span>
                      <span className="shrink-0 text-xs text-brand-100">{formatDate(c.last_message_at || c.updated_at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            );
          }}
        </ResourceState>
      </div>
      <div className="relative mt-4 flex flex-col gap-2">
        <Link
          to="/assistant"
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        >
          Ask the Application Assistant
          <Icon name="arrowRight" className="h-4 w-4" />
          <span className="sr-only">(new conversation)</span>
        </Link>
        <Link
          to="/interview-assistant"
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/40 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        >
          <Icon name="sparkles" className="h-4 w-4" />
          Prepare for interviews
        </Link>
      </div>
    </section>
  );
}
