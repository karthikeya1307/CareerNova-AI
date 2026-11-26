import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { listAuditEvents } from "../../api/admin";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import useApiResource from "../../hooks/useApiResource";
import { formatDateTime } from "../../utils/dates";
import { CardEmpty, CardSkeleton } from "../dashboard/components/DashboardCard";
import { AdminError, AdminHeader, adminPanel } from "./adminShared";

const PAGE = 50;

// backend/services/audit.ACTIONS
export const ACTION_LABEL = {
  "superadmin.bootstrap": "Super admin set up",
  "user.create": "User added",
  "user.role_change": "Role changed",
  "user.deactivate": "User deactivated",
  "user.reactivate": "User reactivated",
  "user.invite": "Invitation sent",
  "user.invite_revoke": "Invitation cancelled",
  "user.activate": "Account activated",
  "auth.login_locked": "Sign-in locked",
  "index.rebuild": "Search index rebuilt",
  "internship.create": "Internship created",
  "internship.update": "Internship updated",
  "internship.deactivate": "Internship deactivated",
  "internship.verify": "Internship verified",
};
const TONE = { "user.deactivate": "danger", "auth.login_locked": "warning", "user.role_change": "info", "superadmin.bootstrap": "info" };

// Plain-language summary of an event's details (the backend never stores secrets in them).
export function describeDetails(event) {
  const d = event.details || {};
  switch (event.action) {
    case "user.role_change":
      return `${d.from} → ${d.to}${d.via ? ` (${d.via})` : ""}`;
    case "user.create":
      return `${d.role}${d.pending_activation ? ", pending activation" : ""}`;
    case "user.invite":
      return d.resend ? "New link sent (earlier link revoked)" : "First invitation";
    case "user.invite_revoke":
      return d.revoked ? `${d.revoked} open invitation(s) cancelled` : "";
    case "user.activate":
      return d.via === "invitation" ? "Set own password via invitation" : "";
    case "user.deactivate":
      return d.signed_out_devices != null ? `Signed out of ${d.signed_out_devices} device(s)` : "";
    case "auth.login_locked":
      return `${d.limit} failed attempts within ${d.window_minutes} minutes`;
    case "index.rebuild":
      return `${d.indexed} internships indexed`;
    case "internship.update":
      return d.fields ? `Changed: ${d.fields.join(", ")}` : "";
    case "superadmin.bootstrap":
      return d.mode === "promoted_existing" ? `Existing account promoted (was ${d.previous_role})` : "New account created";
    default:
      return "";
  }
}

const actor = (event) => (event.actor_user_id ? `User #${event.actor_user_id} (${event.actor_role})` : event.action.startsWith("auth.") ? "System" : "Command line");

// GET /admin/audit-events, newest first. Read-only.
export default function AdminAuditPage() {
  const [params, setParams] = useSearchParams();
  const skip = Math.max(0, Number(params.get("skip")) || 0);
  const action = params.get("action") || "";
  const events = useApiResource(() => listAuditEvents({ skip, limit: PAGE, action }), `admin-audit:${skip}:${action}`);

  useEffect(() => {
    const previous = document.title;
    document.title = "Audit log · Admin · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const update = (changes) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, String(value));
      else next.delete(key);
    }
    setParams(next);
  };

  const page = events.data;
  const items = page?.items || [];

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <AdminHeader title="Audit log" description="Administrative and security actions, newest first. Passwords, tokens and credentials are never recorded." />
      <section className={adminPanel} aria-label="Audit events">
        <div className="mb-4 flex flex-col gap-1 sm:w-72">
          <label htmlFor="audit-action" className="text-sm font-medium text-slate-700">
            Action
          </label>
          <select
            id="audit-action"
            value={action}
            onChange={(e) => update({ action: e.target.value, skip: 0 })}
            className="cn-input"
          >
            <option value="">All actions</option>
            {Object.entries(ACTION_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {(events.status === "loading" || events.status === "idle") && !page ? (
          <CardSkeleton label="audit events" lines={5} />
        ) : events.status === "error" ? (
          <AdminError error={events.error} onRetry={events.reload} label="the audit log" />
        ) : !items.length ? (
          <CardEmpty title="No audit events" message={action ? "No events of this kind yet." : "Administrative actions will appear here."} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[48rem] text-left text-sm">
              <caption className="sr-only">Audit events</caption>
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="py-2 pr-3">When</th>
                  <th scope="col" className="py-2 pr-3">Action</th>
                  <th scope="col" className="py-2 pr-3">Target</th>
                  <th scope="col" className="py-2 pr-3">Details</th>
                  <th scope="col" className="py-2">By</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((e) => (
                  <tr key={e.event_id}>
                    <td className="whitespace-nowrap py-2.5 pr-3 text-slate-600">{formatDateTime(e.created_at)}</td>
                    <td className="py-2.5 pr-3">
                      <Badge tone={TONE[e.action] || "neutral"}>{ACTION_LABEL[e.action] || e.action}</Badge>
                    </td>
                    <td className="break-all py-2.5 pr-3 text-slate-700">{e.target_label || "—"}</td>
                    <td className="py-2.5 pr-3 text-slate-600">{describeDetails(e) || "—"}</td>
                    <td className="py-2.5 text-slate-600">{actor(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <nav aria-label="Audit pages" className="mt-4 flex items-center justify-between gap-3 text-sm text-slate-600">
          <span>{page ? `${page.total} event${page.total === 1 ? "" : "s"}` : ""}</span>
          <span className="flex gap-2">
            <Button variant="secondary" disabled={skip === 0} onClick={() => update({ skip: Math.max(0, skip - PAGE) })}>
              Previous
            </Button>
            <Button variant="secondary" disabled={!page || skip + items.length >= page.total} onClick={() => update({ skip: skip + PAGE })}>
              Next
            </Button>
          </span>
        </nav>
      </section>
    </div>
  );
}
