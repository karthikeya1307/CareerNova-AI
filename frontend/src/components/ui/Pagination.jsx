import Button from "./Button";

// For backend lists shaped { total, skip, limit, items }.
export default function Pagination({ total, skip, limit, onChange }) {
  if (!total || total <= limit) return null;
  const page = Math.floor(skip / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-4 pt-4 text-sm text-slate-600">
      <span>
        Page {page} of {pages} ({total} total)
      </span>
      <div className="flex gap-2">
        <Button variant="secondary" disabled={page <= 1} onClick={() => onChange(Math.max(0, skip - limit))}>
          Previous
        </Button>
        <Button variant="secondary" disabled={page >= pages} onClick={() => onChange(skip + limit)}>
          Next
        </Button>
      </div>
    </nav>
  );
}
