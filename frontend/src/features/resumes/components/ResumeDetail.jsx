import Badge from "../../../components/ui/Badge";
import { formatDateTime } from "../../../utils/dates";
import { resumeStatus } from "../../dashboard/format";
import { CONTACT_FIELDS, entryLines, safeExternalUrl } from "../resumeData";

function Section({ title, count, children }) {
  return (
    <section className="border-t border-slate-100 pt-5">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        {title}
        {count != null && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{count}</span>}
      </h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function NotFound({ what }) {
  return <p className="text-sm text-slate-500">No {what} found in this resume.</p>;
}

function Entries({ items, what }) {
  if (!items?.length) return <NotFound what={what} />;
  return (
    <ol className="flex flex-col gap-3">
      {items.map((item, index) => {
        const { heading, lines } = entryLines(item);
        return (
          <li key={index} className="rounded-lg bg-slate-50 px-4 py-3">
            {heading && <p className="text-sm font-medium text-slate-900">{heading}</p>}
            {lines.length > 0 && (
              <ul className="mt-1 flex flex-col gap-0.5 text-sm text-slate-600">
                {lines.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Chips({ items, tone = "brand" }) {
  const cls = tone === "brand" ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-700";
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item} className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
          {item}
        </li>
      ))}
    </ul>
  );
}

function SimpleList({ items }) {
  return (
    <ul className="list-inside list-disc text-sm text-slate-700">
      {items.map((item, i) => (
        <li key={i}>{typeof item === "string" ? item : entryLines(item).heading}</li>
      ))}
    </ul>
  );
}

// Everything the backend extracted from one resume (ResumeDetailResponse). Nothing is invented:
// empty core sections say so, optional sections (certifications, languages, achievements) appear
// only when the parser found something.
export default function ResumeDetail({ detail }) {
  const data = detail.extracted_data || {};
  const status = resumeStatus(detail.status);
  const byCategory = (detail.normalized_skills || []).reduce((groups, skill) => {
    const key = skill.category || "other";
    (groups[key] ||= []).push(skill.name);
    return groups;
  }, {});
  const categories = Object.keys(byCategory).sort();

  return (
    <div className="flex flex-col gap-5">
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-slate-500">Status</dt>
          <dd className="mt-0.5">
            <Badge tone={status.tone}>{status.label}</Badge>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Uploaded</dt>
          <dd className="mt-0.5 text-slate-900">{formatDateTime(detail.uploaded_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">File type</dt>
          <dd className="mt-0.5 uppercase text-slate-900">{detail.file_type}</dd>
        </div>
      </dl>

      <Section title="Contact details">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          {CONTACT_FIELDS.map((field) => {
            const value = data[field.key];
            const href = field.link ? safeExternalUrl(value) : null;
            return (
              <div key={field.key} className="min-w-0">
                <dt className="text-xs text-slate-500">{field.label}</dt>
                <dd className="mt-0.5 break-words text-sm text-slate-900">
                  {!value ? (
                    <span className="text-slate-400">Not found</span>
                  ) : href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-700 underline-offset-2 hover:underline">
                      {value}
                    </a>
                  ) : (
                    value
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      </Section>

      {data.professional_summary && (
        <Section title="Summary">
          <p className="whitespace-pre-line text-sm text-slate-700">{data.professional_summary}</p>
        </Section>
      )}

      <Section title="Skills" count={(detail.normalized_skills || []).length}>
        {categories.length ? (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-slate-500">Recognised skills, used for matching and skill-gap analysis.</p>
            {categories.map((category) => (
              <div key={category}>
                <p className="mb-1.5 text-xs font-medium capitalize text-slate-600">{category.replace(/_/g, " ")}</p>
                <Chips items={byCategory[category]} />
              </div>
            ))}
          </div>
        ) : (
          <NotFound what="recognised skills" />
        )}
        {data.soft_skills?.length > 0 && (
          <div className="mt-3">
            <p className="mb-1.5 text-xs font-medium text-slate-600">Soft skills (as written)</p>
            <Chips items={data.soft_skills} tone="neutral" />
          </div>
        )}
      </Section>

      <Section title="Education" count={data.education?.length || 0}>
        <Entries items={data.education} what="education" />
      </Section>
      <Section title="Work experience" count={data.work_experience?.length || 0}>
        <Entries items={data.work_experience} what="work experience" />
      </Section>
      {data.internships?.length > 0 && (
        <Section title="Internships" count={data.internships.length}>
          <Entries items={data.internships} what="internships" />
        </Section>
      )}
      <Section title="Projects" count={data.projects?.length || 0}>
        <Entries items={data.projects} what="projects" />
      </Section>
      {data.certifications?.length > 0 && (
        <Section title="Certifications" count={data.certifications.length}>
          <SimpleList items={data.certifications} />
        </Section>
      )}
      {data.languages?.length > 0 && (
        <Section title="Languages">
          <Chips items={data.languages} tone="neutral" />
        </Section>
      )}
      {data.achievements?.length > 0 && (
        <Section title="Achievements" count={data.achievements.length}>
          <SimpleList items={data.achievements} />
        </Section>
      )}
    </div>
  );
}
