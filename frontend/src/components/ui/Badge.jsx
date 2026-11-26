const TONES = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
  info: "bg-brand-50 text-brand-700 ring-brand-100",
  success: "bg-mint-50 text-mint-700 ring-mint-100",
  warning: "bg-amber-50 text-amber-800 ring-amber-100",
  danger: "bg-red-50 text-red-700 ring-red-100",
  ai: "bg-violet-50 text-violet-700 ring-violet-100",
};

export default function Badge({ tone = "neutral", children }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone] || TONES.neutral}`}>
      {children}
    </span>
  );
}
