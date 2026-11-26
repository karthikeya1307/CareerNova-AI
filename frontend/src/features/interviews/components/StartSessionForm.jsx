import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listCareerTracks } from "../../../api/careerTracks";
import { errorMessage } from "../../../api/errors";
import { getInternship } from "../../../api/internships";
import { createSession, DIFFICULTIES, getLlmStatus, MIX, MIX_TOTAL, MODES, TIME_LIMIT } from "../../../api/interviews";
import { listResumes } from "../../../api/resumes";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import Icon from "../../../components/ui/Icon";
import Select from "../../../components/ui/Select";
import useApiResource from "../../../hooks/useApiResource";
import { formatDate } from "../../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import AiAssistChoice from "../../documents/components/AiAssistChoice";
import InternshipPicker from "../../documents/components/InternshipPicker";
import { difficultyLabel } from "../interviewFormat";

export const INTERVIEW_AI_COPY = {
  legend: "AI-tailored questions",
  feature: "AI-tailored questions",
  deterministic: (
    <>
      Questions come from the <span className="font-medium text-slate-800">built-in question bank and your resume</span>, and answers are scored with a
      rubric. No AI is used.
    </>
  ),
  byDefault: "By default questions come from the built-in question bank and your resume, and nothing leaves this service.",
  hint: "Optional. Adds up to 2 extra questions written by AI from your resume; each is checked against your resume before it is used.",
  consent: "I have read this and agree to AI-tailored questions for this session",
};

const defaultMix = () => Object.fromEntries(Object.entries(MIX).map(([k, v]) => [k, String(v.default)]));
const whole = (raw) => /^\d+$/.test(String(raw ?? "").trim());

// Mirrors CreateSessionRequest validation (QuestionMix limits and total 1-15, time limit 30-900 s).
export function validateSessionForm({ mix, mode, timeLimit }) {
  const errors = {};
  let total = 0;
  for (const [key, rule] of Object.entries(MIX)) {
    const n = Number(String(mix[key] ?? "").trim());
    if (!whole(mix[key]) || n < rule.min || n > rule.max) errors[key] = `Enter a whole number from ${rule.min} to ${rule.max}.`;
    else total += n;
  }
  if (!Object.keys(errors).length && (total < MIX_TOTAL.min || total > MIX_TOTAL.max)) {
    errors.mix = `Choose ${MIX_TOTAL.min}–${MIX_TOTAL.max} questions in total (currently ${total}).`;
  }
  if (mode === "mock" && String(timeLimit ?? "").trim() !== "") {
    const n = Number(timeLimit);
    if (!whole(timeLimit) || n < TIME_LIMIT.min || n > TIME_LIMIT.max) {
      errors.timeLimit = `Enter ${TIME_LIMIT.min}–${TIME_LIMIT.max} seconds, or leave it empty for no limit.`;
    }
  }
  return errors;
}

