import { useId, useState } from "react";

function EyeIcon({ open }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7Z" />
      <circle cx="12" cy="12" r="3" />
      {!open && <path strokeLinecap="round" d="M4 4l16 16" />}
    </svg>
  );
}

// Password field with an accessible show/hide toggle. Same label/error/hint contract as <Input>.
export default function PasswordInput({ label, error, hint, id, className = "", describedBy, ...props }) {
  const autoId = useId();
  const inputId = id || autoId;
  const [visible, setVisible] = useState(false);
  const ids = [error ? `${inputId}-error` : hint ? `${inputId}-hint` : null, describedBy].filter(Boolean).join(" ") || undefined;

  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <label htmlFor={inputId} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          type={visible ? "text" : "password"}
          aria-invalid={error ? true : undefined}
          aria-describedby={ids}
          autoCapitalize="none"
          spellCheck={false}
          className={`w-full rounded-md border py-2 pl-3 pr-11 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${
            error ? "border-red-400" : "border-slate-300"
          }`}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          aria-pressed={visible}
          aria-controls={inputId}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-slate-500 hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
        >
          <EyeIcon open={visible} />
        </button>
      </div>
      {error ? (
        <p id={`${inputId}-error`} className="text-xs text-red-600">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${inputId}-hint`} className="text-xs text-slate-500">
            {hint}
          </p>
        )
      )}
    </div>
  );
}
