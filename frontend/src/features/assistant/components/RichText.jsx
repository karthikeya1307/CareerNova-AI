// Light formatting for assistant answers: "## " headings, "- " / "  - " bullets, "1. " numbered lines and
// **bold** spans. Everything is rendered as text (no HTML from the backend is ever injected).
function Inline({ text }) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export function blocks(content) {
  const out = [];
  for (const raw of String(content ?? "").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (line.startsWith("## ")) out.push({ type: "heading", text: line.slice(3) });
    else if (/^ {2,}- /.test(line)) out.push({ type: "bullet", level: 2, text: line.replace(/^ +- /, "") });
    else if (line.startsWith("- ") || line.startsWith("* ")) out.push({ type: "bullet", level: 1, text: line.slice(2) });
    else if (/^\d{1,2}\. /.test(line)) out.push({ type: "numbered", number: line.match(/^(\d{1,2})\./)[1], text: line.replace(/^\d{1,2}\. /, "") });
    else out.push({ type: "text", text: line });
  }
  return out;
}

export default function RichText({ content, inverted = false }) {
  return (
    <div className="flex flex-col gap-1 break-words text-sm leading-relaxed">
      {blocks(content).map((b, i) => {
        if (b.type === "heading")
          return (
            <p key={i} className={`mt-2 font-display text-[13px] font-bold ${inverted ? "text-white" : "text-brand-700"}`}>
              {b.text}
            </p>
          );
        if (b.type === "bullet")
          return (
            <p key={i} className={`flex gap-2 ${b.level === 2 ? "pl-5" : "pl-1"}`}>
              <span aria-hidden="true" className={inverted ? "text-brand-100" : "text-brand-500"}>
                •
              </span>
              <span className="min-w-0">
                <Inline text={b.text} />
              </span>
            </p>
          );
        if (b.type === "numbered")
          return (
            <p key={i} className="flex gap-2 pl-1">
              <span className={`min-w-[1.25rem] font-semibold tabular-nums ${inverted ? "text-brand-100" : "text-brand-700"}`}>{b.number}.</span>
              <span className="min-w-0">
                <Inline text={b.text} />
              </span>
            </p>
          );
        return (
          <p key={i}>
            <Inline text={b.text} />
          </p>
        );
      })}
    </div>
  );
}
