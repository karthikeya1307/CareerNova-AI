import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { errorMessage, normalizeError } from "../../api/errors";
import { completeSession, deleteSession, getLlmStatus, getSession } from "../../api/interviews";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import AiAssistChoice from "../documents/components/AiAssistChoice";
import QuestionCard from "./components/QuestionCard";
import SessionSummary from "./components/SessionSummary";
import { categoryLabel, difficultyLabel, isOpen, modeLabel, NOTICE_TITLE, sessionStatus } from "./interviewFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

export const FEEDBACK_AI_COPY = {
  legend: "Feedback method",
  feature: "AI feedback",
  deterministic: (
    <>
      Answers are scored with the <span className="font-medium text-slate-800">built-in rubric</span> (key points, structure and length). No AI is used.
    </>
  ),
  byDefault: "By default your answers are scored with the built-in rubric and nothing leaves this service.",
  hint: "Optional. Adds AI-written coaching to the rubric feedback. The score always comes from the rubric.",
  consent: "I have read this and agree to send my answers for AI feedback in this session",
};

function Navigator({ questions, current, onSelect }) {
  return (
    <nav aria-label="Questions">
      <ol className="flex flex-wrap gap-1.5 lg:flex-col">
        {questions.map((q, index) => (
          <li key={q.question_id}>
            <button
              type="button"
              onClick={() => onSelect(index)}
              aria-current={index === current ? "step" : undefined}
              aria-label={`Question ${q.position}, ${categoryLabel(q.category)}, ${q.answered ? "answered" : "unanswered"}`}
              className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                index === current ? "border-brand-300 bg-brand-50 text-brand-800" : "border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <span
                aria-hidden="true"
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                  q.answered ? "bg-mint-100 text-mint-700" : "bg-slate-100 text-slate-500"
                }`}
              >
                {q.answered ? <Icon name="check" className="h-3 w-3" /> : q.position}
              </span>
              <span className="hidden lg:inline">{categoryLabel(q.category)}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}

// One interview session: answer questions while it is open, then review the backend's results.
// Query: ?q=<index> keeps the current question in the URL.
export default function InterviewSessionPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const location = useLocation();
  const confirm = useConfirm();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const session = useApiResource(() => getSession(id), `session:${id}`, { enabled: Number.isInteger(id) && id > 0 });
  const llm = useApiResource(getLlmStatus, "llm-status");
  const [drafts, setDrafts] = useState({}); // question_id -> typed text (kept while navigating and on errors)
  const [results, setResults] = useState({}); // question_id -> AnswerOut from this visit
  const [ai, setAi] = useState({ useLlm: false, consent: false });
  const [action, setAction] = useState(null);
  const [actionError, setActionError] = useState(null);
  const busy = useRef(false);

  const data = session.data;
  const questions = data?.questions || [];
  const requested = Number(params.get("q"));
  const current = Number.isInteger(requested) && requested >= 0 && requested < questions.length ? requested : 0;

  useEffect(() => {
    if (!data) return undefined;
    const previous = document.title;
    document.title = `${data.title || "Interview session"} · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [data]);

  const select = (index) => {
    const next = new URLSearchParams(params);
    next.set("q", String(index));
    setParams(next, { replace: true });
  };

  const onAnswered = (question, answer) => {
    setResults((r) => ({ ...r, [question.question_id]: answer }));
    // Reflect the answer immediately, then refresh from the backend (answered counts, model answers).
    session.setData({
      ...data,
      status: "in_progress",
      answered_count: data.answered_count + (question.answered ? 0 : 1),
      questions: data.questions.map((q) =>
        q.question_id === question.question_id
          ? { ...q, answered: true, attempts: q.attempts + 1, latest_score: answer.score, latest_feedback: answer.feedback, evaluation: answer.evaluation }
          : q,
      ),
    });
    session.reload();
  };

  const onRevealed = (updated) => session.setData({ ...data, questions: data.questions.map((q) => (q.question_id === updated.question_id ? updated : q)) });

  const run = async (name, task) => {
    if (busy.current) return;
    busy.current = true;
    setAction(name);
    setActionError(null);
    try {
      await task();
    } catch (failure) {
      setActionError(errorMessage(failure));
      if (normalizeError(failure).status === 409) session.reload();
    } finally {
      busy.current = false;
      setAction(null);
    }
  };

  const onComplete = async () => {
    const unanswered = questions.filter((q) => !q.answered).length;
    const ok = await confirm({
      title: "Finish this session?",
      message:
        (unanswered
          ? `${unanswered} question${unanswered === 1 ? " is" : "s are"} unanswered and will count as 0 in the overall score. `
          : "All questions are answered. ") + "You can't add answers after finishing.",
      confirmLabel: "Finish session",
      tone: "primary",
    });
    if (!ok) return;
    await run("complete", async () => {
      session.setData(await completeSession(id));
      toast.success("Session finished. Here are your results.");
    });
  };

  const onDelete = async () => {
    const ok = await confirm({
      title: "Delete this session?",
      message: "This permanently deletes the session, its questions and all your answers. This cannot be undone.",
      confirmLabel: "Delete session",
      tone: "danger",
    });
    if (!ok) return;
    await run("delete", async () => {
      await deleteSession(id);
      toast.success("Session deleted.");
      navigate("/interview-prep", { replace: true });
    });
  };

  const back = (
    <Link to="/interview-prep" className="inline-flex w-fit items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
      <Icon name="arrowRight" className="h-4 w-4 rotate-180" />
      All sessions
    </Link>
  );

  if (session.status === "error" && session.error?.status === 404) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {back}
        <div className={panel}>
          <CardEmpty title="Session not found" message="This interview session doesn't exist, was deleted, or belongs to another account." />
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {back}
        <div className={panel}>
          {session.status === "error" ? <CardError error={session.error} onRetry={session.reload} label="the session" /> : <CardSkeleton label="the session" lines={6} />}
        </div>
      </div>
    );
  }

  const status = sessionStatus(data.status);
  const open = isOpen(data.status);
  const question = questions[current];
  const unanswered = questions.filter((q) => !q.answered).length;
  const generation = data.summary?.generation;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {back}
      <header className={`${panel} flex flex-col gap-3`}>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={status.tone}>{status.label}</Badge>
          <Badge>{modeLabel(data.mode)}</Badge>
          {data.difficulty && <Badge>Difficulty: {difficultyLabel(data.difficulty)}</Badge>}
          <Badge>{data.generation_method === "llm" ? "Includes AI-tailored questions" : "Question bank + your resume (no AI)"}</Badge>
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">{data.title || `Interview session #${data.session_id}`}</h1>
        <p className="text-sm text-slate-600">
          Started {formatDateTime(data.started_at)}
          {data.completed_at ? ` · finished ${formatDateTime(data.completed_at)}` : ""} · {data.answered_count}/{data.total_questions ?? questions.length} answered
          {data.internship_id ? (
            <>
              {" · "}
              <Link to={`/internships/${data.internship_id}`} className="font-medium text-brand-700 hover:underline">
                View internship
              </Link>
            </>
          ) : null}
        </p>
        {location.state?.created && open && (
          <p role="status" className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-800">
            Your questions are ready. Answer them in any order, then finish the session to see your results.
          </p>
        )}
        {data.notices?.length > 0 && (
          <ul className="flex flex-col gap-1.5" aria-label="Session notices">
            {data.notices.map((n, i) => (
              <li key={i} className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <span className="font-medium">{NOTICE_TITLE[n.code] || "Note"}</span>
                {n.category ? ` (${categoryLabel(n.category)}${n.requested != null ? `: ${n.generated ?? 0} of ${n.requested}` : ""})` : ""}: {n.detail}
              </li>
            ))}
          </ul>
        )}
        {generation?.llm?.used && (
          <p className="text-xs text-slate-500">
            AI-tailored questions: {generation.llm.accepted} accepted, {generation.llm.rejected} rejected by the fact check.
          </p>
        )}
        {data.status === "abandoned" && <p className="text-sm text-slate-600">This session was abandoned and can't be continued.</p>}
        <div className="flex flex-wrap gap-2">
          {open && (
            <Button onClick={onComplete} loading={action === "complete"} disabled={Boolean(action) || !questions.length}>
              {action !== "complete" && <Icon name="check" className="h-4 w-4" />}
              Finish session{unanswered ? ` (${unanswered} unanswered)` : ""}
            </Button>
          )}
          {!open && (
            <Link
              to={`/interview-prep${data.internship_id ? `?internship=${data.internship_id}` : ""}`}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
            >
              <Icon name="refresh" className="h-4 w-4" />
              Practise again
            </Link>
          )}
          <Button variant="danger" onClick={onDelete} loading={action === "delete"} disabled={Boolean(action)}>
            Delete
          </Button>
        </div>
        {actionError && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            {actionError}
          </p>
        )}
      </header>

      {data.status === "completed" && (
        <div className={panel}>
          <SessionSummary session={data} />
        </div>
      )}

      {!questions.length ? (
        <div className={panel}>
          <CardEmpty title="No questions in this session" message="The backend generated no questions. Start a new session with a different mix." />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[12rem_minmax(0,1fr)]">
          <div className="min-w-0 self-start lg:sticky lg:top-4">
            <Navigator questions={questions} current={current} onSelect={select} />
          </div>
          <div className={`${panel} flex min-w-0 flex-col gap-5`}>
            {open && <AiAssistChoice status={llm} useLlm={ai.useLlm} consent={ai.consent} onChange={setAi} copy={FEEDBACK_AI_COPY} />}
            <QuestionCard
              key={question.question_id}
              sessionId={id}
              question={question}
              total={questions.length}
              open={open}
              mode={data.mode}
              draft={drafts[question.question_id]}
              onDraft={(qid, text) => setDrafts((d) => ({ ...d, [qid]: text }))}
              ai={{ useLlm: ai.useLlm && Boolean(llm.data?.available), consent: ai.consent }}
              result={results[question.question_id]}
              onAnswered={onAnswered}
              onRevealed={onRevealed}
              onClosed={session.reload}
            />
            <div className="flex justify-between gap-2 border-t border-slate-100 pt-4">
              <Button variant="secondary" onClick={() => select(current - 1)} disabled={current === 0}>
                Previous
              </Button>
              <Button variant="secondary" onClick={() => select(current + 1)} disabled={current >= questions.length - 1}>
                Next
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
