import { useState } from "react";
import { errorMessage } from "../../../api/errors";
import { KEYWORD_MAX, listInternships } from "../../../api/internships";
import Button from "../../../components/ui/Button";
import Icon from "../../../components/ui/Icon";

// Choose the target internship by searching active internships (GET /internships/?q=).
export default function InternshipPicker({ value, onChange, error: fieldError, legend = "Target internship" }) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState({ status: "idle" });

  const search = async (event) => {
    event?.preventDefault();
    if (state.status === "loading") return;
    setState({ status: "loading" });
    try {
      const data = await listInternships({ q: query.trim(), limit: 8 });
      setState({ status: "success", items: data.items, total: data.total });
    } catch (failure) {
      setState({ status: "error", message: errorMessage(failure) });
    }
  };

  if (value) {
    const required = value.required_skills || [];
    return (
      <div className="flex flex-col gap-3 rounded-xl border border-brand-200 bg-brand-50/60 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-medium text-brand-700">{legend}</p>
            <p className="truncate font-medium text-slate-900">{value.title}</p>
            <p className="truncate text-sm text-slate-600">{value.company}</p>
          </div>
          <Button variant="secondary" onClick={() => onChange(null)} className="py-1.5">
            Change
          </Button>
        </div>
        {/* The posting details the backend uses for this internship (from the internship record). */}
        {(value.description || required.length > 0 || value.min_education) && (
          <dl className="flex flex-col gap-1.5 border-t border-brand-100 pt-2 text-xs text-slate-700" aria-label="Internship details used">
            {value.description && (
              <div>
                <dt className="font-medium text-slate-500">Responsibilities</dt>
                <dd className="line-clamp-3">{value.description}</dd>
              </div>
            )}
            {required.length > 0 && (
              <div>
                <dt className="font-medium text-slate-500">Required skills</dt>
                <dd>{required.join(", ")}</dd>
              </div>
            )}
            {value.min_education && (
              <div>
                <dt className="font-medium text-slate-500">Education</dt>
                <dd>{value.min_education}</dd>
              </div>
            )}
          </dl>
        )}
      </div>
    );
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium text-slate-700">{legend}</legend>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="search"
          aria-label="Search internships by title, company or description"
          aria-invalid={fieldError ? true : undefined}
          aria-describedby={fieldError ? "internship-picker-error" : undefined}
          value={query}
          maxLength={KEYWORD_MAX}
          placeholder="Search by title, company or keyword"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search(e)}
          className={`min-w-0 flex-1 rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${fieldError ? "border-red-400" : "border-slate-300"}`}
        />
        <Button variant="secondary" onClick={search} loading={state.status === "loading"}>
          {state.status !== "loading" && <Icon name="briefcase" className="h-4 w-4" />}
          Find internships
        </Button>
      </div>
      {fieldError && (
        <p id="internship-picker-error" className="text-xs text-red-600">
          {fieldError}
        </p>
      )}
      {state.status === "error" && (
        <p role="alert" className="text-sm text-red-700">
          {state.message}
        </p>
      )}
      {state.status === "success" &&
        (state.items.length ? (
          <ul className="flex max-h-72 flex-col gap-1.5 overflow-y-auto" aria-label="Internship search results">
            {state.items.map((it) => (
              <li key={it.internship_id}>
                <button
                  type="button"
                  onClick={() => onChange(it)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                >
                  <span className="block text-sm font-medium text-slate-900">{it.title}</span>
                  <span className="block text-xs text-slate-500">{[it.company, it.location, it.work_mode].filter(Boolean).join(" · ")}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No active internships match “{query}”.</p>
        ))}
    </fieldset>
  );
}
