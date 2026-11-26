import { useId } from "react";

export default function Select({ label, error, options = [], id, className = "", ...props }) {
  const autoId = useId();
  const selectId = id || autoId;
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {label && (
        <label htmlFor={selectId} className="text-sm font-medium text-slate-700">
          {label}
        </label>
      )}
      <select
        id={selectId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${selectId}-error` : undefined}
        className={`cn-input ${error ? "border-red-400 hover:border-red-400 focus:border-red-500 focus:ring-red-100" : ""}`}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={`${selectId}-error`} className="text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
