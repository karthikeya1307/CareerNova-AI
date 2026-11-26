import Icon from "./Icon";

// `titleAs="h1"` when the empty state is the whole page (not found, no access), so the page has a heading.
export default function EmptyState({ title, message, action, icon = "sparkles", titleAs: Title = "p" }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      <span aria-hidden="true" className="mb-1 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 ring-8 ring-brand-50/50">
        <Icon name={icon} className="h-6 w-6" />
      </span>
      <Title className="font-display text-base font-semibold text-slate-900">{title}</Title>
      {message && <p className="max-w-md text-sm text-slate-600">{message}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
