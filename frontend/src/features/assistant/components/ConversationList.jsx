import { Link } from "react-router-dom";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";
import { formatDateTime } from "../../../utils/dates";
import { CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";

// Conversation history (GET /assistant/conversations, most recently updated first).
export default function ConversationList({ conversations, activeId, onNew, onMore, newDisabled, basePath = "/assistant" }) {
  const data = conversations.data;
  return (
    <nav aria-label="Conversations" className="flex min-h-0 flex-col gap-3">
      <Button onClick={onNew} disabled={newDisabled} className="w-full">
        <Icon name="edit" className="h-4 w-4" />
        New conversation
      </Button>
      {(conversations.status === "loading" || conversations.status === "idle") && !data ? (
        <CardSkeleton label="your conversations" lines={3} />
      ) : conversations.status === "error" && !data ? (
        <CardError error={conversations.error} onRetry={conversations.reload} label="your conversations" />
      ) : !data.items.length ? (
        <p className="px-1 text-sm text-slate-500">No conversations yet. Your chats are saved here.</p>
      ) : (
        <>
          <ul className="flex flex-col gap-1" aria-label="Your conversations">
            {data.items.map((c) => {
              const active = c.conversation_id === activeId;
              return (
                <li key={c.conversation_id}>
                  <Link
                    to={`${basePath}/${c.conversation_id}`}
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-lg px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                      active ? "bg-brand-50 text-brand-800" : "text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <span className="block truncate font-medium">{c.title || "New conversation"}</span>
                    <span className="block text-xs text-slate-500">
                      {c.message_count} message{c.message_count === 1 ? "" : "s"} · {formatDateTime(c.last_message_at || c.created_at)}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          {data.total > data.items.length && (
            <Button variant="ghost" onClick={onMore} loading={conversations.status === "loading"} className="text-xs">
              Show more ({data.total - data.items.length} older)
            </Button>
          )}
        </>
      )}
    </nav>
  );
}
