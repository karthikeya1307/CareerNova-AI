import { useRef, useState } from "react";
import { LIMITS, updateApplication, WORK_MODES } from "../../../api/applications";
import { listDocuments } from "../../../api/documents";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import Input from "../../../components/ui/Input";
import Select from "../../../components/ui/Select";
import useApiResource from "../../../hooks/useApiResource";
import { isoToLocalInput, localInputToIso } from "../../../utils/dates";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const text = (v) => (v == null ? "" : String(v));

// Edit details with PATCH /applications/{id} (ApplicationUpdate). For catalogue (internal)
// applications company, role and link come from the internship and cannot be edited.
export default function DetailsEditor({ application: a, onSaved, onCancel }) {
  const external = a.source === "external";
  const [form, setForm] = useState({
    company_name: text(a.company_name), title: text(a.title), application_url: text(a.application_url), location: text(a.location), work_mode: text(a.work_mode),
    applied_at: isoToLocalInput(a.applied_at), notes: text(a.notes), contact_name: text(a.contact_name), contact_email: text(a.contact_email),
    resume_document_id: a.resume_document_id ? String(a.resume_document_id) : "", cover_letter_document_id: a.cover_letter_document_id ? String(a.cover_letter_document_id) : "",
  });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const resumes = useApiResource(() => listDocuments({ type: "resume" }), "docs:resume");
  const letters = useApiResource(() => listDocuments({ type: "cover_letter" }), "docs:cover_letter");
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const validate = () => {
    const found = {};
    if (external && !form.company_name.trim()) found.company_name = "Enter the company.";
    if (external && !form.title.trim()) found.title = "Enter the role.";
    if (external && form.application_url.trim() && !/^https?:\/\/[^\s/]+\S*$/i.test(form.application_url.trim())) found.application_url = "Enter a full http:// or https:// URL.";
    if (form.contact_email.trim() && !EMAIL.test(form.contact_email.trim())) found.contact_email = "Enter a valid email address.";
    if (form.contact_name.length > LIMITS.contact) found.contact_name = `Use at most ${LIMITS.contact} characters.`;
    if (form.notes.length > LIMITS.notes) found.notes = `Keep notes under ${LIMITS.notes} characters.`;
    if (a.status !== "SAVED" && a.applied_at && !form.applied_at) found.applied_at = "A submitted application needs its application date.";
    if (form.applied_at && new Date(form.applied_at) > new Date()) found.applied_at = "The date can't be in the future.";
    return found;
  };

  // Only fields that changed are sent; cleared optional fields are sent as null.
  const changes = () => {
    const body = {};
    const optional = (key, value, original) => {
      const next = value.trim() ? value.trim() : null;
      if ((next ?? null) !== (original ?? null)) body[key] = next;
    };
    if (external) {
      if (form.company_name.trim() !== a.company_name) body.company_name = form.company_name.trim();
      if (form.title.trim() !== a.title) body.title = form.title.trim();
      optional("application_url", form.application_url, a.application_url);
      optional("location", form.location, a.location);
      if ((form.work_mode || null) !== (a.work_mode || null)) body.work_mode = form.work_mode || null;
    }
    if (a.status !== "SAVED" && form.applied_at !== isoToLocalInput(a.applied_at)) body.applied_at = localInputToIso(form.applied_at);
    if ((form.notes.trim() ? form.notes : null) !== (a.notes ?? null)) body.notes = form.notes.trim() ? form.notes : null;
    optional("contact_name", form.contact_name, a.contact_name);
    optional("contact_email", form.contact_email, a.contact_email);
    for (const key of ["resume_document_id", "cover_letter_document_id"]) {
      const next = form[key] ? Number(form[key]) : null;
      if (next !== (a[key] ?? null)) body[key] = next;
    }
    return body;
  };

  const submit = async (event) => {
    event.preventDefault();
    if (lock.current) return;
    const found = validate();
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length) return;
    const body = changes();
    if (!Object.keys(body).length) {
      onCancel();
      return;
    }
    lock.current = true;
    setBusy(true);
    try {
      onSaved(await updateApplication(a.application_id, body));
    } catch (failure) {
      setApiError(failure);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  const docOptions = (res, current) => [
    { value: "", label: "None" },
    ...(res.data || []).map((d) => ({ value: String(d.document_id), label: d.title || `Document #${d.document_id}` })),
    ...(current && !(res.data || []).some((d) => d.document_id === current) ? [{ value: String(current), label: `Document #${current}` }] : []),
  ];

  return (
    <form onSubmit={submit} noValidate aria-label="Edit application details" className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {external && (
          <>
            <Input label="Company" value={form.company_name} onChange={set("company_name")} error={errors.company_name} maxLength={LIMITS.name} />
            <Input label="Role" value={form.title} onChange={set("title")} error={errors.title} maxLength={LIMITS.name} />
            <Input label="Application link" type="url" value={form.application_url} onChange={set("application_url")} error={errors.application_url} />
            <Input label="Location" value={form.location} onChange={set("location")} maxLength={150} />
            <Select label="Work mode" value={form.work_mode} onChange={set("work_mode")} options={[{ value: "", label: "Not specified" }, ...WORK_MODES.map((m) => ({ value: m, label: m }))]} />
          </>
        )}
        {a.status !== "SAVED" && <Input label="Date applied" type="datetime-local" value={form.applied_at} onChange={set("applied_at")} error={errors.applied_at} />}
        <Input label="Contact name" value={form.contact_name} onChange={set("contact_name")} error={errors.contact_name} maxLength={LIMITS.contact} />
        <Input label="Contact email" type="email" value={form.contact_email} onChange={set("contact_email")} error={errors.contact_email} />
        <Select label="Resume sent" value={form.resume_document_id} onChange={set("resume_document_id")} options={docOptions(resumes, a.resume_document_id)} />
        <Select label="Cover letter sent" value={form.cover_letter_document_id} onChange={set("cover_letter_document_id")} options={docOptions(letters, a.cover_letter_document_id)} />
      </div>
      <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
        Notes
        <textarea rows={4} value={form.notes} onChange={set("notes")} className="rounded-md border border-slate-300 px-3 py-2 text-sm font-normal shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
        {errors.notes && <span className="text-xs font-normal text-red-600">{errors.notes}</span>}
      </label>
      <ErrorAlert error={apiError} title="Your changes couldn't be saved" />
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          Save details
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
