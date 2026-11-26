import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createCoverLetter, createResumeDocument, getLlmStatus, MAX_EMPHASIS, RESUME_OPTIONS, TONES } from "../../../api/documents";
import { errorMessage } from "../../../api/errors";
import { getInternship } from "../../../api/internships";
import { getResumeSkills, listResumes } from "../../../api/resumes";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import Icon from "../../../components/ui/Icon";
import Select from "../../../components/ui/Select";
import useApiResource from "../../../hooks/useApiResource";
import { formatDate } from "../../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import AiAssistChoice from "./AiAssistChoice";
import InternshipPicker from "./InternshipPicker";

const TYPES = [
  { id: "resume", label: "Tailored resume", icon: "document" },
  { id: "cover_letter", label: "Cover letter", icon: "edit" },
];
const defaultOptions = () => Object.fromEntries(Object.entries(RESUME_OPTIONS).map(([k, v]) => [k, String(v.default)]));

export function validateOptions(options) {
  const errors = {};
  for (const [key, rule] of Object.entries(RESUME_OPTIONS)) {
    const raw = String(options[key] ?? "").trim();
    const n = Number(raw);
    if (!/^\d+$/.test(raw) || n < rule.min || n > rule.max) errors[key] = `Enter a whole number from ${rule.min} to ${rule.max}.`;
  }
  return errors;
}

