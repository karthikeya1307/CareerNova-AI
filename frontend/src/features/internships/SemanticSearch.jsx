import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SEARCH_QUERY, searchInternships } from "../../api/internships";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import Select from "../../components/ui/Select";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import InternshipCard from "./components/InternshipCard";
import { EXAMPLE_QUERIES } from "./internshipFormat";

const K_OPTIONS = [5, 10, 20, 50];

// Similarity is the cosine score from the embedding index; shown as a percentage, never as a match score.
export function similarityPercent(value) {
  return Math.max(0, Math.min(100, Math.round(Number(value) * 100)));
}

// What the backend understood from the query (skills, role, location, work mode, level), shown as plain text.
function Understood({ interpretation }) {
  const i = interpretation;
  if (!i) return null;
  const parts = [
    i.skills?.length ? `skills: ${i.skills.join(", ")}` : null,
    i.roles?.length ? `role: ${i.roles.join(", ")}` : null,
    i.location ? `location: ${i.location}` : null,
    i.work_mode ? `work mode: ${i.work_mode}` : null,
    i.experience_level ? `level: ${i.experience_level}` : null,
  ].filter(Boolean);
  if (!parts.length) return null;
  return (
    <p className="mb-2 text-xs text-slate-600" aria-label="How your search was understood">
      <span className="font-medium text-slate-700">We understood: </span>
      {parts.join(" · ")}
    </p>
  );
}

// Natural-language search: GET /internships/search. The backend interprets the query, applies the location and
// work mode asked for, keeps only relevant postings and explains each result; nothing here is invented.
export default function SemanticSearch() {
  const [params, setParams] = useSearchParams();
  const query = (params.get("query") || "").trim();
  const k = K_OPTIONS.includes(Number(params.get("k"))) ? Number(params.get("k")) : 10;
  const [text, setText] = useState(query);
  const [error, setError] = useState(null);
  useEffect(() => setText(query), [query]);

  const valid = query.length >= SEARCH_QUERY.min && query.length <= SEARCH_QUERY.max;
  const results = useApiResource(() => searchInternships(query, k), valid ? `${query}|${k}` : null, { enabled: valid });

  const run = (value, nextK = k) => {
    const q = value.trim();
    if (q.length < SEARCH_QUERY.min) {
      setError(`Enter at least ${SEARCH_QUERY.min} characters.`);
      return;
    }
    setError(null);
    const next = new URLSearchParams(params);
    next.set("query", q);
    next.set("k", String(nextK));
    setParams(next);
  };

  const unavailable = results.status === "error" && results.error.status === 503;

  return (
    <div className="flex flex-col gap-6">
      <section aria-label="AI search" className="rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-brand-50/60 p-5 shadow-sm">
        <form
          role="search"
          aria-label="Semantic internship search"
          noValidate
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            run(text);
          }}
        >
          <label htmlFor="semantic-query" className="text-sm font-medium text-slate-800">
            Describe the internship you want
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="semantic-query"
              type="search"
              value={text}
              maxLength={SEARCH_QUERY.max}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Python internships for freshers"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "semantic-query-error" : "semantic-query-hint"}
              className={`min-w-0 flex-1 rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${error ? "border-red-400" : "border-slate-300"}`}
            />
            <Select aria-label="Number of results" value={String(k)} onChange={(e) => (query ? run(query, Number(e.target.value)) : setParams((p) => { const n = new URLSearchParams(p); n.set("k", e.target.value); return n; }))} options={K_OPTIONS.map((n) => ({ value: String(n), label: `Top ${n}` }))} />
            <Button type="submit" loading={results.status === "loading"}>
              <Icon name="sparkles" className="h-4 w-4" />
              AI search
            </Button>
          </div>
          {error ? (
            <p id="semantic-query-error" className="text-xs text-red-600">
              {error}
            </p>
          ) : (
            <p id="semantic-query-hint" className="text-xs text-slate-500">
              Understands skills, roles, location and remote/hybrid/onsite (e.g. “Java internships in Hyderabad”), and searches by meaning too.
            </p>
          )}
        </form>
        <div className="mt-4">
          <p className="text-xs font-medium text-slate-500">Try:</p>
          <ul className="mt-1.5 flex flex-wrap gap-2" aria-label="Example searches">
            {EXAMPLE_QUERIES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  onClick={() => run(example)}
                  className="rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-label="AI search results" aria-busy={results.status === "loading" || undefined}>
        {!valid ? (
          <CardEmpty title="Search by meaning" message="Type what you're looking for or pick an example above." />
        ) : results.status === "loading" || results.status === "idle" ? (
          <CardSkeleton label="search results" lines={5} />
        ) : unavailable ? (
          <CardEmpty
            title="AI search is unavailable right now"
            message="The search index isn't ready. Try again later, or use Browse with keyword and skill filters meanwhile."
            action={<Button variant="secondary" onClick={results.reload}>Try again</Button>}
          />
        ) : results.status === "error" ? (
          <CardError error={results.error} onRetry={results.reload} label="search results" />
        ) : results.data.results.length === 0 ? (
          <>
            <Understood interpretation={results.data.interpretation} />
            <CardEmpty title="No internships found" message={results.data.message || "Try describing the role, skills or domain differently."} />
          </>
        ) : (
          <>
            <Understood interpretation={results.data.interpretation} />
            {results.data.message && (
              <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">
                {results.data.message}
              </p>
            )}
            <p className="mb-3 text-sm text-slate-600" aria-live="polite">
              {results.data.results.length} result{results.data.results.length === 1 ? "" : "s"} for “{results.data.query}”, ranked by relevance
              {results.data.mode === "keyword" ? " (skills, role and keywords)" : " (skills, role, location and meaning)"}
              {results.data.index_built_at ? ` · index updated ${formatDateTime(results.data.index_built_at)}` : ""}
            </p>
            <ol className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Search results">
              {results.data.results.map((hit) => (
                <li key={hit.internship.internship_id} className="flex min-w-0 flex-col gap-1.5">
                  <InternshipCard
                    internship={hit.internship}
                    badge={
                      <Badge tone="info">
                        <span className="tabular-nums">{similarityPercent(hit.score ?? hit.similarity)}%</span>
                        <span className="sr-only"> relevance</span>
                      </Badge>
                    }
                  />
                  {hit.reasons?.length > 0 && (
                    <p className="px-1 text-xs text-slate-600">
                      <span className="font-medium text-slate-700">Why: </span>
                      {hit.reasons.join(" · ")}
                    </p>
                  )}
                </li>
              ))}
            </ol>
            <p className="mt-3 text-xs text-slate-500">
              Relevance combines exact matches (skills, role, location, work mode) with how closely the posting's text matches your query. For how well a posting fits your resume, use Check my match on its page.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
