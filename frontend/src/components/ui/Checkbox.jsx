import { useId } from "react";

export default function Checkbox({ label, hint, id, className = "", ...props }) {
  const autoId = useId();
  const inputId = id || autoId;
  return (
    <div className={`flex items-start gap-2 ${className}`}>
      <input
        id={inputId}
        type="checkbox"
        aria-describedby={hint ? `${inputId}-hint` : undefined}
        className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-brand-600 focus:ring-2 focus:ring-brand-500"
        {...props}
      />
      <div className="text-sm">
        <label htmlFor={inputId} className="font-medium text-slate-700">
          {label}
        </label>
        {hint && (
          <p id={`${inputId}-hint`} className="text-xs text-slate-500">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}
