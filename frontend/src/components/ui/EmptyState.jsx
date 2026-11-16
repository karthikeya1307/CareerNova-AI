export default function EmptyState({ title, message, action }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <p className="text-base font-medium text-slate-800">{title}</p>
      {message && <p className="max-w-md text-sm text-slate-600">{message}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