// Create a tailored resume or cover letter from the student's parsed resume and a chosen internship.
export default function CreateDocumentForm({ initialType = "resume", initialInternshipId = null, initialResumeId = null }) {
  const navigate = useNavigate();
  const [type, setType] = useState(initialType === "cover_letter" ? "cover_letter" : "resume");
  const resumes = useApiResource(listResumes, "resumes");
  const parsed = (resumes.data || []).filter((r) => r.status === "completed");
  const [resumeId, setResumeId] = useState(null);
  // undefined = not chosen by the student yet (a link's pre-selected internship is used);
  // null = the student cleared it with "Change".
  const [chosenInternship, setInternship] = useState(undefined);
  const [options, setOptions] = useState(defaultOptions);
  const [tone, setTone] = useState("formal");
  const [emphasis, setEmphasis] = useState([]);
  const [ai, setAi] = useState({ useLlm: false, consent: false });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const busy = useRef(false);
  const llm = useApiResource(getLlmStatus, "llm-status");

  // Default to the requested resume if it is parsed, otherwise the latest parsed one.
  useEffect(() => {
    if (resumeId || !parsed.length) return;
    const requested = parsed.find((r) => r.resume_id === Number(initialResumeId));
    setResumeId((requested || parsed[0]).resume_id);
  }, [parsed, resumeId, initialResumeId]);

  // Pre-select an internship passed in the URL (?internship=ID).
  // Derived during render, so the search box never flashes before the pre-selection appears.
  const preset = useApiResource(() => getInternship(Number(initialInternshipId)), initialInternshipId, { enabled: Boolean(initialInternshipId) });
  const internship = chosenInternship !== undefined ? chosenInternship : preset.status === "success" ? preset.data : null;

  const skills = useApiResource(() => getResumeSkills(resumeId), resumeId, { enabled: Boolean(resumeId) && type === "cover_letter" });
  useEffect(() => setEmphasis([]), [resumeId]);

  const toggleEmphasis = (name) =>
    setEmphasis((current) => (current.includes(name) ? current.filter((s) => s !== name) : current.length < MAX_EMPHASIS ? [...current, name] : current));

  const submit = async (event) => {
    event.preventDefault();
    if (busy.current) return; // one generation at a time
    const found = {};
    if (!resumeId) found.resume = "Choose a resume.";
    if (!internship) found.internship = "Choose the internship you're applying to.";
    if (type === "resume") Object.assign(found, validateOptions(options));
    if (ai.useLlm && !ai.consent) found.consent = "Accept the disclosure to use AI-assisted writing, or turn it off.";
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length) return;

    busy.current = true;
    setSubmitting(true);
    try {
      const common = { resumeId, internshipId: internship.internship_id, useLlm: ai.useLlm && llm.data?.available, consent: ai.consent };
      const document =
        type === "resume"
          ? await createResumeDocument({ ...common, options: Object.fromEntries(Object.entries(options).map(([k, v]) => [k, Number(v)])) })
          : await createCoverLetter({ ...common, tone, emphasizeSkills: emphasis });
      navigate(`/documents/${document.document_id}`, { state: { created: true } });
    } catch (failure) {
      setApiError(failure);
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  };

  if (resumes.status === "loading" || resumes.status === "idle") return <CardSkeleton label="your resumes" lines={4} />;
  if (resumes.status === "error") return <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />;
  if (!parsed.length) {
    return (
      <CardEmpty
        title="Upload a resume first"
        message="Documents are built only from information on a successfully parsed resume."
        action={<Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">Go to resumes</Link>}
      />
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5" aria-label="Create a document">
      <div role="radiogroup" aria-label="Document type" className="inline-flex w-fit rounded-lg bg-slate-100 p-1">
        {TYPES.map((t) => (
          <button
            key={t.id}
            type="button"
            role="radio"
            aria-checked={type === t.id}
            onClick={() => setType(t.id)}
            className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
              type === t.id ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Icon name={t.icon} className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      <Select
        label="Resume to use"
        value={resumeId ? String(resumeId) : ""}
        onChange={(e) => setResumeId(Number(e.target.value))}
        error={errors.resume}
        options={parsed.map((r, i) => ({ value: String(r.resume_id), label: `${r.filename} · ${formatDate(r.uploaded_at)}${i === 0 ? " (latest)" : ""}` }))}
      />

      {preset.status === "error" ? (
        <p role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          The internship from your link isn't available ({errorMessage(preset.error)}). Choose another one below.
        </p>
      ) : null}
      {preset.status === "loading" ? <CardSkeleton label="the internship" lines={1} /> : <InternshipPicker value={internship} onChange={setInternship} error={errors.internship} />}

      {type === "resume" ? (
        <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <legend className="mb-2 text-sm font-medium text-slate-700">Layout</legend>
          {Object.entries(RESUME_OPTIONS).map(([key, rule]) => (
            <div key={key} className="flex flex-col gap-1">
              <label htmlFor={`opt-${key}`} className="text-sm text-slate-700">
                {rule.label}
              </label>
              <input
                id={`opt-${key}`}
                inputMode="numeric"
                value={options[key]}
                onChange={(e) => setOptions((o) => ({ ...o, [key]: e.target.value }))}
                aria-invalid={errors[key] ? true : undefined}
                aria-describedby={`opt-${key}-hint`}
                className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${errors[key] ? "border-red-400" : "border-slate-300"}`}
              />
              <p id={`opt-${key}-hint`} className={`text-xs ${errors[key] ? "text-red-600" : "text-slate-500"}`}>
                {errors[key] || `${rule.min}–${rule.max}`}
              </p>
            </div>
          ))}
        </fieldset>
      ) : (
        <>
          <Select label="Tone" value={tone} onChange={(e) => setTone(e.target.value)} options={TONES.map((t) => ({ value: t, label: t === "formal" ? "Formal" : "Concise" }))} />
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-slate-700">Skills to emphasise (optional, up to {MAX_EMPHASIS})</legend>
            <p className="text-xs text-slate-500">Only skills on your resume can be emphasised.</p>
            {skills.status === "loading" || skills.status === "idle" ? (
              <CardSkeleton label="your skills" lines={1} />
            ) : skills.status === "error" ? (
              <CardError error={skills.error} onRetry={skills.reload} label="your skills" />
            ) : skills.data.skills.length ? (
              <div className="flex flex-wrap gap-1.5">
                {skills.data.skills.map((s) => {
                  const on = emphasis.includes(s.name);
                  return (
                    <button
                      key={s.skill_id}
                      type="button"
                      aria-pressed={on}
                      disabled={!on && emphasis.length >= MAX_EMPHASIS}
                      onClick={() => toggleEmphasis(s.name)}
                      className={`rounded-full border px-3 py-1 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:opacity-50 ${
                        on ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      {s.name}
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No recognised skills on this resume.</p>
            )}
          </fieldset>
        </>
      )}

      <AiAssistChoice status={llm} useLlm={ai.useLlm} consent={ai.consent} onChange={setAi} error={errors.consent} />

      <ErrorAlert error={apiError} title="The document couldn't be created" />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={submitting}>
          {!submitting && <Icon name="sparkles" className="h-4 w-4" />}
          {submitting ? "Generating…" : type === "resume" ? "Generate tailored resume" : "Generate cover letter"}
        </Button>
        <p className="text-xs text-slate-500">You'll review the result before downloading it.</p>
      </div>
    </form>
  );
}
