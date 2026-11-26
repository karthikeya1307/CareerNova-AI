import RichText from "./RichText";
import { useAuth } from "../../../context/AuthContext";
import Avatar from "../../../components/ui/Avatar";
import { Link } from "react-router-dom";
import Badge from "../../../components/ui/Badge";
import { formatDateTime } from "../../../utils/dates";
import { actionLink, GENERATION_LABEL, sourceLink, sourcesOrigin, sourceTypeLabel, WARNING_LABEL } from "../assistantFormat";

function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer font-medium text-slate-600">
        Based on {sources.length} source{sources.length === 1 ? "" : "s"} {sourcesOrigin(sources)}
      </summary>
      <ul className="mt-1.5 flex flex-col gap-1" aria-label="Sources">
        {sources.map((s, i) => {
          const to = sourceLink(s);
          return (
            <li key={`${s.type}:${s.id}:${i}`} className="flex flex-wrap items-center gap-1.5">
              <span className="text-slate-500">{sourceTypeLabel(s.type)}:</span>
              {to ? (
                <Link to={to} className="font-medium text-brand-700 hover:underline">
                  {s.label}
                </Link>
              ) : (
                <span className="text-slate-700">{s.label}</span>
              )}
              {s.available === false && <Badge>No longer available</Badge>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function Results({ resultSet }) {
  const items = resultSet?.items || [];
  if (!items.length) return null;
  return (
    <ol className="mt-2 flex flex-col gap-1 text-sm" aria-label="Results">
      {items.map((item, i) => {
        const to = sourceLink({ type: item.type, id: item.id });
        return (
          <li key={`${item.type}:${item.id}:${i}`} className="flex gap-2">
            <span className="tabular-nums text-slate-400">{i + 1}.</span>
            {to ? (
              <Link to={to} className="font-medium text-brand-700 hover:underline">
                {item.label}
              </Link>
            ) : (
              <span className="text-slate-800">{item.label}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Actions({ actions }) {
  const links = (actions || []).map((a) => ({ label: a.label, to: actionLink(a) })).filter((a) => a.to);
  if (!links.length) return null;
  return (
    <div className="mt-3">
      <p className="text-xs text-slate-500">Suggested next steps (opens the page where you can do this yourself):</p>
      <ul className="mt-1 flex flex-wrap gap-2" aria-label="Suggested next steps">
        {links.map((a, i) => (
          <li key={i}>
            <Link
              to={a.to}
              className="inline-flex rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
            >
              {a.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

// One message (MessageOut). Only fields the backend returned are shown; nothing is added.
export default function MessageBubble({ message: m, pending = false }) {
  const mine = m.sender === "user";
  const { user } = useAuth();
  return (
    <li className={`flex items-end gap-2 ${mine ? "flex-row-reverse justify-start" : "justify-start"}`}>
      {mine && <Avatar user={user} size="sm" className="mb-1 hidden sm:inline-flex" />}
      <article
        aria-label={mine ? "Your message" : "Assistant reply"}
        className={`max-w-[92%] rounded-2xl px-4 py-3 sm:max-w-[80%] ${
          mine ? "rounded-br-sm bg-brand-600 text-white" : "rounded-bl-sm border border-slate-200 bg-white text-slate-900 shadow-sm"
        } ${pending ? "opacity-70" : ""}`}
      >
        {mine ? <p className="whitespace-pre-line break-words text-sm">{m.content}</p> : <RichText content={m.content} />}
        {!mine && (
          <>
            <Results resultSet={m.result_set} />
            {m.warnings?.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1" aria-label="Notes about this answer">
                {m.warnings.map((w, i) => (
                  <li key={i} className="rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">
                    <span className="font-medium">{WARNING_LABEL[w.code] || "Note"}:</span> {w.detail}
                  </li>
                ))}
              </ul>
            )}
            <Sources sources={m.sources} />
            <Actions actions={m.suggested_actions} />
          </>
        )}
        <p className={`mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] ${mine ? "text-brand-100" : "text-slate-500"}`}>
          {pending ? "Sending…" : m.created_at ? <time dateTime={m.created_at}>{formatDateTime(m.created_at)}</time> : null}
          {!mine && m.generation_method && <span>· {GENERATION_LABEL[m.generation_method] || m.generation_method}</span>}
          {!mine && !m.sources?.length && <span>· No sources for this answer</span>}
        </p>
      </article>
    </li>
  );
}