// Start an interview session from a parsed resume, optionally for one internship.
export default function StartSessionForm({ initialInternshipId = null, initialResumeId = null, initialRole = null, initialMode = null }) {
  const navigate = useNavigate();
  const resumes = useApiResource(listResumes, "resumes");
  const parsed = (resumes.data || []).filter((r) => r.status === "completed");
  const [resumeId, setResumeId] = useState(null);
  const [chosenInternship, setInternship] = useState(undefined); // undefined = use the link's internship
  const [mode, setMode] = useState(initialMode === "mock" ? "mock" : "practice");
  const tracks = useApiResource(listCareerTracks, "career-tracks");
  const [targetRole, setTargetRole] = useState(/^[a-z0-9-]+$/.test(initialRole || "") ? initialRole : "");
  const [difficulty, setDifficulty] = useState("mixed");
  const [mix, setMix] = useState(defaultMix);
  const [timeLimit, setTimeLimit] = useState("");
  const [ai, setAi] = useState({ useLlm: false, consent: false });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const busy = useRef(false);
  const llm = useApiResource(getLlmStatus, "llm-status");

  useEffect(() => {
    if (resumeId || !parsed.length) return;
    const requested = parsed.find((r) => r.resume_id === Number(initialResumeId));
    setResumeId((requested || parsed[0]).resume_id);
  }, [parsed, resumeId, initialResumeId]);

  const preset = useApiResource(() => getInternship(Number(initialInternshipId)), initialInternshipId, { enabled: Boolean(initialInternshipId) });
  const internship = chosenInternship !== undefined ? chosenInternship : preset.status === "success" ? preset.data : null;

  const total = Object.values(mix).reduce((sum, v) => sum + (whole(v) ? Number(v) : 0), 0);

  const submit = async (event) => {
    event.preventDefault();
    if (busy.current) return; // one session at a time
    const found = validateSessionForm({ mix, mode, timeLimit });
    if (!resumeId) found.resume = "Choose a resume.";
    if (ai.useLlm && !ai.consent) found.consent = "Accept the disclosure to use AI-tailored questions, or turn it off.";
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length) return;

    busy.current = true;
    setSubmitting(true);
    try {
      const session = await createSession({
        resumeId,
        internshipId: internship?.internship_id ?? null,
        targetRole: targetRole || null,
        mode,
        difficulty,
        mix: Object.fromEntries(Object.entries(mix).map(([k, v]) => [k, Number(v)])),
        timeLimitSeconds: mode === "mock" && timeLimit.trim() ? Number(timeLimit) : null,
        useLlm: ai.useLlm && Boolean(llm.data?.available),
        consent: ai.consent,
      });
      navigate(`/interview-prep/sessions/${session.session_id}`, { state: { created: true } });
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
        message="Interview questions are generated from a successfully parsed resume."
        action={<Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">Go to resumes</Link>}
      />
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5" aria-label="Start an interview session">
      <Select
        label="Resume to use"
        value={resumeId ? String(resumeId) : ""}
        onChange={(e) => setResumeId(Number(e.target.value))}
        error={errors.resume}
        options={parsed.map((r, i) => ({ value: String(r.resume_id), label: `${r.filename} · ${formatDate(r.uploaded_at)}${i === 0 ? " (latest)" : ""}` }))}
      />

      {preset.status === "error" ? (
        <p role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          The internship from your link isn't available ({errorMessage(preset.error)}). Choose another one or continue without one.
        </p>
      ) : null}
      {preset.status === "loading" ? (
        <CardSkeleton label="the internship" lines={1} />
      ) : (
        <div className="flex flex-col gap-1">
          <InternshipPicker value={internship} onChange={setInternship} legend="Target internship (optional)" />
          {!internship && (
            <p className="text-xs text-slate-500">Without an internship you get general questions; internship-specific questions are replaced with behavioural ones.</p>
          )}
        </div>
      )}

      <Select
        label="Target role (optional)"
        value={targetRole}
        onChange={(e) => setTargetRole(e.target.value)}
        disabled={tracks.status !== "success"}
        options={[
          { value: "", label: tracks.status === "success" ? "Any role - questions from your resume" : "Loading roles…" },
          ...(tracks.data || []).map((t) => ({ value: t.slug, label: t.title })),
        ]}
      />
      {targetRole && (
        <p className="-mt-3 text-xs text-slate-500">
          Technical questions focus on this role's skills: the ones on your resume first, then the role's core skills you are missing.
        </p>
      )}

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium text-slate-700">Interview type</legend>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {MODES.map((m) => (
            <label
              key={m.id}
              className={`flex cursor-pointer gap-3 rounded-xl border p-3 text-sm ${mode === m.id ? "border-brand-300 bg-brand-50/60" : "border-slate-200 hover:bg-slate-50"}`}
            >
              <input type="radio" name="mode" value={m.id} checked={mode === m.id} onChange={() => setMode(m.id)} className="mt-0.5 h-4 w-4 text-brand-600 focus:ring-brand-500" />
              <span>
                <span className="block font-medium text-slate-900">{m.label}</span>
                <span className="block text-xs text-slate-500">{m.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Select label="Difficulty" value={difficulty} onChange={(e) => setDifficulty(e.target.value)} options={DIFFICULTIES.map((d) => ({ value: d, label: difficultyLabel(d) }))} />
        {mode === "mock" && (
          <div className="flex flex-col gap-1">
            <label htmlFor="time-limit" className="text-sm font-medium text-slate-700">
              Time limit per question (seconds, optional)
            </label>
            <input
              id="time-limit"
              inputMode="numeric"
              value={timeLimit}
              onChange={(e) => setTimeLimit(e.target.value)}
              aria-invalid={errors.timeLimit ? true : undefined}
              aria-describedby="time-limit-hint"
              className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${errors.timeLimit ? "border-red-400" : "border-slate-300"}`}
            />
            <p id="time-limit-hint" className={`text-xs ${errors.timeLimit ? "text-red-600" : "text-slate-500"}`}>
              {errors.timeLimit || `${TIME_LIMIT.min}–${TIME_LIMIT.max}. Leave empty for no limit.`}
            </p>
          </div>
        )}
      </div>

      <fieldset className="flex flex-col gap-3" aria-describedby="mix-total">
        <legend className="mb-1 text-sm font-medium text-slate-700">Questions per category</legend>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Object.entries(MIX).map(([key, rule]) => (
            <div key={key} className="flex flex-col gap-1">
              <label htmlFor={`mix-${key}`} className="text-sm text-slate-700">
                {rule.label}
              </label>
              <input
                id={`mix-${key}`}
                inputMode="numeric"
                value={mix[key]}
                onChange={(e) => setMix((m) => ({ ...m, [key]: e.target.value }))}
                aria-invalid={errors[key] ? true : undefined}
                aria-describedby={`mix-${key}-hint`}
                className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${errors[key] ? "border-red-400" : "border-slate-300"}`}
              />
              <p id={`mix-${key}-hint`} className={`text-xs ${errors[key] ? "text-red-600" : "text-slate-500"}`}>
                {errors[key] || `${rule.min}–${rule.max}`}
              </p>
            </div>
          ))}
        </div>
        <p id="mix-total" className={`text-xs ${errors.mix ? "text-red-600" : "text-slate-500"}`} role={errors.mix ? "alert" : undefined}>
          {errors.mix || `${total} question${total === 1 ? "" : "s"} in total (${MIX_TOTAL.min}–${MIX_TOTAL.max}). The backend may generate fewer if your resume has too little to ask about; it tells you why.`}
        </p>
      </fieldset>

      <AiAssistChoice status={llm} useLlm={ai.useLlm} consent={ai.consent} onChange={setAi} error={errors.consent} copy={INTERVIEW_AI_COPY} />

      <ErrorAlert error={apiError} title="The session couldn't be started" />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={submitting}>
          {!submitting && <Icon name="mic" className="h-4 w-4" />}
          {submitting ? "Preparing questions…" : "Start interview"}
        </Button>
        <p className="text-xs text-slate-500">Answers are scored automatically as practice guidance, not a hiring decision.</p>
      </div>
    </form>
  );
}
