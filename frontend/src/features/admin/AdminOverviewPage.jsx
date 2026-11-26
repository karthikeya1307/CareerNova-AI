import { useEffect } from "react";
import { Link } from "react-router-dom";
import { adminListInternships, getIndexStatus, internshipTotals, listAllUsers } from "../../api/admin";
import { getInternshipFilters } from "../../api/internships";
import Badge from "../../components/ui/Badge";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardSkeleton } from "../dashboard/components/DashboardCard";
import { AdminError, AdminHeader, adminPanel } from "./adminShared";

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-2xl font-semibold tabular-nums text-slate-900">{value}</dd>
      {hint && <dd className="text-xs text-slate-500">{hint}</dd>}
    </div>
  );
}

function Section({ title, link, linkLabel, children }) {
  return (
    <section aria-labelledby={`${title}-title`} className={`${adminPanel} flex min-w-0 flex-col gap-4`}>
      <div className="flex items-center justify-between gap-2">
        <h2 id={`${title}-title`} className="text-base font-semibold text-slate-900">
          {title}
        </h2>
        {link && (
          <Link to={link} className="text-sm font-medium text-brand-700 hover:underline">
            {linkLabel}
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

// Active internships per domain: the domain list from /internships/filters and each domain's total.
async function domainCounts() {
  const { domains = [] } = await getInternshipFilters();
  const counts = await Promise.all(domains.map(async (d) => ({ domain: d, count: (await adminListInternships({ domain: d, includeInactive: false, limit: 1 })).total })));
  return counts.sort((a, b) => b.count - a.count || a.domain.localeCompare(b.domain));
}

// Admin overview built only from existing endpoints (the backend has no statistics endpoint):
// user counts from the complete user list, internship totals, per-domain totals and the index status.
export default function AdminOverviewPage() {
  const users = useApiResource(() => listAllUsers(), "admin-all-users");
  const totals = useApiResource(internshipTotals, "admin-internship-totals");
  const domains = useApiResource(domainCounts, "admin-domain-counts");
  const index = useApiResource(getIndexStatus, "admin-index-status");

  useEffect(() => {
    const previous = document.title;
    document.title = "Admin overview · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const u = users.data;
  const counts = u
    ? {
        total: u.items.length,
        students: u.items.filter((x) => x.role === "student").length,
        admins: u.items.filter((x) => x.role === "admin" || x.role === "super_admin").length,
        verified: u.items.filter((x) => x.is_verified).length,
        // is_active comes from the account-security migration; older backends omit it.
        deactivated: u.items.some((x) => "is_active" in x) ? u.items.filter((x) => x.is_active === false).length : null,
      }
    : null;
  const maxDomain = Math.max(1, ...(domains.data || []).map((d) => d.count));

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <AdminHeader title="Admin overview" description="Counts are calculated from the live data the admin endpoints return. Nothing here changes data." />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Section title="Users" link="/admin/users" linkLabel="Manage users">
          {users.status === "error" ? (
            <AdminError error={users.error} onRetry={users.reload} label="the user list" />
          ) : !counts ? (
            <CardSkeleton label="user counts" lines={2} />
          ) : (
            <>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Registered users" value={counts.total} />
                <Stat label="Students" value={counts.students} />
                <Stat label="Admins" value={counts.admins} />
                <Stat label="Email verified" value={counts.verified} hint={`${counts.total - counts.verified} not verified`} />
              </dl>
              {!u.complete && <p className="text-xs text-amber-800">Showing counts for the first {counts.total} users only.</p>}
              {counts.deactivated != null && (
                <p className="text-xs text-slate-500">
                  {counts.deactivated === 0 ? "All accounts are active." : `${counts.deactivated} deactivated account${counts.deactivated === 1 ? "" : "s"}.`}
                </p>
              )}
            </>
          )}
        </Section>

        <Section title="Internships" link="/admin/internships" linkLabel="Manage internships">
          {totals.status === "error" ? (
            <AdminError error={totals.error} onRetry={totals.reload} label="internship totals" />
          ) : !totals.data ? (
            <CardSkeleton label="internship totals" lines={2} />
          ) : (
            <dl className="grid grid-cols-3 gap-3">
              <Stat label="All internships" value={totals.data.all} />
              <Stat label="Active" value={totals.data.active} />
              <Stat label="Deactivated" value={totals.data.all - totals.data.active} />
            </dl>
          )}
          <div>
            <h3 className="text-sm font-medium text-slate-700">Active internships by domain</h3>
            {domains.status === "error" ? (
              <AdminError error={domains.error} onRetry={domains.reload} label="domain counts" />
            ) : !domains.data ? (
              <CardSkeleton label="domain counts" lines={3} />
            ) : !domains.data.length ? (
              <p className="mt-2 text-sm text-slate-500">No active internships have a domain.</p>
            ) : (
              <ul className="mt-2 flex flex-col gap-1.5" aria-label="Active internships by domain">
                {domains.data.map((d) => (
                  <li key={d.domain} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_2.5rem] items-center gap-2 text-sm">
                    <span className="truncate text-slate-700" title={d.domain}>
                      {d.domain}
                    </span>
                    <span className="h-2 rounded-full bg-slate-100" aria-hidden="true">
                      <span className="block h-2 rounded-full bg-brand-500" style={{ width: `${(d.count / maxDomain) * 100}%` }} />
                    </span>
                    <span className="text-right tabular-nums text-slate-900">{d.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>

        <Section title="Search index" link="/admin/index" linkLabel="Index details">
          {index.status === "error" ? (
            <AdminError error={index.error} onRetry={index.reload} label="the index status" />
          ) : !index.data ? (
            <CardSkeleton label="the index status" lines={2} />
          ) : (
            <>
              <div className="flex flex-wrap gap-1.5">
                <Badge tone={index.data.built ? "success" : "danger"}>{index.data.built ? "Built" : "Not built"}</Badge>
                {index.data.stale && <Badge tone="warning">Out of date</Badge>}
                {!index.data.model_matches_configuration && index.data.built && <Badge tone="warning">Model differs from configuration</Badge>}
              </div>
              <dl className="grid grid-cols-2 gap-3">
                <Stat label="Indexed vectors" value={index.data.indexed_vectors} />
                <Stat label="Active internships" value={index.data.active_internships} />
              </dl>
              <p className="text-xs text-slate-500">Last built: {index.data.built_at ? formatDateTime(index.data.built_at) : "never"}</p>
            </>
          )}
        </Section>

        <Section title="Not available from the backend">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
            <li>Skill management and skill counts (no admin skill endpoints).</li>
            <li>Audit logs and recent admin activity.</li>
            <li>Account activation or deactivation; only the role can be changed.</li>
            <li>User details, profiles and resume files.</li>
          </ul>
        </Section>
      </div>
    </div>
  );
}
