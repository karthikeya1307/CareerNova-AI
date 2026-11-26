import { useEffect, useId, useRef } from "react";

// Accessible modal: role="dialog", labelled by its title, Escape closes, focus moves inside.
export default function Modal({ title, children, footer, onClose }) {
  const titleId = useId();
  const panel = useRef(null);

  useEffect(() => {
    const previous = document.activeElement;
    panel.current?.querySelector("input, button, select, textarea, [tabindex]")?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previous && typeof previous.focus === "function") previous.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-navy-950/50 p-4 backdrop-blur-sm motion-safe:animate-fade-in">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white shadow-elevated motion-safe:animate-scale-in"
      >
        <h2 id={titleId} className="border-b border-slate-100 px-6 py-4 text-base font-semibold text-slate-900">
          {title}
        </h2>
        <div className="px-6 py-5 text-sm text-slate-700">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 rounded-b-2xl border-t border-slate-100 bg-slate-50/60 px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}
