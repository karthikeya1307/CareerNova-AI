import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createConversation, deleteConversation, getCapabilities, getConversation, listConversations, listMessages, MESSAGE_MAX, sendMessage, TITLE_MAX,
  updateConversation,
} from "../../api/assistant";
import { listCareerTracks } from "../../api/careerTracks";
import { errorMessage, normalizeError } from "../../api/errors";
import { attachStudyDocuments, listStudyDocuments } from "../../api/studyDocuments";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import { mergeMessages, PRODUCT_QUESTIONS } from "./assistantFormat";
import Composer, { validateMessage } from "./components/Composer";
import ConversationList from "./components/ConversationList";
import MessageBubble from "./components/MessageBubble";
import PrepActions from "./components/PrepActions";
import StudyDocumentPanel from "./components/StudyDocumentPanel";
import AssistantSwitch, { ASSISTANTS } from "./components/AssistantSwitch";

const panel = "rounded-2xl border border-slate-200/80 bg-white shadow-card";
const toId = (value) => (/^\d+$/.test(String(value ?? "")) && Number(value) > 0 ? Number(value) : null);

function SendError({ error, onRetry, onNew }) {
  if (!error) return null;
  const limited = error.status === 429;
  const full = error.status === 409;
  return (
    <div role="alert" className="flex flex-col gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 sm:flex-row sm:items-center sm:justify-between">
      <span>
        <span className="font-medium">{limited ? "Slow down a little. " : "Your message wasn't sent. "}</span>
        {error.message}
        {limited && error.retryAfter ? ` (about ${error.retryAfter} s)` : ""} Your text is still in the box.
      </span>
      <span className="flex shrink-0 gap-2">
        {full ? (
          <Button variant="secondary" onClick={onNew} className="py-1 text-xs">
            Start a new conversation
          </Button>
        ) : (
          <Button variant="secondary" onClick={onRetry} className="py-1 text-xs">
            Try again
          </Button>
        )}
      </span>
    </div>
  );
}

