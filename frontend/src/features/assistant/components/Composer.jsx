import { forwardRef } from "react";
import { MESSAGE_MAX } from "../../../api/assistant";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";
import AiAssistChoice from "../../documents/components/AiAssistChoice";

export const ASSISTANT_AI_COPY = {
  legend: "Answer style",
  feature: "AI rewording",
  deterministic: (
    <>
      Answers use the <span className="font-medium text-slate-800">standard, fact-based method</span>: built only from your own data and the internship
      knowledge base, with sources. No AI is used.
    </>
  ),
  byDefault: "By default answers are built from your data with the standard method, and nothing leaves this service.",
  hint: "Optional. Rewords the answer's facts in a more natural way. Every AI sentence is checked against those facts; if it can't be verified, the standard answer is shown.",
  consent: "I have read this and agree to AI rewording for my messages in this conversation",
};

export function validateMessage(text, max = MESSAGE_MAX) {
  if (!text.trim()) return "Type a question first.";
  if (text.length > max) return `Keep your message under ${max.toLocaleString()} characters.`;
  return null;
}

// Message box. Enter sends, Shift+Enter adds a line. The text stays here until the backend accepts it.
const Composer = forwardRef(function Composer({ value, onChange, onSubmit, sending, error, max = MESSAGE_MAX, llm, ai, onAi, aiError }, ref) {
  const onKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent?.isComposing) {
      event.preventDefault();
      onSubmit();
    }
  };
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      noValidate
      aria-label="Ask the assistant"
      className="flex flex-col gap-2"
    >
      <AiAssistChoice status={llm} useLlm={ai.useLlm} consent={ai.consent} onChange={onAi} error={aiError} copy={ASSISTANT_AI_COPY} />
      <label htmlFor="assistant-message" className="sr-only">
        Your question
      </label>
      <div className="flex items-end gap-2">
        <textarea
          id="assistant-message"
          ref={ref}
          rows={2}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about your skills, matches, documents, interviews or applications…"
          aria-invalid={error ? true : undefined}
          aria-describedby="assistant-message-hint"
          className={`max-h-48 min-h-[3rem] flex-1 resize-y rounded-xl border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${
            error ? "border-red-400" : "border-slate-300"
          }`}
        />
        <Button type="submit" loading={sending} aria-label="Send message" className="h-11 shrink-0 px-3">
          {!sending && <Icon name="arrowRight" className="h-4 w-4" />}
          <span className="hidden sm:inline">{sending ? "Sending…" : "Send"}</span>
        </Button>
      </div>
      <p id="assistant-message-hint" className={`text-xs ${error ? "text-red-600" : "text-slate-500"}`} role={error ? "alert" : undefined}>
        {error || `${value.length.toLocaleString()}/${max.toLocaleString()} · Enter to send, Shift+Enter for a new line`}
      </p>
    </form>
  );
});

export default Composer;
