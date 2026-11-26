import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { adminListInternships, deactivateInternship, updateInternship, verifyInternship } from "../../api/admin";
import { errorMessage } from "../../api/errors";
import { getInternshipFilters, KEYWORD_MAX } from "../../api/internships";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import Pagination from "../../components/ui/Pagination";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDate } from "../../utils/dates";
import { CardEmpty, CardSkeleton } from "../dashboard/components/DashboardCard";
import { AdminError, AdminHeader, adminPanel } from "./adminShared";

const PAGE = 20;

// Internship catalogue for administrators: GET /internships/?include_inactive=true with the backend's
// q / domain filters and paging. Deactivate = DELETE (soft delete); reactivate = PATCH is_active.
export default function AdminInternshipsPage() {
  const confirm = useConfirm();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const domain = params.get("domain") || "";
  const inactive = params.get("inactive") !== "0";
  const skip = Math.max(0, Number(params.get("skip")) || 0);
  const list = useApiResource(() => adminListInternships({ q, domain, includeInactive: inactive, skip, limit: PAGE }), `admin-internships:${q}:${domain}:${inactive}:${skip}`);
  const filters = useApiResource(getInternshipFilters, "internship-filters");
  const [query, setQuery] = useState(q);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const lock = useRef(false);

  useEffect(() => {
    const previous = document.title;
    document.title = "Manage internships · Admin · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const update = (change) => {
    const merged = { q, domain, inactive, skip: 0, ...change };
    const next = new URLSearchParams();
    if (merged.q) next.set("q", merged.q);
    if (merged.domain) next.set("domain", merged.domain);
    if (!merged.inactive) next.set("inactive", "0");
    if (merged.skip) next.set("skip", String(merged.skip));
    setParams(next);
  };

  const run = async (i, task, message) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(i.internship_id);
    setError(null);
    try {
      await task();
      toast.success(message);
      list.reload();
    } catch (failure) {
      setError({ id: i.internship_id, message: errorMessage(failure) });
    } finally {
      lock.current = false;
      setBusy(null);
    }
  };

  const deactivate = async (i) => {
    const ok = await confirm({
      title: `Deactivate ${i.title}?`,
      message:
        "Students will no longer see it in browsing, search or new matches, and it is marked for removal from the search index. " +
        "Nothing is deleted: you can reactivate it later. Existing applications keep their records.",
      confirmLabel: "Deactivate",
      tone: "danger",
    });
    if (ok) await run(i, () => deactivateInternship(i.internship_id), `${i.title} was deactivated.`);
  };
  const reactivate = async (i) => {
    const ok = await confirm({
      title: `Reactivate ${i.title}?`,
      message: "Students will see it again. Rebuild the search index for it to appear in semantic search and matching.",
      confirmLabel: "Reactivate",
      tone: "primary",
    });
    if (ok) await run(i, () => updateInternship(i.internship_id, { is_active: true }), `${i.title} was reactivated.`);
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <AdminHeader title="Manage internships" description="Add, edit, deactivate or reactivate internships in the catalogue students browse.">
        <Link
          to="/admin/internships/new"
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
        >
          <Icon name="edit" className="h-4 w-4" />
          Add internship
        </Link>
      </AdminHeader>

      <section className={adminPanel} aria-label="Internship catalogue">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end">
          <form
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              update({ q: query.trim() });
            }}
            className="flex flex-1 flex-col gap-2 sm:flex-row"
          >
            <input
              type="search"
              aria-label="Search by title, company or description"
              placeholder="Search title, company or description"
              value={query}
              maxLength={KEYWORD_MAX}
              onChange={(e) => setQuery(e.target.value)}
              className="min-w-0 flex-1 cn-input"
            />
            <Button type="submit" variant="secondary">
              Search
            </Button>
          </form>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="admin-domain" className="text-xs font-medium text-slate-600">
                Domain
              </label>
              <select
                id="admin-domain"
                value={domain}
                onChange={(e) => update({ domain: e.target.value })}
                className="cn-input"
              >
                <option value="">All domains</option>
                {(filters.data?.domains || []).map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
              <input type="checkbox" checked={inactive} onChange={(e) => update({ inactive: e.target.checked })} className="h-4 w-4 rounded border-slate-300 text-brand-600" />
              Include deactivated
            </label>
          </div>
        </div>

        {(list.status === "loading" || list.status === "idle") && !list.data ? (
          <CardSkeleton label="internships" lines={5} />
        ) : list.status === "error" ? (
          <AdminError error={list.error} onRetry={list.reload} label="the internship list" />
        ) : !list.data.items.length ? (
          <CardEmpty title="No internships found" message={q || domain ? "Try other filters." : "Add the first internship."} />
        ) : (
          <>
            <p className="mb-2 text-xs text-slate-500" aria-live="polite">
              {list.data.total} internship{list.data.total === 1 ? "" : "s"}
            </p>
            <ul className="flex flex-col gap-2" aria-label="Internships">
              {list.data.items.map((i) => (
                <li key={i.internship_id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{i.title}</p>
                    <p className="text-sm text-slate-600">{i.company}</p>
                    <p className="text-xs text-slate-500">
                      #{i.internship_id} · {[i.domain, i.location, i.work_mode].filter(Boolean).join(" · ") || "No domain or location"}
                      {i.deadline ? ` · deadline ${formatDate(i.deadline)}` : ""} · source {i.source}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {i.is_active ? <Badge tone="success">Active</Badge> : <Badge>Deactivated</Badge>}
                      {i.source_label && <Badge>{i.source_label}</Badge>}
                      {i.freshness === "verified" ? (
                        <Badge tone="success">Verified {i.last_verified_at ? formatDate(i.last_verified_at) : ""}</Badge>
                      ) : i.freshness === "stale" ? (
                        <Badge tone="warning">Verification over 30 days old</Badge>
                      ) : null}
                      {i.required_skills?.length > 0 && <Badge>{i.required_skills.length} required skills</Badge>}
                    </div>
                    {error?.id === i.internship_id && (
                      <p role="alert" className="mt-1 text-sm text-red-700">
                        {error.message}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <Link
                      to={`/admin/internships/${i.internship_id}/edit`}
                      aria-label={`Edit ${i.title} at ${i.company}`}
                      className="inline-flex items-center rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                    >
                      Edit
                    </Link>
                    {i.is_active && (
                      <Button
                        variant="secondary"
                        onClick={() => run(i, () => verifyInternship(i.internship_id), `${i.title} marked as verified today.`)}
                        disabled={Boolean(busy)}
                        className="py-1.5"
                        aria-label={`Mark ${i.title} at ${i.company} as verified`}
                      >
                        Mark verified
                      </Button>
                    )}
                    {i.is_active ? (
                      <Button variant="ghost" onClick={() => deactivate(i)} loading={busy === i.internship_id} disabled={Boolean(busy)} className="py-1.5 text-red-700" aria-label={`Deactivate ${i.title} at ${i.company}`}>
                        Deactivate
                      </Button>
                    ) : (
                      <Button variant="secondary" onClick={() => reactivate(i)} loading={busy === i.internship_id} disabled={Boolean(busy)} className="py-1.5" aria-label={`Reactivate ${i.title} at ${i.company}`}>
                        Reactivate
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            <Pagination total={list.data.total} skip={list.data.skip} limit={list.data.limit} onChange={(next) => update({ skip: next })} />
          </>
        )}
      </section>
    </div>
  );
}
