import { CardError } from "../dashboard/components/DashboardCard";

export const adminPanel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

// Error state for admin requests. A 403 means the backend no longer accepts this account as an
// administrator (for example the role was changed elsewhere), so retrying will not help.
export function AdminError({ error, onRetry, label }) {
  if (error?.status === 403) {
    return (
      <div role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-800">
        <p className="font-medium">The server refused access to {label}.</p>
        <p className="mt-0.5">{error.message} Only administrators can use this page. If your role changed recently, sign out and sign in again.</p>
      </div>
    );
  }
  return <CardError error={error} onRetry={onRetry} label={label} />;
}

export function AdminHeader({ title, description, children }) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Administration</p>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
      </div>
      {children}
    </header>
  );
}

export const fullName = (u) => [u.first_name, u.last_name].filter(Boolean).join(" ") || "—";
