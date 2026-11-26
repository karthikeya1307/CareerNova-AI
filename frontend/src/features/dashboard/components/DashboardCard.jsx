import { useId } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../../../api/errors";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";

// Card shell shared by every dashboard section: icon, title, optional "view all" link and body.
export default function DashboardCard({ title, icon, link, linkLabel = "View all", className = "", children }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={`cn-card flex min-w-0 flex-col p-5 transition-shadow duration-200 hover:shadow-card-hover sm:p-6 ${className}`}>
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {icon && (
            <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-50 to-violet-50 text-brand-600 ring-1 ring-inset ring-brand-100">
              <Icon name={icon} className="h-5 w-5" />
            </span>
          )}
          <h2 id={headingId} className="text-base font-semibold text-slate-900">
            {title}
          </h2>
        </div>
        {link && (
          <Link
            to={link}
            className="inline-flex items-center gap-1 rounded text-sm font-medium text-brand-700 hover:text-brand-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
          >
            {linkLabel}
            <span className="sr-only"> — {title}</span>
            <Icon name="arrowRight" className="h-4 w-4" />
          </Link>
        )}
      </header>
      <div className="flex flex-1 flex-col">{children}</div>
    </section>
  );
}

// Placeholder blocks while a section loads.
export function CardSkeleton({ label, lines = 3 }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3">
      <span className="sr-only">Loading {label}…</span>
      <div aria-hidden="true" className="cn-skeleton h-8 w-1/3" />
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} aria-hidden="true" className="cn-skeleton h-3.5" style={{ width: `${90 - i * 15}%` }} />
      ))}
    </div>
  );
}

// Error with a retry button. The message comes from the normalised ApiError (never raw details).
export function CardError({ error, onRetry, label }) {
  return (
    <div role="alert" className="flex flex-1 flex-col items-start gap-3 rounded-xl border border-red-100 bg-red-50/60 p-4 text-sm text-red-800">
      <p className="flex items-start gap-2">
        <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          <span className="font-medium">Couldn't load {label}.</span> {errorMessage(error)}
        </span>
      </p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry} className="py-1.5">
          <Icon name="refresh" className="h-4 w-4" />
          Try again
        </Button>
      )}
    </div>
  );
}

// Empty or not-yet-available state with an optional call to action.
export function CardEmpty({ title, message, action }) {
  return (
    <div className="flex flex-1 flex-col items-start justify-center gap-2 rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-4">
      <p className="text-sm font-medium text-slate-800">{title}</p>
      {message && <p className="text-sm text-slate-600">{message}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

// Renders the right state for a useApiResource result; `children(data)` renders success.
export function ResourceState({ resource, label, lines, children }) {
  if (resource.status === "loading" || resource.status === "idle") return <CardSkeleton label={label} lines={lines} />;
  if (resource.status === "error") return <CardError error={resource.error} onRetry={resource.reload} label={label} />;
  return children(resource.data);
}
