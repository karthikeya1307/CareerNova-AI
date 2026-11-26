import { useEffect } from "react";

// Page heading for auth screens; also sets the browser tab title.
export default function AuthHeader({ title, description }) {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [title]);

  return (
    <header className="mb-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
      {description && <p className="mt-1.5 text-sm text-slate-600">{description}</p>}
    </header>
  );
}

// Consistent inline link style for auth screens.
export const linkClass =
  "font-medium text-brand-700 underline-offset-2 hover:text-brand-800 hover:underline focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600";
