import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listCareerTracks } from "../../api/careerTracks";
import { compareResumes, listResumes, versionName } from "../../api/resumes";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import Select from "../../components/ui/Select";
import useApiResource from "../../hooks/useApiResource";
import { formatDate } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card";
const STATUS = {
  added: { tone: "success", label: "Added" },
  removed: { tone: "danger", label: "Removed" },
  modified: { tone: "warning", label: "Modified" },
  unchanged: { tone: "neutral", label: "Unchanged" },
  missing_in_both: { tone: "neutral", label: "Missing in both" },
};
const toId = (v) => (/^\d+$/.test(String(v ?? "")) ? Number(v) : null);

function Chips({ items, tone, label }) {
  if (!items?.length) return <p className="text-xs text-slate-400">None</p>;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label={label}>
      {items.map((s) => (
        <li key={s}>
          <Badge tone={tone}>{s}</Badge>
        </li>
      ))}
    </ul>
  );
}

function Delta({ value }) {
  if (value == null) return <span className="text-slate-400">—</span>;
  const cls = value > 0 ? "text-mint-700" : value < 0 ? "text-red-700" : "text-slate-500";
  return <span className={`font-semibold tabular-nums ${cls}`}>{value > 0 ? `+${value}` : value}</span>;
}

function Bullets({ items, label, empty }) {
  if (!items?.length) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <ul className="flex flex-col gap-1.5 text-sm text-slate-700" aria-label={label}>
      {items.map((t, i) => (
        <li key={i} className="flex gap-2">
          <span aria-hidden="true" className="text-brand-500">•</span>
          <span className="min-w-0">{t}</span>
        </li>
      ))}
    </ul>
  );
}

