import Button from "../../../components/ui/Button";

const TYPE_TITLE = { key_points: "Key points to cover", star: "Structure your answer (STAR)", outline: "Suggested outline" };

// Model-answer guidance from the backend (QuestionOut.key_points / explanation / suggested_answer).
// In mock mode the backend sends these as null until the question is answered or revealed.
export default function SuggestedAnswer({ question, canReveal, onReveal, revealing }) {
  const s = question.suggested_answer;
  const hidden = s == null && question.key_points == null && question.explanation == null;
  if (hidden) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed border-slate-300 p-3 text-sm text-slate-600">
        <span>Mock interview: the model answer is hidden until you answer this question.</span>
        {canReveal && (
          <Button variant="secondary" onClick={onReveal} loading={revealing} className="py-1.5">
            Reveal the model answer
          </Button>
        )}
      </div>
    );
  }
  const points = s?.points?.length ? s.points : question.key_points || [];
  return (
    <details className="rounded-xl border border-slate-200 p-3 text-sm">
      <summary className="cursor-pointer font-medium text-slate-800">Model answer guidance</summary>
      <div className="mt-2 flex flex-col gap-2 text-slate-700">
        {points.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-500">{TYPE_TITLE[s?.type] || "Key points"}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5" aria-label="Model answer points">
              {points.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        {(s?.explanation || question.explanation) && <p className="text-xs text-slate-600">{s?.explanation || question.explanation}</p>}
        {s?.note && <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">{s.note}</p>}
        {s?.tips?.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-500">Tips</p>
            <ul className="mt-1 list-disc pl-5 text-xs">
              {s.tips.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
        )}
        {s?.possible_stories?.length > 0 && (
          <p className="text-xs">
            <span className="font-medium text-slate-500">Stories from your resume you could use: </span>
            {s.possible_stories.join("; ")}
          </p>
        )}
        {s?.from_your_resume?.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-500">From your resume</p>
            <ul className="mt-1 list-disc pl-5 text-xs">
              {s.from_your_resume.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
