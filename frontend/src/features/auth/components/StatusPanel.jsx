import { useEffect, useRef } from "react";

const TONES = {
  success: { ring: "bg-mint-50 text-mint-600", path: "M5 12.5l4.5 4.5L19 7.5" },
  info: { ring: "bg-brand-50 text-brand-600", path: "M4 7l8 6 8-6M4 7v10h16V7" },
  warning: { ring: "bg-amber-50 text-amber-600", path: "M12 8v5m0 3.5v.5M10.3 4.3 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z" },
  error: { ring: "bg-red-50 text-red-600", path: "M7 7l10 10M17 7 7 17" },
};

// Result screen for an auth flow (account created, email verified, link expired, ...).
// The heading receives focus so screen-reader and keyboard users land on the new state.
export default function StatusPanel({ tone = "info", title, children, actions }) {
  const heading = useRef(null);
  useEffect(() => {
    heading.current?.focus();
    const previous = document.title;
    document.title = `${title} · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [title]);
  const style = TONES[tone];

  return (
    <section className="flex flex-col items-center text-center" aria-live="polite">
      <span className={`flex h-14 w-14 items-center justify-center rounded-full ${style.ring}`} aria-hidden="true">
        <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d={style.path} />
        </svg>
      </span>
      <h1 ref={heading} tabIndex={-1} className="mt-4 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl focus:outline-none">
        {title}
      </h1>
      <div className="mt-2 space-y-3 text-sm text-slate-600">{children}</div>
      {actions && <div className="mt-6 flex w-full flex-col gap-3">{actions}</div>}
    </section>
  );
}
