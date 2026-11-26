import Checkbox from "../../../components/ui/Checkbox";

// Wording for each place the choice is offered. Documents is the default (F6).
export const AI_COPY = {
  document: {
    legend: "Writing method",
    feature: "AI-assisted writing",
    deterministic: (
      <>
        Your document will be generated with the <span className="font-medium text-slate-800">deterministic, fact-based method</span>: only information
        from your resume, arranged for this internship.
      </>
    ),
    byDefault: "By default the document is generated with the deterministic, fact-based method and nothing leaves this service.",
    hint: "Optional. Every AI-written statement is fact-checked against your resume; unsupported statements are removed.",
    consent: "I have read this and agree to AI-assisted writing for this document",
  },
};

// Optional AI assistance (backend: use_llm + llm_consent, disclosure from GET /documents/llm-status).
// Off by default. When the server has no AI provider configured, only the deterministic method is
// offered. Consent must be given explicitly before an AI request can be submitted.
export default function AiAssistChoice({ status, useLlm, consent, onChange, error, copy = AI_COPY.document }) {
  if (status.status === "loading" || status.status === "idle") {
    return <p className="text-xs text-slate-500">Checking whether {copy.feature} is available…</p>;
  }
  if (status.status === "error" || !status.data?.available) {
    return (
      <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        {status.status === "error" ? `${capitalise(copy.feature)} status couldn't be checked, so it's turned off. ` : `${capitalise(copy.feature)} isn't configured on this server. `}
        {copy.deterministic}
      </p>
    );
  }
  const { provider, model, disclosure } = status.data;
  return (
    <fieldset className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4">
      <legend className="px-1 text-sm font-medium text-slate-700">{copy.legend}</legend>
      <p className="text-xs text-slate-600">{copy.byDefault}</p>
      <Checkbox
        label={`Use ${copy.feature} (${provider}${model ? `, ${model}` : ""})`}
        hint={copy.hint}
        checked={useLlm}
        onChange={(e) => onChange({ useLlm: e.target.checked, consent: e.target.checked ? consent : false })}
      />
      {useLlm && (
        <div className="flex flex-col gap-2 rounded-lg bg-amber-50 p-3">
          <p className="text-xs font-medium text-amber-900">Privacy disclosure</p>
          <p className="text-xs text-amber-900">{disclosure}</p>
          <Checkbox label={copy.consent} checked={consent} onChange={(e) => onChange({ useLlm, consent: e.target.checked })} />
          {error && (
            <p className="text-xs text-red-700" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </fieldset>
  );
}

const capitalise = (s) => s.charAt(0).toUpperCase() + s.slice(1);
