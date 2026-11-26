import { useEffect, useRef, useState } from "react";
import { ANSWER_MAX, listAnswers, revealQuestion, submitAnswer } from "../../../api/interviews";
import { errorMessage, normalizeError } from "../../../api/errors";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import { formatDateTime } from "../../../utils/dates";
import { categoryLabel, difficultyLabel, formatScore, scoreTone } from "../interviewFormat";
import EvaluationView from "./EvaluationView";
import SuggestedAnswer from "./SuggestedAnswer";

export function validateAnswer(text) {
  if (!text.trim()) return "Write an answer before submitting.";
  if (text.length > ANSWER_MAX) return `Keep your answer under ${ANSWER_MAX.toLocaleString()} characters.`;
  return null;
}

function Attempts({ sessionId, questionId, count }) {
  const [state, setState] = useState({ status: "idle" });
  const load = async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "success", items: await listAnswers(sessionId, questionId) });
    } catch (failure) {
      setState({ status: "error", message: errorMessage(failure) });
    }
  };
  if (!count) return null;
  return (
    <div className="text-sm">
      {state.status !== "success" && (
        <Button variant="ghost" onClick={load} loading={state.status === "loading"} className="px-2 py-1 text-xs">
          Show your {count === 1 ? "answer" : `${count} attempts`}
        </Button>
      )}
      {state.status === "error" && (
        <p role="alert" className="text-xs text-red-700">
          Couldn't load your answers: {state.message}
        </p>
      )}
      {state.status === "success" && (
        <ol className="flex flex-col gap-2" aria-label="Your attempts">
          {state.items.map((a) => (
            <li key={a.answer_id} className="rounded-lg border border-slate-200 p-3">
              <p className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                Attempt {a.attempt} · {formatDateTime(a.created_at)}
                <Badge tone={scoreTone(a.score)}>
                  {formatScore(a.score)}/100 · {a.label}
                </Badge>
              </p>
              <p className="whitespace-pre-line text-sm text-slate-800">{a.answer_text}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// One interview question: its details, the answer editor, and the backend's evaluation.
export default function QuestionCard({ sessionId, question, total, open, mode, draft = "", onDraft, ai, result, onAnswered, onRevealed, onClosed }) {
  const [editing, setEditing] = useState(!question.answered);
  const [error, setError] = useState(null);
  const [apiError, setApiError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const busy = useRef(false);
  const shownAt = useRef(Date.now());
  const fieldId = `answer-${question.question_id}`;

  useEffect(() => {
    shownAt.current = Date.now();
  }, [editing]);

  const submit = async (event) => {
    event.preventDefault();
    if (busy.current) return;
    const problem = validateAnswer(draft);
    setError(problem);
    setApiError(null);
    if (problem) return;
    if (ai.useLlm && !ai.consent) {
      setError("Accept the disclosure to get AI feedback, or turn it off.");
      return;
    }
    busy.current = true;
    setSubmitting(true);
    try {
      const seconds = Math.min(3600, Math.max(0, Math.round((Date.now() - shownAt.current) / 1000)));
      const answer = await submitAnswer(sessionId, question.question_id, { answerText: draft, timeTakenSeconds: seconds, useLlm: ai.useLlm, consent: ai.consent });
      setEditing(false);
      onAnswered(question, answer);
    } catch (failure) {
      // The typed answer stays in the editor (it lives in the page's drafts).
      setApiError(failure);
      if (normalizeError(failure).status === 409) onClosed();
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  };

  const reveal = async () => {
    if (revealing) return;
    setRevealing(true);
    setApiError(null);
    try {
      onRevealed(await revealQuestion(sessionId, question.question_id));
    } catch (failure) {
      setApiError(failure);
    } finally {
      setRevealing(false);
    }
  };

  const evaluation = result
    ? { score: result.score, feedback: result.feedback, feedbackSource: result.feedback_source, evaluation: { ...result.evaluation, label: result.label } }
    : question.answered
      ? { score: question.latest_score, feedback: question.latest_feedback, evaluation: question.evaluation }
      : null;

  return (
    <article aria-labelledby={`q-${question.question_id}-title`} className="flex flex-col gap-4">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="info">{categoryLabel(question.category)}</Badge>
          {question.difficulty && <Badge>{difficultyLabel(question.difficulty)}</Badge>}
          {question.skill && <Badge>{question.skill}</Badge>}
          {question.time_limit_seconds ? <Badge tone="warning">Time limit {question.time_limit_seconds}s</Badge> : null}
          {question.answered ? <Badge tone="success">Answered{question.attempts > 1 ? ` · ${question.attempts} attempts` : ""}</Badge> : <Badge tone="warning">Unanswered</Badge>}
        </div>
        <p className="text-xs text-slate-500">
          Question {question.position} of {total}
        </p>
        <h2 id={`q-${question.question_id}-title`} className="text-lg font-semibold leading-snug text-slate-900">
          {question.text}
        </h2>
        {question.skill_status === "required_missing" && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">This skill is required by the internship but isn't on your resume. Answer honestly about your level.</p>
        )}
      </header>

      <SuggestedAnswer question={question} canReveal={open && mode === "mock"} onReveal={reveal} revealing={revealing} />

      {open && editing ? (
        <form onSubmit={submit} noValidate className="flex flex-col gap-2" aria-label={`Answer question ${question.position}`}>
          <label htmlFor={fieldId} className="text-sm font-medium text-slate-700">
            Your answer
          </label>
          <textarea
            id={fieldId}
            rows={8}
            value={draft}
            onChange={(e) => onDraft(question.question_id, e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby={`${fieldId}-hint`}
            className={`w-full rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${error ? "border-red-400" : "border-slate-300"}`}
          />
          <p id={`${fieldId}-hint`} className={`text-xs ${error ? "text-red-600" : "text-slate-500"}`} role={error ? "alert" : undefined}>
            {error || `${draft.length.toLocaleString()}/${ANSWER_MAX.toLocaleString()} characters. Write in full sentences.`}
          </p>
          <ErrorAlert error={apiError} title="Your answer couldn't be evaluated" />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" loading={submitting}>
              {submitting ? "Evaluating…" : question.answered ? "Submit new attempt" : "Submit answer"}
            </Button>
            {question.answered && (
              <Button variant="ghost" onClick={() => setEditing(false)} disabled={submitting}>
                Cancel
              </Button>
            )}
          </div>
        </form>
      ) : (
        <>
          {apiError && <ErrorAlert error={apiError} title="Something went wrong" />}
          {!question.answered && !open && <p className="text-sm text-slate-500">Not answered before the session was closed.</p>}
        </>
      )}

      {evaluation && (!editing || !open) && (
        <>
          <EvaluationView {...evaluation} />
          {open && (
            <div>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Try again
              </Button>
            </div>
          )}
        </>
      )}

      <Attempts key={question.attempts} sessionId={sessionId} questionId={question.question_id} count={question.attempts} />
    </article>
  );
}