// Two separate assistants share this page:
//   kind="application" (/assistant): how to use CareerNova AI + the student's own data, restricted scope;
//   kind="interview" (/interview-assistant): Interview Preparation Assistant (roles, questions, roadmap,
//   mock interviews, study-document Q&A). Each has its own conversations; the backend keeps their scopes apart.
// /<base> starts a new chat (created on the first message); /<base>/:conversationId opens a saved one.
export default function AssistantPage({ kind = "application" }) {
  const meta = ASSISTANTS[kind];
  const base = meta.path;
  const { conversationId } = useParams();
  const id = toId(conversationId);
  const invalid = conversationId !== undefined && !id;
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();

  const [limit, setLimit] = useState(20);
  const conversations = useApiResource(() => listConversations({ limit, assistant: kind }), `assistant-conversations:${kind}:${limit}`);
  const caps = useApiResource(getCapabilities, "assistant-capabilities");
  const llm = {
    status: caps.status,
    error: caps.error,
    data: caps.data?.llm ? { ...caps.data.llm, disclosure: caps.data.llm.assistant_disclosure || caps.data.llm.disclosure } : null,
  };
  const max = caps.data?.limits?.message_chars || MESSAGE_MAX;
  const conversation = useApiResource(() => getConversation(id), `assistant-conversation:${id}`, { enabled: Boolean(id) });

  const [messages, setMessages] = useState([]);
  const loadedFor = useRef(null);
  const [older, setOlder] = useState({ status: "idle", done: false });
  const [draft, setDraft] = useState("");
  const [inputError, setInputError] = useState(null);
  const [sendError, setSendError] = useState(null);
  const [pending, setPending] = useState(null);
  const [ai, setAi] = useState({ useLlm: false, consent: false });
  const [aiError, setAiError] = useState(null);
  const [renaming, setRenaming] = useState(null); // title being edited
  const [renameError, setRenameError] = useState(null);
  const [action, setAction] = useState(null);
  const [showList, setShowList] = useState(false);
  const [showDocs, setShowDocs] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const tracks = useApiResource(listCareerTracks, "career-tracks", { enabled: kind === "interview" });
  const studyDocs = useApiResource(listStudyDocuments, "study-documents", { enabled: kind === "interview" });
  const busy = useRef(false);
  const composer = useRef(null);
  const scroller = useRef(null);

  // Show the opened conversation's messages (oldest first). Refreshes merge by message_id.
  useEffect(() => {
    if (!id) {
      setMessages([]);
      loadedFor.current = null;
      return;
    }
    const data = conversation.data;
    if (!data || data.conversation_id !== id) {
      if (loadedFor.current !== id) setMessages([]);
      return;
    }
    setMessages((prev) => (loadedFor.current === id ? mergeMessages(prev, data.messages) : mergeMessages(data.messages)));
    loadedFor.current = id;
  }, [conversation.data, id]);

  // Switching conversations resets per-conversation UI. A send error is kept when we moved to the
  // conversation that was just created for that (failed) first message, so Try again stays visible.
  const keepErrorFor = useRef(null);
  useEffect(() => {
    setOlder({ status: "idle", done: false });
    setRenaming(null);
    setShowList(false);
    if (keepErrorFor.current !== id) setSendError(null);
    keepErrorFor.current = null;
  }, [id]);

  useEffect(() => {
    const other = conversation.data?.assistant;
    if (id && other && other !== kind && conversation.data?.conversation_id === id) {
      navigate(`${ASSISTANTS[other].path}/${id}`, { replace: true });
    }
  }, [conversation.data, id, kind, navigate]);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, pending]);

  useEffect(() => {
    const previous = document.title;
    document.title = `${meta.title} · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [meta.title]);

  const send = async (textArg) => {
    const text = textArg ?? draft;
    if (busy.current) return; // one message at a time
    const problem = validateMessage(text, max);
    setInputError(problem);
    if (problem) {
      if (textArg !== undefined) setDraft(textArg);
      return;
    }
    if (ai.useLlm && !ai.consent) {
      setAiError("Accept the disclosure to use AI rewording, or turn it off.");
      return;
    }
    setAiError(null);
    setSendError(null);
    busy.current = true;
    setPending(text);
    setDraft("");
    let target = id;
    let created = null;
    try {
      if (!target) {
        created = (await createConversation({ assistant: kind })).conversation_id;
        target = created;
      }
      const exchange = await sendMessage(target, { message: text, useLlm: ai.useLlm && Boolean(llm.data?.available), consent: ai.consent });
      setMessages((prev) => mergeMessages(target === id ? prev : [], [exchange.user_message, exchange.assistant_message]));
      loadedFor.current = target;
      if (target !== id) navigate(`${base}/${target}`);
      else conversation.reload();
      conversations.reload();
    } catch (failure) {
      setDraft((current) => current || text); // never lose what the student typed
      setSendError(normalizeError(failure));
      if (created) {
        // The empty conversation exists now; retry there instead of creating another one.
        loadedFor.current = created;
        keepErrorFor.current = created;
        navigate(`${base}/${created}`, { replace: true });
        conversations.reload();
      }
    } finally {
      busy.current = false;
      setPending(null);
      composer.current?.focus();
    }
  };

  const loadOlder = async () => {
    if (older.status === "loading" || !messages.length) return;
    setOlder((o) => ({ ...o, status: "loading" }));
    try {
      const batch = await listMessages(id, { beforeId: messages[0].message_id, limit: 50 });
      setMessages((prev) => mergeMessages(batch, prev));
      setOlder({ status: "idle", done: batch.length < 50 });
    } catch (failure) {
      setOlder({ status: "error", done: false, message: errorMessage(failure) });
    }
  };

  const rename = async (event) => {
    event.preventDefault();
    const title = renaming.trim();
    if (!title) return setRenameError("Enter a title.");
    if (title.length > TITLE_MAX) return setRenameError(`Use at most ${TITLE_MAX} characters.`);
    if (action) return undefined;
    setAction("rename");
    setRenameError(null);
    try {
      const updated = await updateConversation(id, { title });
      conversation.setData({ ...conversation.data, ...updated, messages: conversation.data.messages });
      setRenaming(null);
      conversations.reload();
    } catch (failure) {
      setRenameError(errorMessage(failure));
    } finally {
      setAction(null);
    }
    return undefined;
  };

  const remove = async () => {
    const ok = await confirm({
      title: "Delete this conversation?",
      message: "The conversation and all its messages are deleted permanently. Your resumes, applications and other data are not affected.",
      confirmLabel: "Delete conversation",
      tone: "danger",
    });
    if (!ok || action) return;
    setAction("delete");
    try {
      await deleteConversation(id);
      toast.success("Conversation deleted.");
      conversations.reload();
      navigate(base, { replace: true });
    } catch (failure) {
      toast.error(`The conversation couldn't be deleted: ${errorMessage(failure)}`);
    } finally {
      setAction(null);
    }
  };

  // Choose the study documents this chat answers from ([] = stop). A new chat is created first if needed.
  const attach = async (documentIds) => {
    setAttaching(true);
    try {
      const target = id || (await createConversation({ assistant: kind })).conversation_id;
      const updated = await attachStudyDocuments(target, documentIds);
      if (target !== id) {
        loadedFor.current = target;
        navigate(`${base}/${target}`);
      } else {
        conversation.setData({ ...conversation.data, ...updated, messages: conversation.data?.messages || [] });
      }
      conversations.reload();
      if (documentIds.length)
        toast.success(`Questions in this chat are now answered from ${documentIds.length === 1 ? "your document" : `${documentIds.length} documents`}.`);
    } catch (failure) {
      toast.error(`The document couldn't be attached: ${errorMessage(failure)}`);
    } finally {
      setAttaching(false);
    }
  };

  const startNew = () => {
    setSendError(null);
    navigate(base);
  };

  const data = id && conversation.data?.conversation_id === id ? conversation.data : null;
  const notFound = invalid || (id && conversation.status === "error" && conversation.error?.status === 404);
  const hasOlder = data && !older.done && data.message_count > messages.length;
  const sending = pending !== null;
  const attachedIds = data?.study_document_ids || (data?.study_document_id ? [data.study_document_id] : []);
  const attachedDocs = attachedIds.map((docId) => (studyDocs.data || []).find((d) => d.document_id === docId) || { document_id: docId, filename: `document #${docId}` });

  let body;
  if (notFound) {
    body = (
      <div className="flex flex-1 items-center justify-center p-6">
        <CardEmpty
          title="Conversation not found"
          message="It doesn't exist, was deleted, or belongs to another account."
          action={<Button onClick={startNew}>Start a new conversation</Button>}
        />
      </div>
    );
  } else if (id && !data && !messages.length) {
    body = (
      <div className="p-6">
        {conversation.status === "error" ? <CardError error={conversation.error} onRetry={conversation.reload} label="the conversation" /> : <CardSkeleton label="the conversation" lines={5} />}
      </div>
    );
  } else if (!messages.length && !sending) {
    body = (
      <div className="flex flex-1 flex-col items-center justify-center gap-5 p-6 text-center">
        <span className={`flex h-12 w-12 items-center justify-center rounded-2xl ${kind === "interview" ? "bg-violet-50 text-violet-600" : "bg-brand-50 text-brand-600"}`}>
          <Icon name={meta.icon} className="h-6 w-6" />
        </span>
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{meta.greeting}</h2>
          <p className="mx-auto mt-1 max-w-lg text-sm text-slate-600">{meta.intro}</p>
        </div>
        <ul className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2" aria-label="Suggested questions">
          {meta.suggestions.map((q) => (
            <li key={typeof q === "string" ? q : q.to}>
              {typeof q === "string" ? (
                <button
                  type="button"
                  onClick={() => send(q)}
                  disabled={sending}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-left text-sm text-slate-700 hover:border-brand-300 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:opacity-60"
                >
                  {q}
                </button>
              ) : (
                <Link
                  to={q.to}
                  className="flex w-full items-center justify-between gap-2 rounded-xl border border-slate-200 px-3 py-2.5 text-left text-sm text-slate-700 hover:border-brand-300 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                >
                  {q.label}
                  <Icon name="arrowRight" className="h-4 w-4 shrink-0 text-slate-400" />
                </Link>
              )}
            </li>
          ))}
        </ul>
        {kind === "application" && (
        <div className="w-full max-w-2xl text-left">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">About the app</h3>
          <ul className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2" aria-label="Questions about CareerNova AI">
            {PRODUCT_QUESTIONS.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  onClick={() => send(q)}
                  disabled={sending}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-left text-sm text-slate-700 hover:border-brand-300 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:opacity-60"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
        )}
        {caps.data?.limits && (
          <p className="text-xs text-slate-500">
            Up to {caps.data.limits.messages_per_minute} messages a minute and {caps.data.limits.messages_per_day} a day.
          </p>
        )}
      </div>
    );
  } else {
    body = (
      <div ref={scroller} className="min-h-[18rem] flex-1 overflow-y-auto px-3 py-4 sm:px-5 lg:max-h-[calc(100vh-22rem)]">
        {hasOlder && (
          <div className="mb-3 flex flex-col items-center gap-1">
            <Button variant="ghost" onClick={loadOlder} loading={older.status === "loading"} className="text-xs">
              Load earlier messages
            </Button>
            {older.status === "error" && (
              <p role="alert" className="text-xs text-red-700">
                {older.message}
              </p>
            )}
          </div>
        )}
        <ol className="flex flex-col gap-3" aria-label="Messages" role="log" aria-live="polite">
          {messages.map((m) => (
            <MessageBubble key={m.message_id} message={m} />
          ))}
          {sending && <MessageBubble message={{ message_id: -1, sender: "user", content: pending }} pending />}
        </ol>
        {sending && (
          <p className="mt-3 flex items-center gap-2 text-xs text-slate-500" role="status">
            <span className="inline-flex gap-1" aria-hidden="true">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:120ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:240ms]" />
            </span>
            The assistant is looking at your data…
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{meta.title}</h1>
          <p className="mt-1 text-sm text-slate-600">{meta.tagline}</p>
        </div>
        <Button variant="secondary" className="lg:hidden" onClick={() => setShowList((v) => !v)} aria-expanded={showList} aria-controls="assistant-conversations">
          <Icon name="chat" className="h-4 w-4" />
          Conversations{conversations.data ? ` (${conversations.data.total})` : ""}
        </Button>
      </header>
      <AssistantSwitch current={kind} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside id="assistant-conversations" className={`${panel} min-w-0 p-3 lg:block lg:max-h-[calc(100vh-10rem)] lg:overflow-y-auto ${showList ? "block" : "hidden"}`}>
          <ConversationList
            conversations={conversations}
            activeId={id}
            onNew={startNew}
            onMore={() => setLimit((l) => Math.min(100, l + 20))}
            basePath={base}
            newDisabled={!id && !messages.length}
          />
        </aside>

        <section aria-label="Chat" className={`${panel} flex min-h-[32rem] min-w-0 flex-col`}>
          {data && (
            <div className="flex flex-col gap-2 border-b border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              {renaming !== null ? (
                <form onSubmit={rename} className="flex flex-1 flex-wrap items-center gap-2" aria-label="Rename conversation">
                  <label htmlFor="conversation-title" className="sr-only">
                    Conversation title
                  </label>
                  <input
                    id="conversation-title"
                    value={renaming}
                    maxLength={TITLE_MAX}
                    onChange={(e) => setRenaming(e.target.value)}
                    aria-invalid={renameError ? true : undefined}
                    className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                  <Button type="submit" loading={action === "rename"} className="py-1.5">
                    Save
                  </Button>
                  <Button variant="ghost" onClick={() => setRenaming(null)} className="py-1.5">
                    Cancel
                  </Button>
                  {renameError && (
                    <p role="alert" className="w-full text-xs text-red-700">
                      {renameError}
                    </p>
                  )}
                </form>
              ) : (
                <div className="min-w-0">
                  <h2 className="truncate text-base font-semibold text-slate-900">{data.title || "New conversation"}</h2>
                  <p className="text-xs text-slate-500">
                    {data.message_count} message{data.message_count === 1 ? "" : "s"}
                    {data.last_message_at ? ` · last ${formatDateTime(data.last_message_at)}` : ""}
                  </p>
                </div>
              )}
              {renaming === null && (
                <div className="flex shrink-0 flex-wrap gap-1">
                  <Button variant="ghost" onClick={conversation.reload} className="px-2 py-1 text-xs" aria-label="Refresh messages">
                    <Icon name="refresh" className="h-3.5 w-3.5" />
                    Refresh
                  </Button>
                  <Button variant="ghost" onClick={() => setRenaming(data.title || "")} className="px-2 py-1 text-xs">
                    Rename
                  </Button>
                  <Button variant="ghost" onClick={remove} loading={action === "delete"} className="px-2 py-1 text-xs text-red-700">
                    Delete
                  </Button>
                </div>
              )}
            </div>
          )}

          {body}

          {!notFound && (
            <div className="flex flex-col gap-2 border-t border-slate-100 p-3 sm:p-4">
              {kind === "interview" && attachedIds.length > 0 && (
                <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-xs text-brand-900">
                  <span className="flex min-w-0 items-center gap-2">
                    <Icon name="document" className="h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">
                      Answering from {attachedDocs.length === 1 ? "your document" : `${attachedDocs.length} documents`}:{" "}
                      <span className="font-semibold">{attachedDocs.map((d) => d.filename).join(", ")}</span>
                    </span>
                  </span>
                  <Button variant="ghost" onClick={() => attach([])} loading={attaching} className="min-h-0 px-2 py-1 text-xs">
                    {attachedDocs.length === 1 ? "Stop using it" : "Stop using them"}
                  </Button>
                </div>
              )}
              {kind === "interview" && showDocs && (
                <StudyDocumentPanel
                  documents={studyDocs}
                  attachedIds={attachedIds}
                  onAttach={attach}
                  onClose={() => setShowDocs(false)}
                  busy={attaching || sending}
                />
              )}
              {kind === "interview" && (
                <PrepActions
                  onSend={(message) => send(message)}
                  disabled={sending}
                  tracks={tracks.data}
                  targetRole={data?.target_role}
                  onDocuments={() => setShowDocs((v) => !v)}
                />
              )}
              <SendError error={sendError} onRetry={() => send()} onNew={startNew} />
              <Composer
                ref={composer}
                value={draft}
                onChange={(v) => {
                  setDraft(v);
                  if (inputError) setInputError(null);
                }}
                onSubmit={() => send()}
                sending={sending}
                error={inputError}
                max={max}
                llm={llm}
                ai={ai}
                onAi={(next) => {
                  setAi(next);
                  setAiError(null);
                }}
                aiError={aiError}
              />
              <p className="text-[11px] text-slate-500">
                The assistant can suggest next steps but never changes your data. Check important details on the linked pages.{" "}
                <Link to="/" className="underline">
                  Dashboard
                </Link>
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
