const SIZES = { sm: "h-4 w-4 border-2", md: "h-6 w-6 border-2", lg: "h-10 w-10 border-[3px]" };

export default function Spinner({ size = "md", label = "Loading" }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-slate-600">
      <span aria-hidden="true" className={`inline-block animate-spin rounded-full border-current border-r-transparent opacity-80 ${SIZES[size]} ${label === "" ? "" : "text-brand-600"}`} />
      {label ? <span>{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  );
}
