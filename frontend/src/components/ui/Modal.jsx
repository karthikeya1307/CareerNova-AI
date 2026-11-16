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
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4">
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} className="w-full max-w-md rounded-lg bg-white shadow-xl">
        <h2 id={titleId} className="border-b border-slate-100 px-5 py-3 text-base font-semibold">
          {title}
        </h2>
        <div className="px-5 py-4 text-sm text-slate-700">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}