function Result({ c }) {
  const nameA = `A · ${c.a.label || c.a.filename}`;
  const nameB = `B · ${c.b.label || c.b.filename}`;
  const stronger = c.verdict.stronger;
  const m = c.metrics;
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="verdict-title" className={`${panel} border-brand-200 bg-gradient-to-br from-white to-brand-50/50`}>
        <h2 id="verdict-title" className="flex items-center gap-2 text-lg font-bold text-slate-900">
          <Icon name="target" className="h-5 w-5 text-brand-600" />
          {c.verdict.headline}
        </h2>
        <p className="mt-1 text-xs text-slate-500">Based on {c.verdict.basis}.</p>
        {c.verdict.reasons.length > 0 && (
          <div className="mt-3">
            <p className="text-sm font-semibold text-slate-800">Why {stronger ? `version ${stronger.toUpperCase()}` : "they are close"}:</p>
            <Bullets items={c.verdict.reasons} label="Reasons" />
          </div>
        )}
      </section>

      <section aria-labelledby="metrics-title" className={panel}>
        <h2 id="metrics-title" className="text-base font-semibold text-slate-900">Measured metrics</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left text-sm">
            <caption className="sr-only">Scores for version A and version B</caption>
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="py-2 pr-3">Metric</th>
                <th scope="col" className="py-2 pr-3">A</th>
                <th scope="col" className="py-2 pr-3">B</th>
                <th scope="col" className="py-2">Change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr className="font-semibold">
                <th scope="row" className="py-2 pr-3">Resume readiness ({m.readiness.algorithm})</th>
                <td className="py-2 pr-3 tabular-nums">{m.readiness.a}/100</td>
                <td className="py-2 pr-3 tabular-nums">{m.readiness.b}/100</td>
                <td className="py-2"><Delta value={m.readiness.change} /></td>
              </tr>
              {m.readiness.categories.map((cat) => (
                <tr key={cat.key}>
                  <th scope="row" className="py-1.5 pl-3 pr-3 font-normal text-slate-600">{cat.label}</th>
                  <td className="py-1.5 pr-3 tabular-nums">{cat.a}/{cat.max}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{cat.b}/{cat.max}</td>
                  <td className="py-1.5"><Delta value={cat.change} /></td>
                </tr>
              ))}
              {m.role && (
                <tr className="font-semibold">
                  <th scope="row" className="py-2 pr-3">{m.role.title} fit ({m.role.algorithm})</th>
                  <td className="py-2 pr-3 tabular-nums">{m.role.a}/100</td>
                  <td className="py-2 pr-3 tabular-nums">{m.role.b}/100</td>
                  <td className="py-2"><Delta value={m.role.change} /></td>
                </tr>
              )}
              {m.ats && (
                <>
                  <tr className="font-semibold">
                    <th scope="row" className="py-2 pr-3">ATS: required keywords for {m.ats.title}</th>
                    <td className="py-2 pr-3 tabular-nums">{m.ats.a.required.present}/{m.ats.a.required.total}</td>
                    <td className="py-2 pr-3 tabular-nums">{m.ats.b.required.present}/{m.ats.b.required.total}</td>
                    <td className="py-2"><Delta value={m.ats.b.required.present - m.ats.a.required.present} /></td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1.5 pl-3 pr-3 font-normal text-slate-600">ATS checks passed</th>
                    <td className="py-1.5 pr-3 tabular-nums">{m.ats.a.checks_passed}/{m.ats.a.checks_total}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{m.ats.b.checks_passed}/{m.ats.b.checks_total}</td>
                    <td className="py-1.5"><Delta value={m.ats.b.checks_passed - m.ats.a.checks_passed} /></td>
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>
        {!m.ats && <p className="mt-2 text-xs text-slate-500">Choose an internship above to compare ATS keyword coverage for that job.</p>}
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section aria-labelledby="skills-title" className={panel}>
          <h2 id="skills-title" className="text-base font-semibold text-slate-900">
            Skills <span className="text-sm font-normal text-slate-500">({c.skills.count.a} → {c.skills.count.b})</span>
          </h2>
          {[["technical", "Technical"], ["soft", "Soft skills"]].map(([key, label]) => (
            <div key={key} className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div><p className="mb-1 text-xs font-semibold text-mint-700">{label} added in B</p><Chips items={c.skills[key].added} tone="success" label={`${label} added`} /></div>
              <div><p className="mb-1 text-xs font-semibold text-red-700">{label} removed in B</p><Chips items={c.skills[key].removed} tone="danger" label={`${label} removed`} /></div>
              <div><p className="mb-1 text-xs font-semibold text-slate-500">In both</p><Chips items={c.skills[key].kept} tone="neutral" label={`${label} in both`} /></div>
            </div>
          ))}
          <div className="mt-4 border-t border-slate-100 pt-3">
            <p className="text-xs font-semibold text-slate-600">Keywords (skills found anywhere in the resume)</p>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div><p className="mb-1 text-xs text-slate-500">New in B</p><Chips items={c.keywords.added} tone="success" label="Keywords added" /></div>
              <div><p className="mb-1 text-xs text-slate-500">Gone in B</p><Chips items={c.keywords.removed} tone="danger" label="Keywords removed" /></div>
              <div><p className="mb-1 text-xs text-slate-500">Now backed by a project or job</p><Chips items={c.keywords.now_backed_by_evidence} tone="info" label="Newly evidenced" /></div>
              <div><p className="mb-1 text-xs text-slate-500">No longer backed by evidence</p><Chips items={c.keywords.lost_evidence} tone="warning" label="Lost evidence" /></div>
            </div>
          </div>
        </section>

        <section aria-labelledby="contact-title" className={panel}>
          <h2 id="contact-title" className="text-base font-semibold text-slate-900">Contact and profile</h2>
          <ul className="mt-3 flex flex-col divide-y divide-slate-100 text-sm" aria-label="Contact fields">
            {c.contact.map((f) => (
              <li key={f.field} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="font-medium text-slate-700">{f.label}</span>
                <Badge tone={STATUS[f.status].tone}>{STATUS[f.status].label}</Badge>
              </li>
            ))}
            <li className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="font-medium text-slate-700">Professional summary</span>
              <Badge tone={STATUS[c.summary].tone}>{STATUS[c.summary].label}</Badge>
            </li>
          </ul>
        </section>
      </div>

      <section aria-labelledby="sections-title" className={panel}>
        <h2 id="sections-title" className="text-base font-semibold text-slate-900">Section by section</h2>
        <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Object.entries(c.sections).map(([key, s]) => (
            <div key={key} className="rounded-xl border border-slate-200 p-3">
              <h3 className="text-sm font-semibold text-slate-900">{s.label}</h3>
              <ul className="mt-2 flex flex-col gap-1.5 text-xs" aria-label={`${s.label} changes`}>
                {s.added.map((t) => <li key={`a${t}`}><Badge tone="success">Added</Badge> <span className="text-slate-700">{t}</span></li>)}
                {s.removed.map((t) => <li key={`r${t}`}><Badge tone="danger">Removed</Badge> <span className="text-slate-700">{t}</span></li>)}
                {s.modified.map((x) => (
                  <li key={`m${x.title}`}>
                    <Badge tone="warning">Modified</Badge> <span className="font-medium text-slate-800">{x.title}</span>
                    {x.lines_added.map((l) => <p key={`+${l}`} className="ml-3 text-mint-700">+ {l}</p>)}
                    {x.lines_removed.map((l) => <p key={`-${l}`} className="ml-3 text-red-700">− {l}</p>)}
                  </li>
                ))}
                {s.unchanged.length > 0 && <li className="text-slate-500">{s.unchanged.length} unchanged</li>}
                {!s.added.length && !s.removed.length && !s.modified.length && !s.unchanged.length && <li className="text-slate-400">Not in either version</li>}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section aria-labelledby="improved-title" className={panel}>
          <h2 id="improved-title" className="text-base font-semibold text-mint-700">Improvements in B</h2>
          <Bullets items={c.improvements_in_b} label="Improvements" empty="No measured improvements in version B." />
        </section>
        <section aria-labelledby="weak-title" className={panel}>
          <h2 id="weak-title" className="text-base font-semibold text-red-700">Weaknesses introduced in B</h2>
          <Bullets items={c.weaknesses_introduced_in_b} label="Weaknesses introduced" empty="Nothing was lost in version B." />
        </section>
        <section aria-labelledby="recs-title" className={panel}>
          <h2 id="recs-title" className="text-base font-semibold text-slate-900">
            How to improve {stronger ? `version ${stronger === "a" ? "B" : "A"}` : "the lower-scoring version"}
          </h2>
          <Bullets items={[...c.recommendations_for_weaker, ...c.role_advice]} label="Recommendations" empty="No recommendations." />
        </section>
      </div>
      <ul className="flex flex-col gap-1 text-xs text-slate-500" aria-label="Notes">
        {c.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
      <p className="sr-only">Comparing {nameA} with {nameB}.</p>
    </div>
  );
}

// Compare two of the student's resume versions (/resumes/compare?a=&b=&role=).
export default function ResumeComparePage() {
  const [params, setParams] = useSearchParams();
  const resumes = useApiResource(listResumes, "resumes");
  const tracks = useApiResource(listCareerTracks, "career-tracks");
  const list = resumes.data || [];
  const parsed = list.filter((r) => r.status === "completed");
  const [form, setForm] = useState({ a: params.get("a") || "", b: params.get("b") || "", role: params.get("role") || "" });
  const a = toId(params.get("a"));
  const b = toId(params.get("b"));
  const role = /^[a-z0-9-]+$/.test(params.get("role") || "") ? params.get("role") : null;
  const ready = a && b && a !== b;
  const result = useApiResource(() => compareResumes({ a, b, role }), `compare:${a}:${b}:${role}`, { enabled: Boolean(ready) });

  useEffect(() => {
    const previous = document.title;
    document.title = "Compare resumes · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  // Default selection: the two newest parsed versions (older as A, newer as B).
  useEffect(() => {
    if (!form.a && !form.b && parsed.length >= 2) setForm((f) => ({ ...f, a: String(parsed[1].resume_id), b: String(parsed[0].resume_id) }));
  }, [parsed.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = (event) => {
    event.preventDefault();
    const next = new URLSearchParams();
    next.set("a", form.a);
    next.set("b", form.b);
    if (form.role) next.set("role", form.role);
    setParams(next);
  };
  const options = parsed.map((r) => ({ value: String(r.resume_id), label: `${versionName(r)} · ${formatDate(r.uploaded_at)}` }));

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/resumes" className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
            <Icon name="arrowRight" className="h-4 w-4 rotate-180" /> Resumes
          </Link>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Compare resume versions</h1>
          <p className="mt-1 text-sm text-slate-600">Every difference comes from what was extracted from the two files, and both versions are scored the same way.</p>
        </div>
      </header>

      <section aria-label="Choose versions" className={panel}>
        {resumes.status === "loading" || resumes.status === "idle" ? (
          <CardSkeleton label="your resumes" lines={2} />
        ) : resumes.status === "error" ? (
          <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />
        ) : parsed.length < 2 ? (
          <CardEmpty title="Upload at least two resumes" message="Comparison needs two successfully parsed versions." action={<Link to="/resumes" className="text-sm font-semibold text-brand-700 hover:underline">Go to resumes</Link>} />
        ) : (
          <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] xl:items-end [&>*]:min-w-0" aria-label="Compare two versions">
            <Select label="Version A (earlier)" value={form.a} onChange={(e) => setForm({ ...form, a: e.target.value })} options={[{ value: "", label: "Choose…" }, ...options]} />
            <Select label="Version B (later)" value={form.b} onChange={(e) => setForm({ ...form, b: e.target.value })} options={[{ value: "", label: "Choose…" }, ...options]} />
            <Select
              label="For a role (optional)"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              options={[{ value: "", label: "No specific role" }, ...(tracks.data || []).map((t) => ({ value: t.slug, label: t.title }))]}
            />
            <Button type="submit" disabled={!form.a || !form.b || form.a === form.b}>
              <Icon name="refresh" className="h-4 w-4" />
              Compare
            </Button>
            {form.a && form.a === form.b && <p role="alert" className="text-xs text-red-700 sm:col-span-2 xl:col-span-4">Choose two different versions.</p>}
          </form>
        )}
      </section>

      {ready && (result.status === "loading" || result.status === "idle") && <div className={panel}><CardSkeleton label="the comparison" lines={6} /></div>}
      {ready && result.status === "error" && <div className={panel}><CardError error={result.error} onRetry={result.reload} label="the comparison" /></div>}
      {ready && result.status === "success" && <Result c={result.data} />}
    </div>
  );
}
