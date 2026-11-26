import Spinner from "./Spinner";

// CareerNova buttons. Variants keep their original names so every page restyles from here.
const VARIANTS = {
  primary:
    "bg-brand-600 text-white shadow-sm shadow-brand-600/25 hover:bg-brand-700 hover:shadow-glow focus-visible:outline-brand-600",
  secondary:
    "border border-slate-300 bg-white text-slate-800 shadow-sm hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-brand-600",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700 focus-visible:outline-red-600",
  ghost: "text-slate-700 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-brand-600",
  // Light button for dark (navy) surfaces.
  inverse: "bg-white text-navy-900 shadow-sm hover:bg-brand-50 focus-visible:outline-white",
};

export default function Button({ variant = "primary", loading = false, disabled = false, className = "", children, type = "button", ...props }) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex min-h-[2.5rem] items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition duration-150 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none disabled:active:scale-100 motion-reduce:active:scale-100 ${VARIANTS[variant] || VARIANTS.primary} ${className}`}
      {...props}
    >
      {loading && <Spinner size="sm" label="" />}
      {children}
    </button>
  );
}
