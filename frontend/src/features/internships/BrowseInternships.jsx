import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getInternshipFilters, KEYWORD_MAX, listAllInternships, listInternships, WORK_MODES } from "../../api/internships";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import Input from "../../components/ui/Input";
import Pagination from "../../components/ui/Pagination";
import Select from "../../components/ui/Select";
import useApiResource from "../../hooks/useApiResource";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import InternshipCard from "./components/InternshipCard";
import { SORTS, sortInternships } from "./internshipFormat";

export const PAGE_SIZE = 12;
const FILTER_KEYS = ["q", "skill", "domain", "location", "mode", "sort"];

// Browse with keyword / skill / domain / location / work-mode filters, sorting and pagination.
// All state lives in the URL (?q=&skill=&domain=&location=&mode=&sort=&page=) so it can be shared
// and survives Back/Forward.
export default function BrowseInternships() {
  const [params, setParams] = useSearchParams();
  const get = (key) => params.get(key) || "";
  const page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  const filters = { q: get("q"), skill: get("skill"), domain: get("domain"), location: get("location"), work_mode: get("mode") };
  const sort = SORTS.some((s) => s.id === get("sort")) ? get("sort") : "";
  const filterKey = JSON.stringify(filters);

  // Text inputs apply on submit, not on every keystroke.
  const [keyword, setKeyword] = useState(filters.q);
  const [skill, setSkill] = useState(filters.skill);
  useEffect(() => {
    setKeyword(filters.q);
    setSkill(filters.skill);
  }, [filters.q, filters.skill]);

  const options = useApiResource(getInternshipFilters, "filters");
  // Default order: one server page. Sorted: every matching internship, sorted in the browser.
  const results = useApiResource(
    () => (sort ? listAllInternships(filters) : listInternships({ ...filters, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE })),
    sort ? `all:${filterKey}` : `page:${filterKey}:${page}`,
  );

  const update = (changes, { keepPage = false } = {}) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
    if (!keepPage) next.delete("page");
    setParams(next);
  };

  const active = FILTER_KEYS.filter((key) => key !== "sort" && get(key)).length;
  const clearAll = () => {
    const next = new URLSearchParams(params);
    [...FILTER_KEYS, "page"].forEach((key) => next.delete(key));
    setParams(next);
  };

  let items = [];
  let total = 0;
  if (results.status === "success") {
    if (sort) {
      total = results.data.total;
      items = sortInternships(results.data.items, sort).slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    } else {
      total = results.data.total;
      items = results.data.items;
    }
  }
  const first = total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const last = Math.min(total, page * PAGE_SIZE);
  const optionList = (values, all) => [{ value: "", label: all }, ...(values || []).map((v) => ({ value: v, label: v }))];
  const modes = options.data?.work_modes?.length ? options.data.work_modes : WORK_MODES;

  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Search and filters" className="flex flex-col gap-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card">
        <form
          role="search"
          aria-label="Search internships"
          className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] md:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            update({ q: keyword.trim(), skill: skill.trim() });
          }}
        >
          <Input label="Keyword" type="search" placeholder="Title, company or description" maxLength={KEYWORD_MAX} value={keyword} onChange={(e) => setKeyword(e.target.value)} />
          <Input label="Skill" type="search" placeholder="e.g. Python" maxLength={60} value={skill} onChange={(e) => setSkill(e.target.value)} />
          <Button type="submit" className="md:mb-0">
            <Icon name="target" className="h-4 w-4" />
            Search
          </Button>
        </form>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <Select label="Domain" value={filters.domain} onChange={(e) => update({ domain: e.target.value })} options={optionList(options.data?.domains, "All domains")} />
          <Select label="Location" value={filters.location} onChange={(e) => update({ location: e.target.value })} options={optionList(options.data?.locations, "All locations")} />
          <Select label="Sort by" value={sort} onChange={(e) => update({ sort: e.target.value })} options={SORTS.map((s) => ({ value: s.id, label: s.label }))} />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div role="group" aria-label="Work mode" className="inline-flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
            {["", ...modes].map((mode) => {
              const pressed = filters.work_mode === mode;
              return (
                <button
                  key={mode || "all"}
                  type="button"
                  aria-pressed={pressed}
                  onClick={() => update({ mode })}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                    pressed ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {mode || "All modes"}
                </button>
              );
            })}
          </div>
          {active > 0 && (
            <Button variant="ghost" onClick={clearAll}>
              <Icon name="close" className="h-4 w-4" />
              Clear all filters ({active})
            </Button>
          )}
        </div>
        {options.status === "error" && (
          <p className="text-xs text-amber-800">
            Filter options couldn't load.{" "}
            <button type="button" onClick={options.reload} className="font-medium underline">
              Retry
            </button>
          </p>
        )}
      </section>

      <section aria-label="Internship results" aria-busy={results.status === "loading" || undefined}>
        {results.status === "loading" || results.status === "idle" ? (
          <CardSkeleton label="internships" lines={5} />
        ) : results.status === "error" ? (
          <CardError error={results.error} onRetry={results.reload} label="internships" />
        ) : total === 0 ? (
          <CardEmpty
            title="No internships match these filters"
            message="Try a different keyword or skill, or clear some filters."
            action={active ? <Button variant="secondary" onClick={clearAll}>Clear all filters</Button> : null}
          />
        ) : items.length === 0 ? (
          <CardEmpty title="This page is empty" message="Go back to the first page." action={<Button variant="secondary" onClick={() => update({}, {})}>First page</Button>} />
        ) : (
          <>
            <p className="mb-3 text-sm text-slate-600" aria-live="polite">
              Showing {first}–{last} of {total} internship{total === 1 ? "" : "s"}
              {sort ? ` · sorted by ${SORTS.find((s) => s.id === sort).label.toLowerCase()}` : ""}
            </p>
            <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Internships">
              {items.map((internship) => (
                <li key={internship.internship_id} className="flex min-w-0">
                  <InternshipCard internship={internship} />
                </li>
              ))}
            </ul>
            <Pagination total={total} skip={(page - 1) * PAGE_SIZE} limit={PAGE_SIZE} onChange={(skip) => update({ page: String(skip / PAGE_SIZE + 1) }, { keepPage: true })} />
          </>
        )}
      </section>
    </div>
  );
}
