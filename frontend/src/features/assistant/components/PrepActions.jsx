import { Link } from "react-router-dom";
import Icon from "../../../components/ui/Icon";

// Interview preparation agent shortcuts. Each chip sends a normal chat message; the backend answers
// from the student's own resume and curated guides (nothing is generated in the browser).
export const PREP_ACTIONS = [
  { label: "Analyze my resume", message: "Analyze my resume", icon: "document" },
  { label: "Recommend suitable roles", message: "Which roles are suitable for my resume?", icon: "target" },
  { label: "Technical questions", message: "Generate technical questions", icon: "edit" },
  { label: "HR questions", message: "Generate HR questions", icon: "users" },
  { label: "My preparation roadmap", message: "Create my preparation roadmap", icon: "chart" },
];

const chip =
  "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:opacity-60";

export default function PrepActions({ onSend, disabled, tracks, targetRole, onDocuments }) {
  const role = (tracks || []).find((t) => t.slug === targetRole);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="prep-role" className="text-xs font-semibold text-slate-600">
          Prepare for
        </label>
        <select
          id="prep-role"
          value={targetRole || ""}
          disabled={disabled || !tracks}
          onChange={(e) => {
            const t = (tracks || []).find((x) => x.slug === e.target.value);
            if (t) onSend(`Prepare me for ${t.title}`);
          }}
          className="cn-input max-w-[14rem] py-1.5 text-xs"
        >
          <option value="">{tracks ? "Choose a role…" : "Loading roles…"}</option>
          {(tracks || []).map((t) => (
            <option key={t.slug} value={t.slug}>
              {t.title}
            </option>
          ))}
        </select>
        {role && (
          <Link
            to={`/interview-prep?role=${role.slug}&mode=mock`}
            className="inline-flex items-center gap-1.5 rounded-full bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
          >
            <Icon name="mic" className="h-3.5 w-3.5" />
            Mock interview: {role.title}
          </Link>
        )}
      </div>
      <ul className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]" aria-label="Interview preparation actions">
        {PREP_ACTIONS.map((a) => (
          <li key={a.label}>
            <button type="button" className={chip} disabled={disabled} onClick={() => onSend(a.message)}>
              <Icon name={a.icon} className="h-3.5 w-3.5 text-brand-600" />
              {a.label}
            </button>
          </li>
        ))}
        <li>
          <button type="button" className={chip} disabled={disabled} onClick={onDocuments}>
            <Icon name="upload" className="h-3.5 w-3.5 text-brand-600" />
            Upload a study document
          </button>
        </li>
      </ul>
    </div>
  );
}
