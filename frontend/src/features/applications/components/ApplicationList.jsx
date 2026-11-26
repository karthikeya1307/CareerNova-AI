import { useState } from "react";
import { Link } from "react-router-dom";
import { LIMITS, listApplications, SORT_FIELDS, STATUSES } from "../../../api/applications";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import Pagination from "../../../components/ui/Pagination";
import useApiResource from "../../../hooks/useApiResource";
import { formatDate, formatDateTime } from "../../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import { applicationStatus, SORT_LABEL } from "../applicationFormat";

const PAGE = 20;

// Applications from GET /applications. Filtering, search, sorting and paging are done by the backend.
export default function ApplicationList({ filters, onFilters }) {
  const { statuses, q, sort, order, skip } = filters;
  const key = JSON.stringify(filters);
  const list = useApiResource(() => listApplications({ statuses, q, sort, order, skip, limit: PAGE }), key);
  const [query, setQuery] = useState(q || "");

  const toggleStatus = (status) => {
    const next = statuses.includes(status) ? statuses.filter((s) => s !== status) : [...statuses, status];
    onFilters({ statuses: next, skip: 0 });
  };
  const search = (event) => {
    event.preventDefault();
    onFilters({ q: query.trim(), skip: 0 });
  };

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={search} role="search" className="flex flex-col gap-2 sm:flex-row">
        <input
          type="search"
          aria-label="Search applications by company, role or notes"
          placeholder="Search company, role or notes"
          value={query}
          maxLength={LIMITS.query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-0 flex-1 cn-input"
        />
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-1.5">
          {STATUSES.map((status) => {
            const on = statuses.includes(status);
            return (
              <button
                key={status}
                type="button"
                aria-pressed={on}
                onClick={() => toggleStatus(status)}
                className={`rounded-full border px-3 py-1 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 ${
                  on ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {applicationStatus(status).label}
              </button>
            );
          })}
          {(statuses.length > 0 || q) && (
            <button type="button" onClick={() => { setQuery(""); onFilters({ statuses: [], q: "", skip: 0 }); }} className="px-2 text-xs font-medium text-brand-700 hover:underline">
              Clear filters
            </button>
          )}
        </div>
        <div className="flex gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <label htmlFor="app-sort">Sort by</label>
            <select
              id="app-sort"
              value={sort}
              onChange={(e) => onFilters({ sort: e.target.value, skip: 0 })}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {SORT_FIELDS.map((f) => (
                <option key={f} value={f}>
                  {SORT_LABEL[f]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <label htmlFor="app-order">Order</label>
            <select
              id="app-order"
              value={order}
              onChange={(e) => onFilters({ order: e.target.value, skip: 0 })}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </div>
        </div>
      </div>

      {(list.status === "loading" || list.status === "idle") && !list.data ? (
        <CardSkeleton label="your applications" lines={4} />
      ) : list.status === "error" ? (
        <CardError error={list.error} onRetry={list.reload} label="your applications" />
      ) : !list.data.items.length ? (
        statuses.length || q ? (
          <CardEmpty title="No matching applications" message="Try other filters or clear the search." />
        ) : (
          <CardEmpty
            title="No applications yet"
            message="Track an internship from its page, from your saved internships, or add one you applied to elsewhere."
            action={<Link to="/internships" className="text-sm font-medium text-brand-700 hover:underline">Browse internships</Link>}
          />
        )
      ) : (
        <>
          <p className="text-xs text-slate-500" aria-live="polite">
            {list.data.total} application{list.data.total === 1 ? "" : "s"}
          </p>
          <ul className="flex flex-col gap-2" aria-label="Applications">
            {list.data.items.map((a) => {
              const st = applicationStatus(a.status);
              return (
                <li key={a.application_id}>
                  <Link
                    to={`/applications/${a.application_id}`}
                    className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <span className="min-w-0">
                      <span className="block font-medium text-slate-900">{a.title}</span>
                      <span className="block text-sm text-slate-600">{a.company_name}</span>
                      <span className="mt-0.5 block text-xs text-slate-500">
                        {a.applied_at ? `Applied ${formatDate(a.applied_at)}` : `Added ${formatDate(a.created_at)}`}
                        {a.location ? ` · ${a.location}` : ""}
                        {a.source === "external" ? " · Added manually" : ""}
                      </span>
                      {a.next_interview && (
                        <span className="mt-1 block text-xs text-amber-800">
                          Next interview: round {a.next_interview.round_number}, {formatDateTime(a.next_interview.scheduled_at)}
                        </span>
                      )}
                      {a.notes && <span className="mt-1 line-clamp-2 block text-xs text-slate-500">{a.notes}</span>}
                    </span>
                    <span className="flex shrink-0 flex-wrap gap-1.5">
                      <Badge tone={st.tone}>{st.label}</Badge>
                      {a.interview_count > 0 && <Badge>{a.interview_count} interview{a.interview_count === 1 ? "" : "s"}</Badge>}
                      {a.pending_reminders > 0 && <Badge tone="warning">{a.pending_reminders} reminder{a.pending_reminders === 1 ? "" : "s"}</Badge>}
                      {a.deadline_passed && <Badge>Deadline passed</Badge>}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          <Pagination total={list.data.total} skip={list.data.skip} limit={list.data.limit} onChange={(next) => onFilters({ skip: next })} />
        </>
      )}
    </div>
  );
}
