import { useEffect, useRef, useState } from "react";
import { TRANSITIONS, updateStatus } from "../../../api/applications";
import { normalizeError } from "../../../api/errors";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import { useConfirm } from "../../../context/ConfirmContext";
import { applicationStatus, CONSEQUENTIAL, correctionTarget } from "../applicationFormat";

// Status changes through PATCH /applications/{id}/status. Only the backend's allowed transitions are
// offered; expected_status makes the backend refuse (409) if the status changed elsewhere meanwhile.
// Nothing is changed on screen until the backend confirms.
export default function StatusControl({ application, history, onChanged, onConflict }) {
  const confirm = useConfirm();
  const current = application.status;
  const options = TRANSITIONS[current] || [];
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const lock = useRef(false);
  const undoTo = correctionTarget(history, current);

  // A new status (from this form, a correction or an interview round) clears the pending choice.
  useEffect(() => {
    setTarget("");
  }, [current]);

  const send = async (status, correction) => {
    if (lock.current) return;
    const label = applicationStatus(status).label;
    if (correction || CONSEQUENTIAL.includes(status)) {
      const ok = await confirm({
        title: correction ? `Undo the last change?` : `Mark this application as ${label}?`,
        message: correction
          ? `The status goes back from ${applicationStatus(current).label} to ${label}, and the correction is recorded in the history.`
          : status === "WITHDRAWN"
            ? "Withdrawing closes the application. It can only be undone with a correction."
            : `This records a decision on the application. ${status === "REJECTED" ? "No further status changes are possible afterwards except a correction." : ""}`.trim(),
        confirmLabel: correction ? "Undo change" : `Mark as ${label}`,
        tone: status === "WITHDRAWN" || status === "REJECTED" ? "danger" : "primary",
      });
      if (!ok) return;
    }
    lock.current = true;
    setBusy(true);
    setError(null);
    setWarnings([]);
    try {
      const result = await updateStatus(application.application_id, { status, correction, expectedStatus: current });
      setTarget("");
      setWarnings(result.warnings || []);
      onChanged(result);
    } catch (failure) {
      const err = normalizeError(failure);
      setError(err.message);
      if (err.status === 409) onConflict?.();
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    if (!target) {
      setError("Choose the new status.");
      return;
    }
    send(target, false);
  };

  const st = applicationStatus(current);
  return (
    <section aria-labelledby="status-title" className="flex flex-col gap-3">
      <h2 id="status-title" className="text-base font-semibold text-slate-900">
        Status
      </h2>
      <p className="flex items-center gap-2 text-sm text-slate-600">
        Current: <Badge tone={st.tone}>{st.label}</Badge>
      </p>
      {options.length ? (
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-end" aria-label="Change status">
          <div className="flex flex-1 flex-col gap-1">
            <label htmlFor="new-status" className="text-sm font-medium text-slate-700">
              New status
            </label>
            <select
              id="new-status"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-normal shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="">Choose…</option>
              {options.map((s) => (
                <option key={s} value={s}>
                  {applicationStatus(s).label}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" loading={busy}>
            Update status
          </Button>
        </form>
      ) : (
        <p className="text-sm text-slate-500">{st.label} is final; the status can only be changed by undoing the last change.</p>
      )}
      {undoTo && (
        <div>
          <Button variant="ghost" onClick={() => send(undoTo, true)} disabled={busy} className="px-2 py-1 text-xs">
            Undo last change (back to {applicationStatus(undoTo).label})
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
      {warnings.length > 0 && (
        <ul className="flex flex-col gap-1" aria-label="Status warnings">
          {warnings.map((w, i) => (
            <li key={i} className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
              {w}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
