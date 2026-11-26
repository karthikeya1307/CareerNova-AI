import { useState } from "react";
import { updateDocument } from "../../../api/documents";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";

// Edit the wording of a document. Structure (sections, items, paragraph keys, fact links) is kept;
// the backend saves a new "edited" version and fact-checks it against the resume.
// Limits from backend/schemas/document_schema.py: line 1-500 chars (max 20 per item), paragraph 1-2000.
const LINE_MAX = 500;
const LINES_PER_ITEM = 20;
const PARAGRAPH_MAX = 2000;

function toDraft(content) {
  if (content.type === "cover_letter") return { paragraphs: content.paragraphs.map((p) => p.text) };
  return { items: content.sections.map((s) => s.items.map((item) => (item.lines || []).join("\n"))) };
}

export function validateDraft(content, draft) {
  const errors = {};
  if (content.type === "cover_letter") {
    draft.paragraphs.forEach((text, i) => {
      const t = text.trim();
      if (!t) errors[`p${i}`] = "A paragraph can't be empty.";
      else if (t.length > PARAGRAPH_MAX) errors[`p${i}`] = `Keep each paragraph under ${PARAGRAPH_MAX} characters.`;
    });
  } else {
    draft.items.forEach((section, s) =>
      section.forEach((text, i) => {
        const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
        if (lines.length > LINES_PER_ITEM) errors[`s${s}i${i}`] = `Use at most ${LINES_PER_ITEM} lines.`;
        else if (lines.some((l) => l.length > LINE_MAX)) errors[`s${s}i${i}`] = `Keep each line under ${LINE_MAX} characters.`;
      }),
    );
  }
  return errors;
}

function buildContent(content, draft) {
  if (content.type === "cover_letter") {
    return { ...content, paragraphs: content.paragraphs.map((p, i) => ({ ...p, text: draft.paragraphs[i].trim() })) };
  }
  return {
    ...content,
    sections: content.sections.map((section, s) => ({
      ...section,
      items: section.items.map((item, i) => ({
        ...item,
        lines: draft.items[s][i].split("\n").map((l) => l.trim()).filter(Boolean),
      })),
    })),
  };
}

export default function DocumentEditor({ document: doc, onSaved, onCancel }) {
  const content = doc.content_json;
  const [draft, setDraft] = useState(() => toDraft(content));
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [saving, setSaving] = useState(false);

  const save = async (event) => {
    event.preventDefault();
    if (saving) return;
    const found = validateDraft(content, draft);
    setErrors(found);
    setApiError(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      onSaved(await updateDocument(doc.document_id, { content: buildContent(content, draft) }));
    } catch (failure) {
      setApiError(failure);
    } finally {
      setSaving(false);
    }
  };

  const area = (id, label, value, onChange, max, rows) => (
    <div key={id} className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-slate-600">
        {label}
      </label>
      <textarea
        id={id}
        rows={rows}
        value={value}
        maxLength={max}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={errors[id.replace("edit-", "")] ? true : undefined}
        className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500 ${errors[id.replace("edit-", "")] ? "border-red-400" : "border-slate-300"}`}
      />
      {errors[id.replace("edit-", "")] && <p className="text-xs text-red-600">{errors[id.replace("edit-", "")]}</p>}
    </div>
  );

  return (
    <form onSubmit={save} noValidate className="flex flex-col gap-4" aria-label="Edit document">
      <p className="rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-900">
        Edit the wording only. Your changes are saved as a new version and checked against your resume; anything not supported by it is flagged.
      </p>
      {content.type === "cover_letter"
        ? content.paragraphs.map((p, i) =>
            area(`edit-p${i}`, `Paragraph ${i + 1} (${p.key})`, draft.paragraphs[i], (v) => setDraft((d) => ({ paragraphs: d.paragraphs.map((x, j) => (j === i ? v : x)) })), PARAGRAPH_MAX, 4),
          )
        : content.sections.map((section, s) => (
            <fieldset key={section.key} className="flex flex-col gap-2">
              <legend className="text-sm font-semibold text-slate-800">{section.title}</legend>
              {section.items.map((item, i) =>
                area(
                  `edit-s${s}i${i}`,
                  `${item.heading || section.title} — one line per row`,
                  draft.items[s][i],
                  (v) => setDraft((d) => ({ items: d.items.map((sec, a) => (a === s ? sec.map((x, b) => (b === i ? v : x)) : sec)) })),
                  undefined,
                  Math.min(8, Math.max(2, draft.items[s][i].split("\n").length + 1)),
                ),
              )}
            </fieldset>
          ))}
      <ErrorAlert error={apiError} title="Your changes couldn't be saved" />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={saving}>
          {saving ? "Saving…" : "Save as new version"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
