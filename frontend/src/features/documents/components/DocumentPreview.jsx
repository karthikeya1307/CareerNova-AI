// Renders a document's structured content (content_json) exactly as stored. Items and paragraphs that
// carry fact_ids are linked by the backend to facts on the student's resume.
function FromResume({ ids }) {
  if (!ids?.length) return null;
  return (
    <span className="ml-2 inline-flex rounded-full bg-mint-50 px-2 py-0.5 align-middle text-[11px] font-medium text-mint-700" title={`Linked to resume facts: ${ids.join(", ")}`}>
      From your resume
    </span>
  );
}

function Header({ header }) {
  const contact = [header.email, header.phone, header.location, header.linkedin, header.github].filter(Boolean);
  return (
    <div className="border-b border-slate-200 pb-4 text-center">
      {header.name && <p className="text-xl font-semibold text-slate-900">{header.name}</p>}
      {contact.length > 0 && <p className="mt-1 break-words text-xs text-slate-600">{contact.join(" · ")}</p>}
      {header.target && <p className="mt-2 text-sm font-medium text-brand-700">{header.target}</p>}
    </div>
  );
}

export default function DocumentPreview({ document: doc }) {
  const content = doc.content_json;
  if (!content) {
    return <pre className="whitespace-pre-wrap break-words font-sans text-sm text-slate-800">{doc.content}</pre>;
  }
  if (content.type === "cover_letter") {
    return (
      <article aria-label="Cover letter preview" className="flex flex-col gap-4 text-sm leading-relaxed text-slate-800">
        <Header header={content.header || {}} />
        {(content.recipient?.company || content.recipient?.title) && (
          <p className="text-slate-600">
            {[content.recipient.title, content.recipient.company].filter(Boolean).join(" · ")}
          </p>
        )}
        {content.paragraphs.map((p) => (
          <p key={p.key} className="whitespace-pre-line">
            {p.text}
            <FromResume ids={p.fact_ids} />
          </p>
        ))}
        <div>
          <p>{content.signoff}</p>
          {content.signature && <p className="font-medium">{content.signature}</p>}
        </div>
      </article>
    );
  }
  return (
    <article aria-label="Resume preview" className="flex flex-col gap-5 text-sm text-slate-800">
      <Header header={content.header || {}} />
      {content.sections.map((section) => (
        <section key={section.key} aria-label={section.title}>
          <h3 className="border-b border-slate-100 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{section.title}</h3>
          <ul className="mt-2 flex flex-col gap-2.5">
            {section.items.map((item, i) => (
              <li key={i}>
                {item.heading && (
                  <p className="font-medium text-slate-900">
                    {item.heading}
                    <FromResume ids={item.fact_ids} />
                  </p>
                )}
                {item.lines?.length > 0 && (
                  <ul className={`${item.heading ? "mt-0.5 list-disc pl-5" : ""} text-slate-700`}>
                    {item.lines.map((line, j) => (
                      <li key={j}>
                        {line}
                        {!item.heading && j === 0 && <FromResume ids={item.fact_ids} />}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </article>
  );
}
