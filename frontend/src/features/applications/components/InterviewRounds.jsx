import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  addInterviewRound, deleteInterviewRound, INTERVIEW_ALLOWED, INTERVIEW_MODES, INTERVIEW_OUTCOMES, INTERVIEW_TYPES, LIMITS, listInterviewRounds,
  updateInterviewRound,
} from "../../../api/applications";
import { errorMessage } from "../../../api/errors";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import Input from "../../../components/ui/Input";
import Select from "../../../components/ui/Select";
import { useConfirm } from "../../../context/ConfirmContext";
import useApiResource from "../../../hooks/useApiResource";
import { formatDateTime, isoToLocalInput, localInputToIso } from "../../../utils/dates";
import { CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import { safeExternalUrl } from "../../resumes/resumeData";
import { applicationStatus, INTERVIEW_MODE_LABEL, INTERVIEW_TYPE_LABEL, outcome, OUTCOME } from "../applicationFormat";

const TWO_YEARS = 730 * 24 * 3600 * 1000;
const blank = { interview_type: "technical", mode: "online", scheduled_at: "", duration_minutes: "", meeting_url: "", location: "", preparation_notes: "", feedback: "", outcome: "pending" };
const fromRound = (r) => ({
  interview_type: r.interview_type, mode: r.mode, scheduled_at: isoToLocalInput(r.scheduled_at), duration_minutes: r.duration_minutes ? String(r.duration_minutes) : "",
  meeting_url: r.meeting_url || "", location: r.location || "", preparation_notes: r.preparation_notes || "", feedback: r.feedback || "", outcome: r.outcome,
});

// Mirrors InterviewCreate/InterviewUpdate: scheduled_at within two years of today, duration 5-600 min,
// http(s) meeting link, notes up to 5000 characters.
export function validateRound(form, now = new Date()) {
  const errors = {};
  const when = form.scheduled_at ? new Date(form.scheduled_at) : null;
  if (!when || Number.isNaN(when.getTime())) errors.scheduled_at = "Choose the date and time.";
  else if (Math.abs(when.getTime() - now.getTime()) > TWO_YEARS) errors.scheduled_at = "Choose a date within two years of today.";
  if (form.duration_minutes !== "") {
    const n = Number(form.duration_minutes);
    if (!/^\d+$/.test(String(form.duration_minutes)) || n < 5 || n > 600) errors.duration_minutes = "Enter 5–600 minutes.";
  }
  if (form.meeting_url.trim() && !/^https?:\/\/[^\s/]+\S*$/i.test(form.meeting_url.trim())) errors.meeting_url = "Enter a full http:// or https:// link.";
  if (form.location.length > 200) errors.location = "Use at most 200 characters.";
  if (form.preparation_notes.length > LIMITS.notes) errors.preparation_notes = `Keep notes under ${LIMITS.notes} characters.`;
  if (form.feedback.length > LIMITS.notes) errors.feedback = `Keep feedback under ${LIMITS.notes} characters.`;
  return errors;
}

function toBody(form, original) {
  const body = {
    interview_type: form.interview_type,
    mode: form.mode,
    scheduled_at: localInputToIso(form.scheduled_at),
    outcome: form.outcome,
  };
  const optional = {
    duration_minutes: form.duration_minutes === "" ? null : Number(form.duration_minutes),
    meeting_url: form.meeting_url.trim() || null,
    location: form.location.trim() || null,
    preparation_notes: form.preparation_notes.trim() ? form.preparation_notes : null,
    feedback: form.feedback.trim() ? form.feedback : null,
  };
  for (const [k, v] of Object.entries(optional)) {
    // On create, leave out empty fields; on edit, send null only to clear a value that was set.
    if (v !== null || (original && original[k] != null)) body[k] = v;
  }
  return body;
}

function RoundForm({ initial, original, submitLabel, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  const submit = async (event) => {
    event.preventDefault();
    if (lock.current) return;
    const found = validateRound(form);
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length) return;
    lock.current = true;
    setBusy(true);
    try {
      await onSubmit(toBody(form, original));
    } catch (failure) {
      setApiError(failure);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} noValidate aria-label={submitLabel} className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select label="Interview type" value={form.interview_type} onChange={set("interview_type")} options={INTERVIEW_TYPES.map((t) => ({ value: t, label: INTERVIEW_TYPE_LABEL[t] }))} />
        <Select label="Mode" value={form.mode} onChange={set("mode")} options={INTERVIEW_MODES.map((m) => ({ value: m, label: INTERVIEW_MODE_LABEL[m] }))} />
        <Input label="Date and time" type="datetime-local" value={form.scheduled_at} onChange={set("scheduled_at")} error={errors.scheduled_at} required />
        <Input label="Duration in minutes (optional)" inputMode="numeric" value={form.duration_minutes} onChange={set("duration_minutes")} error={errors.duration_minutes} />
        {form.mode === "online" ? (
          <Input label="Meeting link (optional)" type="url" value={form.meeting_url} onChange={set("meeting_url")} error={errors.meeting_url} placeholder="https://" />
        ) : (
          <Input label="Location (optional)" value={form.location} onChange={set("location")} error={errors.location} maxLength={200} />
        )}
        <Select label="Outcome" value={form.outcome} onChange={set("outcome")} options={INTERVIEW_OUTCOMES.map((o) => ({ value: o, label: OUTCOME[o].label }))} />
      </div>
      <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
        Preparation notes (optional)
        <textarea rows={2} value={form.preparation_notes} onChange={set("preparation_notes")} className="rounded-md border border-slate-300 px-3 py-2 text-sm font-normal shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
        {errors.preparation_notes && <span className="text-xs font-normal text-red-600">{errors.preparation_notes}</span>}
      </label>
      {original && (
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
          Feedback (optional)
          <textarea rows={2} value={form.feedback} onChange={set("feedback")} className="rounded-md border border-slate-300 px-3 py-2 text-sm font-normal shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
          {errors.feedback && <span className="text-xs font-normal text-red-600">{errors.feedback}</span>}
        </label>
      )}
      <ErrorAlert error={apiError} title="The interview round couldn't be saved" />
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          {submitLabel}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// Company interview rounds for one application (GET/POST /applications/{id}/interviews,
// PATCH/DELETE /applications/interviews/{iid}). Adding a round or cancelling all rounds can move the
// application status; the backend reports it as status_change.
export default function InterviewRounds({ application, onStatusChange }) {
  const confirm = useConfirm();
  const rounds = useApiResource(() => listInterviewRounds(application.application_id), `rounds:${application.application_id}`);
  const [mode, setMode] = useState(null); // "add" | interview_id being edited
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const canAdd = INTERVIEW_ALLOWED.includes(application.status);

  const after = (change) => {
    rounds.reload();
    setMode(null);
    if (change) {
      setNotice(`Status changed automatically: ${applicationStatus(change.from_status).label} → ${applicationStatus(change.to_status).label}.`);
    }
    onStatusChange();
  };
  const add = async (body) => after((await addInterviewRound(application.application_id, body)).status_change);
  const edit = (id) => async (body) => after((await updateInterviewRound(id, body)).status_change);
  const remove = async (r) => {
    const ok = await confirm({
      title: `Delete round ${r.round_number}?`,
      message: "The round is deleted. If you want to keep a record that it was called off, set its outcome to Cancelled instead.",
      confirmLabel: "Delete round",
      tone: "danger",
    });
    if (!ok) return;
    setError(null);
    try {
      after((await deleteInterviewRound(r.interview_id)).status_change);
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };

  return (
    <section aria-labelledby="rounds-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="rounds-title" className="text-base font-semibold text-slate-900">
          Company interviews
        </h2>
        {canAdd && mode !== "add" && (
          <Button variant="secondary" onClick={() => setMode("add")} className="py-1.5">
            Add interview round
          </Button>
        )}
      </div>
      <p className="text-xs text-slate-500">Real interviews with the company. Practice sessions are in Interview practice.</p>
      {!canAdd && <p className="text-sm text-slate-500">Interview rounds can be added once the application is submitted (status is {applicationStatus(application.status).label}).</p>}
      {notice && (
        <p role="status" className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-800">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {mode === "add" && <RoundForm initial={blank} submitLabel="Add round" onSubmit={add} onCancel={() => setMode(null)} />}
      {(rounds.status === "loading" || rounds.status === "idle") && !rounds.data ? (
        <CardSkeleton label="interview rounds" lines={2} />
      ) : rounds.status === "error" ? (
        <CardError error={rounds.error} onRetry={rounds.reload} label="interview rounds" />
      ) : !rounds.data.length ? (
        <p className="text-sm text-slate-500">No interview rounds yet.</p>
      ) : (
        <ol className="flex flex-col gap-2" aria-label="Interview rounds">
          {rounds.data.map((r) =>
            mode === r.interview_id ? (
              <li key={r.interview_id}>
                <RoundForm initial={fromRound(r)} original={r} submitLabel={`Save round ${r.round_number}`} onSubmit={edit(r.interview_id)} onCancel={() => setMode(null)} />
              </li>
            ) : (
              <li key={r.interview_id} className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 text-sm">
                  <p className="font-medium text-slate-900">
                    Round {r.round_number}: {INTERVIEW_TYPE_LABEL[r.interview_type] || r.interview_type} · {INTERVIEW_MODE_LABEL[r.mode] || r.mode}
                  </p>
                  <p className="text-slate-600">
                    {formatDateTime(r.scheduled_at)}
                    {r.duration_minutes ? ` · ${r.duration_minutes} min` : ""}
                  </p>
                  {safeExternalUrl(r.meeting_url) && (
                    <a href={safeExternalUrl(r.meeting_url)} target="_blank" rel="noopener noreferrer" className="break-all text-brand-700 hover:underline">
                      Meeting link
                    </a>
                  )}
                  {r.location && <p className="text-slate-600">{r.location}</p>}
                  {r.preparation_notes && <p className="mt-1 whitespace-pre-line text-xs text-slate-600">Preparation: {r.preparation_notes}</p>}
                  {r.feedback && <p className="mt-1 whitespace-pre-line text-xs text-slate-600">Feedback: {r.feedback}</p>}
                  {r.interview_session_id && (
                    <Link to={`/interview-prep/sessions/${r.interview_session_id}`} className="text-xs text-brand-700 hover:underline">
                      Linked practice session
                    </Link>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <Badge tone={outcome(r.outcome).tone}>{outcome(r.outcome).label}</Badge>
                  <Button variant="secondary" onClick={() => setMode(r.interview_id)} className="py-1.5" aria-label={`Edit round ${r.round_number}`}>
                    Edit
                  </Button>
                  <Button variant="ghost" onClick={() => remove(r)} className="py-1.5" aria-label={`Delete round ${r.round_number}`}>
                    Delete
                  </Button>
                </div>
              </li>
            ),
          )}
        </ol>
      )}
    </section>
  );
}
