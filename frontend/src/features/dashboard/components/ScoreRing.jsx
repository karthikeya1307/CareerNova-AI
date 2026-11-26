// Circular 0-100 gauge. The number is real text (announced by screen readers via `label`).
const TONES = {
  high: "stroke-mint-500",
  medium: "stroke-brand-500",
  low: "stroke-amber-500",
};

export function scoreTone(value) {
  if (value >= 70) return "high";
  if (value >= 45) return "medium";
  return "low";
}

export default function ScoreRing({ value, label, size = 96 }) {
  const clamped = Math.max(0, Math.min(100, Number(value) || 0));
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden="true" focusable="false">
        <circle cx="50" cy="50" r={radius} fill="none" strokeWidth="9" className="stroke-slate-100" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth="9"
          strokeLinecap="round"
          className={TONES[scoreTone(clamped)]}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
      </svg>
      <span className="absolute text-xl font-semibold tabular-nums text-slate-900">
        {Math.round(clamped)}
        <span className="text-sm font-medium text-slate-500">%</span>
        <span className="sr-only"> {label}</span>
      </span>
    </div>
  );
}
