import { useState } from "react";
import { errorMessage } from "../../../api/errors";
import { saveResumeCorrections } from "../../../api/resumes";
import Button from "../../../components/ui/Button";
import Input from "../../../components/ui/Input";

const field = "w-full cn-input";
const SCALARS = [
  ["full_name", "Full name"], ["email", "Email"], ["phone", "Phone"], ["address", "Address"],
  ["linkedin", "LinkedIn URL"], ["github", "GitHub URL"],
];
// Entry sections hold free text; one entry per block, blocks separated by a blank line.
const ENTRY_SECTIONS = [
  ["education", "Education"], ["work_experience", "Work experience"], ["internships", "Internships"], ["projects", "Projects"],
];
const LIST_SECTIONS = [["certifications", "Certifications"], ["achievements", "Achievements"], ["languages", "Languages"]];

const entryText = (entry) => (typeof entry === "string" ? entry : Object.values(entry || {}).filter((v) => typeof v === "string").join("\n"));
export const toBlocks = (entries) => (entries || []).map(entryText).filter(Boolean).join("\n\n");
export const fromBlocks = (text) =>
  text
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean)
    .map((details) => ({ details }));
export const toLines = (items) => (items || []).join("\n");
export const fromLines = (text) =>
  text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
export const fromCommaList = (text) =>
  [...new Set(text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean))];

// Lets the student correct what the parser extracted. Saved as a new version; the parser's version
// is kept and "Re-parse" returns to it. Nothing is added that the student does not type.
export default function ResumeEditor({ detail, onSaved, onCancel }) {
  const data = detail.extracted_data || {};
  const [values, setValues] = useState(() => ({
    ...Object.fromEntries(SCALARS.map(([k]) => [k, data[k] || ""])),
    professional_summary: data.professional_summary || "",
    skills: (data.skills || []).join(", "),
    ...Object.fromEntries(ENTRY_SECTIONS.map(([k]) => [k, toBlocks(data[k])])),
    ...Object.fromEntries(LIST_SECTIONS.map(([k]) => [k, toLines(data[k])])),
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const set = (key) => (event) => setValues((v) => ({ ...v, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    const skills = fromCommaList(values.skills);
    const body = {
      ...Object.fromEntries(SCALARS.map(([k]) => [k, values[k].trim() || null])),
      professional_summary: values.professional_summary.trim() || null,
      skills,
      technical_skills: skills,
      soft_skills: data.soft_skills || [],
      ...Object.fromEntries(ENTRY_SECTIONS.map(([k]) => [k, fromBlocks(values[k])])),
      ...Object.fromEntries(LIST_SECTIONS.map(([k]) => [k, fromLines(values[k])])),
    };
    try {
      onSaved(await saveResumeCorrections(detail.resume_id, body));
    } catch (failure) {
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-label="Edit extracted details">
      <p className="rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-800">
        Correct anything that was read incorrectly. Your version is used for matching, documents and the assistant. “Re-parse” returns to the
        version read from the file.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {SCALARS.map(([key, label]) => (
          <Input key={key} label={label} value={values[key]} onChange={set(key)} maxLength={key === "address" ? 500 : 300} />
        ))}
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="edit-summary" className="text-sm font-medium text-slate-700">
          Professional summary
        </label>
        <textarea id="edit-summary" rows={3} value={values.professional_summary} onChange={set("professional_summary")} maxLength={5000} className={field} />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="edit-skills" className="text-sm font-medium text-slate-700">
          Skills <span className="font-normal text-slate-500">(comma separated)</span>
        </label>
        <textarea id="edit-skills" rows={2} value={values.skills} onChange={set("skills")} className={field} />
      </div>
      {ENTRY_SECTIONS.map(([key, label]) => (
        <div key={key} className="flex flex-col gap-1">
          <label htmlFor={`edit-${key}`} className="text-sm font-medium text-slate-700">
            {label} <span className="font-normal text-slate-500">(one entry per block; leave a blank line between entries)</span>
          </label>
          <textarea id={`edit-${key}`} rows={4} value={values[key]} onChange={set(key)} className={field} />
        </div>
      ))}
      {LIST_SECTIONS.map(([key, label]) => (
        <div key={key} className="flex flex-col gap-1">
          <label htmlFor={`edit-${key}`} className="text-sm font-medium text-slate-700">
            {label} <span className="font-normal text-slate-500">(one per line)</span>
          </label>
          <textarea id={`edit-${key}`} rows={2} value={values[key]} onChange={set(key)} className={field} />
        </div>
      ))}
      {error && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving}>
          Save corrections
        </Button>
      </div>
    </form>
  );
}
