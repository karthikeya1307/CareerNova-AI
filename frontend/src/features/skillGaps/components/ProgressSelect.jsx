import { useState } from "react";
import { errorMessage } from "../../../api/errors";
import { PROGRESS_LABELS, setSkillProgress } from "../../../api/skillGaps";

const TONE = {
  not_started: "border-slate-300 text-slate-700",
  learning: "border-sky-300 bg-sky-50 text-sky-800",
  practiced: "border-amber-300 bg-amber-50 text-amber-800",
  completed: "border-mint-300 bg-mint-50 text-mint-800",
};

// Saves a skill's progress (Not Started / Learning / Practiced / Completed) for the student.
export default function ProgressSelect({ skill, status = "not_started", onChange }) {
  const [value, setValue] = useState(status);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const change = async (event) => {
    const next = event.target.value;
    const previous = value;
    setValue(next);
    setSaving(true);
    setError(null);
    try {
      const saved = await setSkillProgress(skill, next);
      setValue(saved.status);
      onChange?.(saved);
    } catch (failure) {
      setValue(previous);
      setError(errorMessage(failure));
    } finally {
      setSaving(false);
    }
  };

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <select
        aria-label={`Progress for ${skill}`}
        value={value}
        onChange={change}
        disabled={saving}
        className={`rounded-md border px-2 py-1 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-60 ${TONE[value]}`}
      >
        {Object.entries(PROGRESS_LABELS).map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
      {error && (
        <span role="alert" className="text-xs text-red-700">
          {error}
        </span>
      )}
    </span>
  );
}
