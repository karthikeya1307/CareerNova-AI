import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createInternship, INTERNSHIP_LIMITS as L, updateInternship } from "../../api/admin";
import { getInternship, WORK_MODES } from "../../api/internships";
import Button from "../../components/ui/Button";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Input from "../../components/ui/Input";
import Select from "../../components/ui/Select";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { isoToLocalInput, localInputToIso } from "../../utils/dates";
import { CardEmpty, CardSkeleton } from "../dashboard/components/DashboardCard";
import { AdminError, AdminHeader, adminPanel } from "./adminShared";

const EMPTY = {
  title: "", company: "", description: "", eligibility: "", location: "", application_url: "", deadline: "", domain: "", work_mode: "",
  duration_weeks: "", stipend_per_month: "", stipend_currency: "INR", min_education: "", required_skills: "", preferred_skills: "",
};
const TEXT = ["title", "company", "description", "eligibility", "location", "application_url", "domain", "min_education"];

// Comma- or line-separated skills, trimmed and de-duplicated case-insensitively (like the backend).
export function parseSkills(text) {
  const seen = new Set();
  const out = [];
  for (const raw of String(text || "").split(/[,\n]/)) {
    const s = raw.trim();
    if (s && !seen.has(s.toLowerCase())) {
      seen.add(s.toLowerCase());
      out.push(s);
    }
  }
  return out;
}

const fromInternship = (i) => ({
  ...EMPTY,
  ...Object.fromEntries(TEXT.map((k) => [k, i[k] || ""])),
  deadline: isoToLocalInput(i.deadline),
  work_mode: i.work_mode || "",
  duration_weeks: i.duration_weeks != null ? String(i.duration_weeks) : "",
  stipend_per_month: i.stipend_per_month != null ? String(i.stipend_per_month) : "",
  stipend_currency: i.stipend_currency || "INR",
  required_skills: (i.required_skills || []).join(", "),
  preferred_skills: (i.preferred_skills || []).join(", "),
});

