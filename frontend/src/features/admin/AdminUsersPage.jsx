import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createUser, deactivateUser, listUsers, reactivateUser, sendInvitation, updateUserRole } from "../../api/admin";
import { errorMessage } from "../../api/errors";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import Modal from "../../components/ui/Modal";
import { useAuth } from "../../context/AuthContext";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDate, formatDateTime } from "../../utils/dates";
import { CardEmpty, CardSkeleton } from "../dashboard/components/DashboardCard";
import { AdminError, AdminHeader, adminPanel, fullName } from "./adminShared";

const PAGE = 50;
const ROLE_LABEL = { student: "Student", admin: "Admin", super_admin: "Super admin" };
const ROLE_TONE = { student: "neutral", admin: "info", super_admin: "success" };
const STATUS_PARAM = { active: true, deactivated: false };
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
// Latest invitation (AdminUserResponse.invitation): its state and what happened to the email.
const INVITE_STATE = { pending: "Invitation sent", expired: "Invitation expired", revoked: "Invitation cancelled", accepted: "Invitation accepted" };
const DELIVERY = { sent: "email sent", outboxed: "saved to the test outbox (not sent)", skipped: "email disabled", failed: "email failed", pending: "sending…" };
export function invitationText(invitation) {
  if (!invitation) return "No invitation sent";
  const state = INVITE_STATE[invitation.status] || invitation.status;
  return invitation.status === "pending" || invitation.delivery_status === "failed"
    ? `${state} · ${DELIVERY[invitation.delivery_status] || invitation.delivery_status}`
    : state;
}
const field = "cn-input";

// What the signed-in administrator may do with a user (mirrors backend/routes/admin.ensure_can_manage).
export function permissionsFor(me, u) {
  const isSuper = me?.role === "super_admin";
  if (u.role === "super_admin") return { manage: false, reason: "Protected account" };
  if (me?.user_id === u.user_id) return { manage: false, reason: "You can't change your own account" };
  if (u.role === "admin" && !isSuper) return { manage: false, reason: "Only the super admin manages administrators" };
  return { manage: true, changeRole: isSuper };
}

function AddUserDialog({ isSuper, onClose, onCreated }) {
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", phone_number: "", role: "student" });
  const [errors, setErrors] = useState({});
  const [failure, setFailure] = useState(null);
  const [saving, setSaving] = useState(false);
  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    const problems = {};
    if (!form.first_name.trim()) problems.first_name = "Enter a first name.";
    if (!form.last_name.trim()) problems.last_name = "Enter a last name.";
    if (!EMAIL_RE.test(form.email.trim())) problems.email = "Enter a valid email address.";
    if (form.phone_number.trim() && !/^\+?\d{7,15}$/.test(form.phone_number.replace(/[\s().-]/g, ""))) problems.phone_number = "Enter 7 to 15 digits.";
    setErrors(problems);
    if (Object.keys(problems).length) return;
    setSaving(true);
    setFailure(null);
    try {
      const body = { first_name: form.first_name.trim(), last_name: form.last_name.trim(), email: form.email.trim(), role: form.role };
      if (form.phone_number.trim()) body.phone_number = form.phone_number.trim();
      onCreated(await createUser(body));
    } catch (error) {
      setFailure(errorMessage(error));
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Add user"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form="add-user-form" loading={saving}>
            Create account
          </Button>
        </>
      }
    >
      <form id="add-user-form" onSubmit={submit} noValidate className="flex flex-col gap-3">
        <p className="text-xs text-slate-500">
          The account is created as <strong>pending activation</strong> and an invitation email is sent straight away. You never set or
          see a password: the person opens the link (valid for 72 hours, single use) and chooses their own password.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Input label="First name" value={form.first_name} onChange={set("first_name")} error={errors.first_name} maxLength={100} />
          <Input label="Last name" value={form.last_name} onChange={set("last_name")} error={errors.last_name} maxLength={100} />
        </div>
        <Input label="Email" type="email" value={form.email} onChange={set("email")} error={errors.email} maxLength={255} />
        <Input label="Phone (optional)" value={form.phone_number} onChange={set("phone_number")} error={errors.phone_number} maxLength={20} />
        {isSuper && (
          <div className="flex flex-col gap-1">
            <label htmlFor="new-user-role" className="text-sm font-medium text-slate-700">
              Role
            </label>
            <select id="new-user-role" value={form.role} onChange={set("role")} className={field}>
              <option value="student">Student</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        )}
        {failure && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
            {failure}
          </p>
        )}
      </form>
    </Modal>
  );
}