// Mirrors InternshipCreate / InternshipUpdate validation.
export function validateInternship(form) {
  const errors = {};
  if (!form.title.trim()) errors.title = "Enter the title.";
  if (!form.company.trim()) errors.company = "Enter the company.";
  for (const k of TEXT) if (form[k].trim().length > L[k]) errors[k] = `Use at most ${L[k].toLocaleString()} characters.`;
  if (form.application_url.trim() && !/^https?:\/\//i.test(form.application_url.trim())) errors.application_url = "Start the link with http:// or https://.";
  if (form.duration_weeks !== "" && (!/^\d+$/.test(form.duration_weeks) || +form.duration_weeks < 1 || +form.duration_weeks > 104)) errors.duration_weeks = "Enter 1–104 weeks.";
  if (form.stipend_per_month !== "" && (!/^\d+$/.test(form.stipend_per_month) || +form.stipend_per_month > 1000000)) errors.stipend_per_month = "Enter a whole number from 0 to 1,000,000.";
  if (!/^[A-Z]{3}$/.test(form.stipend_currency)) errors.stipend_currency = "Use a 3-letter code such as INR.";
  if (form.deadline && Number.isNaN(new Date(form.deadline).getTime())) errors.deadline = "Choose a valid date.";
  for (const k of ["required_skills", "preferred_skills"]) {
    const skills = parseSkills(form[k]);
    if (skills.length > L.skills) errors[k] = `Use at most ${L.skills} skills.`;
    else if (skills.some((s) => s.length > L.skillName)) errors[k] = `Each skill can have at most ${L.skillName} characters.`;
  }
  return errors;
}

// Body for the backend: create sends every filled field; edit sends only what changed (null clears).
export function internshipBody(form, original = null) {
  const value = {
    ...Object.fromEntries(TEXT.map((k) => [k, form[k].trim() || null])),
    deadline: form.deadline ? localInputToIso(form.deadline) : null,
    work_mode: form.work_mode || null,
    duration_weeks: form.duration_weeks === "" ? null : Number(form.duration_weeks),
    stipend_per_month: form.stipend_per_month === "" ? null : Number(form.stipend_per_month),
    stipend_currency: form.stipend_currency,
    required_skills: parseSkills(form.required_skills),
    preferred_skills: parseSkills(form.preferred_skills),
  };
  if (!original) {
    return Object.fromEntries(Object.entries(value).filter(([, v]) => v !== null && !(Array.isArray(v) && !v.length)));
  }
  const before = { ...fromInternship(original) };
  const prev = internshipBody(before);
  const body = {};
  for (const [k, v] of Object.entries(value)) {
    const old = k in prev ? prev[k] : Array.isArray(v) ? [] : null;
    if (JSON.stringify(v) !== JSON.stringify(old)) body[k] = v;
  }
  return body;
}

export default function AdminInternshipFormPage() {
  const { internshipId } = useParams();
  const id = internshipId ? Number(internshipId) : null;
  const editing = Boolean(internshipId);
  const navigate = useNavigate();
  const toast = useToast();
  const existing = useApiResource(() => getInternship(id), `admin-internship:${id}`, { enabled: editing && Number.isInteger(id) && id > 0 });
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);

  useEffect(() => {
    if (existing.data) setForm(fromInternship(existing.data));
  }, [existing.data]);

  useEffect(() => {
    const previous = document.title;
    document.title = `${editing ? "Edit" : "Add"} internship · Admin · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [editing]);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: field === "stipend_currency" ? e.target.value.toUpperCase() : e.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (lock.current) return;
    const found = validateInternship(form);
    setErrors(found);
    setApiError(null);
    setNotice(null);
    if (Object.keys(found).length) return;
    const body = internshipBody(form, editing ? existing.data : null);
    if (editing && !Object.keys(body).length) {
      setNotice("Nothing has changed.");
      return;
    }
    lock.current = true;
    setBusy(true);
    try {
      const saved = editing ? await updateInternship(id, body) : await createInternship(body);
      toast.success(editing ? `${saved.title} was updated.` : `${saved.title} was added (#${saved.internship_id}).`);
      navigate("/admin/internships");
    } catch (failure) {
      setApiError(failure);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  const header = (
    <AdminHeader
      title={editing ? "Edit internship" : "Add internship"}
      description={editing ? `Internship #${internshipId}. Only the fields you change are sent.` : "New internships are created as active, with source “admin”."}
    >
      <Link to="/admin/internships" className="text-sm font-medium text-brand-700 hover:underline">
        Back to internships
      </Link>
    </AdminHeader>
  );

  if (editing && (existing.status === "error" || !(Number.isInteger(id) && id > 0))) {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        {header}
        <div className={adminPanel}>
          {existing.error?.status === 404 || !(Number.isInteger(id) && id > 0) ? (
            <CardEmpty title="Internship not found" message="It doesn't exist." />
          ) : (
            <AdminError error={existing.error} onRetry={existing.reload} label="the internship" />
          )}
        </div>
      </div>
    );
  }
  if (editing && !existing.data) {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        {header}
        <div className={adminPanel}>
          <CardSkeleton label="the internship" lines={6} />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      {header}
      <form onSubmit={submit} noValidate aria-label={editing ? "Edit internship" : "Add internship"} className={`${adminPanel} flex flex-col gap-4`}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input label="Title" value={form.title} onChange={set("title")} error={errors.title} maxLength={L.title} required />
          <Input label="Company" value={form.company} onChange={set("company")} error={errors.company} maxLength={L.company} required />
          <Input label="Domain" value={form.domain} onChange={set("domain")} error={errors.domain} maxLength={L.domain} hint="For example Data Science" />
          <Input label="Location" value={form.location} onChange={set("location")} error={errors.location} maxLength={L.location} />
          <Select label="Work mode" value={form.work_mode} onChange={set("work_mode")} options={[{ value: "", label: "Not specified" }, ...WORK_MODES.map((m) => ({ value: m, label: m }))]} />
          <Input label="Application deadline" type="datetime-local" value={form.deadline} onChange={set("deadline")} error={errors.deadline} />
          <Input label="Duration (weeks)" inputMode="numeric" value={form.duration_weeks} onChange={set("duration_weeks")} error={errors.duration_weeks} />
          <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-2">
            <Input label="Stipend per month" inputMode="numeric" value={form.stipend_per_month} onChange={set("stipend_per_month")} error={errors.stipend_per_month} />
            <Input label="Currency" value={form.stipend_currency} onChange={set("stipend_currency")} error={errors.stipend_currency} maxLength={3} />
          </div>
          <Input label="Application link" type="url" value={form.application_url} onChange={set("application_url")} error={errors.application_url} maxLength={L.application_url} placeholder="https://" />
          <Input label="Minimum education" value={form.min_education} onChange={set("min_education")} error={errors.min_education} maxLength={L.min_education} />
        </div>
        {[
          ["description", "Description", 5],
          ["eligibility", "Eligibility", 3],
          ["required_skills", "Required skills (comma or line separated, up to 30)", 2],
          ["preferred_skills", "Preferred skills (comma or line separated, up to 30)", 2],
        ].map(([k, label, rows]) => (
          <div key={k} className="flex flex-col gap-1">
            <label htmlFor={`f-${k}`} className="text-sm font-medium text-slate-700">
              {label}
            </label>
            <textarea
              id={`f-${k}`}
              rows={rows}
              value={form[k]}
              onChange={set(k)}
              aria-invalid={errors[k] ? true : undefined}
              aria-describedby={errors[k] ? `f-${k}-error` : undefined}
              className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${errors[k] ? "border-red-400" : "border-slate-300"}`}
            />
            {errors[k] && (
              <p id={`f-${k}-error`} className="text-xs text-red-600">
                {errors[k]}
              </p>
            )}
          </div>
        ))}
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Saving changes the catalogue students see. Semantic search and matching use the search index, which is updated only when an administrator rebuilds it.
        </p>
        {notice && (
          <p role="status" className="text-sm text-slate-600">
            {notice}
          </p>
        )}
        <ErrorAlert error={apiError} title="The internship couldn't be saved" />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={busy}>
            {editing ? "Save changes" : "Add internship"}
          </Button>
          <Link to="/admin/internships" className="inline-flex items-center rounded-md px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