// GET /admin/users with server-side search (name or email), role and status filters; ordered by id.
// Deactivate/reactivate for accounts the signed-in administrator may manage; role changes for the
// super admin only. The super admin account is shown as protected. Phone numbers and UUIDs are not shown.
export default function AdminUsersPage() {
  const { user: me } = useAuth();
  const isSuper = me?.role === "super_admin";
  const confirm = useConfirm();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const skip = Math.max(0, Number(params.get("skip")) || 0);
  const q = params.get("q") || "";
  const role = params.get("role") || "";
  const statusFilter = params.get("status") || "";
  const users = useApiResource(
    () => listUsers({ skip, limit: PAGE, q, role, isActive: STATUS_PARAM[statusFilter] }),
    `admin-users:${skip}:${q}:${role}:${statusFilter}`,
  );
  const [search, setSearch] = useState(q);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(false);
  const lock = useRef(false);

  useEffect(() => {
    const previous = document.title;
    document.title = "Users · Admin · CareerNova AI";
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

  const run = async (u, action, success) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(u.user_id);
    setError(null);
    try {
      const updated = await action();
      users.setData(users.data.map((x) => (x.user_id === updated.user_id ? updated : x)));
      toast.success(success(updated));
    } catch (failure) {
      setError({ id: u.user_id, message: errorMessage(failure) });
    } finally {
      lock.current = false;
      setBusy(null);
    }
  };

  const changeRole = async (u) => {
    const next = u.role === "admin" ? "student" : "admin";
    const ok = await confirm({
      title: next === "admin" ? `Make ${fullName(u)} an administrator?` : `Remove admin access from ${fullName(u)}?`,
      message:
        next === "admin"
          ? "Administrators can see every user, manage student accounts, edit or deactivate internships and rebuild the search index."
          : "They will lose access to all admin pages and become a student.",
      confirmLabel: next === "admin" ? "Make admin" : "Make student",
      tone: next === "admin" ? "primary" : "danger",
    });
    if (!ok) return;
    await run(u, () => updateUserRole(u.user_id, next), (x) => `${fullName(x)} is now ${x.role === "admin" ? "an administrator" : "a student"}.`);
  };

  const toggleActive = async (u) => {
    const deactivate = u.is_active !== false;
    const ok = await confirm({
      title: deactivate ? `Deactivate ${fullName(u)}?` : `Reactivate ${fullName(u)}?`,
      message: deactivate
        ? "They are signed out everywhere immediately and can't sign in or use the app until reactivated. Their data is kept."
        : "They will be able to sign in again with their existing password.",
      confirmLabel: deactivate ? "Deactivate" : "Reactivate",
      tone: deactivate ? "danger" : "primary",
    });
    if (!ok) return;
    await run(
      u,
      () => (deactivate ? deactivateUser(u.user_id) : reactivateUser(u.user_id)),
      (x) => `${fullName(x)} is ${x.is_active ? "active again" : "deactivated"}.`,
    );
  };

  const created = (account) => {
    setAdding(false);
    const delivery = account.invitation?.delivery_status;
    if (delivery === "failed") toast.error(`${fullName(account)} was added, but the invitation email failed. Use "Resend invitation".`);
    else toast.success(`${fullName(account)} was added. ${invitationText(account.invitation)}.`);
    users.reload();
  };

  const resend = async (u) => {
    const ok = await confirm({
      title: `Send a new invitation to ${fullName(u)}?`,
      message: "A new activation link is emailed to them. Any earlier link stops working.",
      confirmLabel: "Send invitation",
      tone: "primary",
    });
    if (!ok) return;
    await run(u, () => sendInvitation(u.user_id), (x) => `${fullName(x)}: ${invitationText(x.invitation)}.`);
  };

  const rows = users.data || [];
  const filtered = Boolean(q || role || statusFilter);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <AdminHeader
        title="Users"
        description={
          isSuper
            ? "Search accounts, add users, deactivate or reactivate them, and change roles. Your super admin account is protected."
            : "Search accounts, add students, and deactivate or reactivate student accounts. Role changes are reserved for the super admin."
        }
      >
        <Button onClick={() => setAdding(true)}>Add user</Button>
      </AdminHeader>
      <section className={adminPanel} aria-label="User list">
        <form
          className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end"
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            update({ q: search.trim(), skip: 0 });
          }}
        >
          <div className="flex flex-1 flex-col gap-1">
            <label htmlFor="user-search" className="text-sm font-medium text-slate-700">
              Search by name or email
            </label>
            <input id="user-search" type="search" value={search} onChange={(e) => setSearch(e.target.value)} maxLength={100} className={field} />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="role-filter" className="text-sm font-medium text-slate-700">
              Role
            </label>
            <select id="role-filter" value={role} onChange={(e) => update({ role: e.target.value, skip: 0 })} className={field}>
              <option value="">All roles</option>
              <option value="student">Students</option>
              <option value="admin">Admins</option>
              <option value="super_admin">Super admin</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="status-filter" className="text-sm font-medium text-slate-700">
              Status
            </label>
            <select id="status-filter" value={statusFilter} onChange={(e) => update({ status: e.target.value, skip: 0 })} className={field}>
              <option value="">All</option>
              <option value="active">Active</option>
              <option value="deactivated">Deactivated</option>
            </select>
          </div>
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>

        {(users.status === "loading" || users.status === "idle") && !users.data ? (
          <CardSkeleton label="users" lines={5} />
        ) : users.status === "error" ? (
          <AdminError error={users.error} onRetry={users.reload} label="the user list" />
        ) : !rows.length ? (
          <CardEmpty
            title={filtered ? "No matching users" : skip ? "No more users" : "No users"}
            message={filtered ? "No account matches this search and these filters." : skip ? "You've reached the end of the list." : "No accounts are registered yet."}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[48rem] text-left text-sm">
              <caption className="sr-only">Users on this page</caption>
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="py-2 pr-3">Name</th>
                  <th scope="col" className="py-2 pr-3">Email</th>
                  <th scope="col" className="py-2 pr-3">Role</th>
                  <th scope="col" className="py-2 pr-3">Status</th>
                  <th scope="col" className="py-2 pr-3">Last sign-in</th>
                  <th scope="col" className="py-2 pr-3">Joined</th>
                  <th scope="col" className="py-2"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((u) => {
                  const self = me?.user_id === u.user_id;
                  const can = permissionsFor(me, u);
                  const active = u.is_active !== false;
                  return (
                    <tr key={u.user_id}>
                      <th scope="row" className="py-2.5 pr-3 font-medium text-slate-900">
                        {fullName(u)}
                        {self && <span className="ml-1.5 text-xs font-normal text-slate-500">(you)</span>}
                      </th>
                      <td className="break-all py-2.5 pr-3 text-slate-600">{u.email}</td>
                      <td className="py-2.5 pr-3">
                        <Badge tone={ROLE_TONE[u.role] || "neutral"}>{ROLE_LABEL[u.role] || u.role}</Badge>
                        {u.role === "super_admin" && <span className="ml-1.5 text-xs text-slate-500">Protected</span>}
                      </td>
                      <td className="py-2.5 pr-3">
                        {!active ? (
                          <Badge tone="danger">Deactivated</Badge>
                        ) : u.is_verified ? (
                          <Badge tone="success">Active</Badge>
                        ) : (
                          <>
                            <Badge tone="warning">Pending activation</Badge>
                            <span className={`mt-0.5 block text-xs ${u.invitation?.delivery_status === "failed" ? "text-red-700" : "text-slate-500"}`}>
                              {invitationText(u.invitation)}
                            </span>
                          </>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-slate-600">{u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}</td>
                      <td className="py-2.5 pr-3 text-slate-600">{formatDate(u.created_at)}</td>
                      <td className="py-2.5 text-right">
                        {can.manage ? (
                          <span className="inline-flex flex-wrap justify-end gap-2">
                            {can.changeRole && active && (
                              <Button
                                variant="secondary"
                                onClick={() => changeRole(u)}
                                loading={busy === u.user_id}
                                disabled={Boolean(busy)}
                                className="py-1.5 text-xs"
                                aria-label={u.role === "admin" ? `Make ${fullName(u)} a student` : `Make ${fullName(u)} an admin`}
                              >
                                {u.role === "admin" ? "Make student" : "Make admin"}
                              </Button>
                            )}
                            {active && !u.is_verified && (
                              <Button
                                variant="secondary"
                                onClick={() => resend(u)}
                                disabled={Boolean(busy)}
                                className="py-1.5 text-xs"
                                aria-label={`Resend invitation to ${fullName(u)}`}
                              >
                                Resend invitation
                              </Button>
                            )}
                            <Button
                              variant={active ? "danger" : "secondary"}
                              onClick={() => toggleActive(u)}
                              disabled={Boolean(busy)}
                              className="py-1.5 text-xs"
                              aria-label={active ? `Deactivate ${fullName(u)}` : `Reactivate ${fullName(u)}`}
                            >
                              {active ? "Deactivate" : "Reactivate"}
                            </Button>
                          </span>
                        ) : (
                          <span className="text-xs text-slate-500">{can.reason}</span>
                        )}
                        {error?.id === u.user_id && (
                          <p role="alert" className="mt-1 text-xs text-red-700">
                            {error.message}
                          </p>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <nav aria-label="User pages" className="mt-4 flex items-center justify-between gap-3 text-sm text-slate-600">
          <span>
            Users {rows.length ? skip + 1 : 0}–{skip + rows.length}
          </span>
          <span className="flex gap-2">
            <Button variant="secondary" disabled={skip === 0} onClick={() => update({ skip: Math.max(0, skip - PAGE) })}>
              Previous
            </Button>
            <Button variant="secondary" disabled={!users.data || users.data.length < PAGE} onClick={() => update({ skip: skip + PAGE })}>
              Next
            </Button>
          </span>
        </nav>
      </section>
      {adding && <AddUserDialog isSuper={isSuper} onClose={() => setAdding(false)} onCreated={created} />}
    </div>
  );
}
