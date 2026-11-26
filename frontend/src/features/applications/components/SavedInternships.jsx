import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listBookmarks, removeBookmark, trackInternshipApplication } from "../../../api/applications";
import { errorMessage, normalizeError } from "../../../api/errors";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import Pagination from "../../../components/ui/Pagination";
import { useConfirm } from "../../../context/ConfirmContext";
import { useToast } from "../../../context/ToastContext";
import useApiResource from "../../../hooks/useApiResource";
import { formatDate } from "../../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";

// Saved internships (GET /applications/bookmarks), using the same bookmark and tracking calls as the
// internship page (F4).
export default function SavedInternships({ onChanged }) {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();
  const [skip, setSkip] = useState(0);
  const list = useApiResource(() => listBookmarks({ skip, limit: 20 }), `bookmarks:${skip}`);
  const [busy, setBusy] = useState(null); // internship_id while a request runs
  const [error, setError] = useState(null);

  const remove = async (b) => {
    const ok = await confirm({
      title: "Remove from saved internships?",
      message: `${b.internship.title} at ${b.internship.company} will no longer be saved. Any application you track for it is kept.`,
      confirmLabel: "Remove",
      tone: "danger",
    });
    if (!ok || busy) return;
    setBusy(b.internship_id);
    setError(null);
    try {
      await removeBookmark(b.internship_id);
      toast.success("Removed from saved internships.");
      list.reload();
      onChanged?.();
    } catch (failure) {
      setError({ id: b.internship_id, message: errorMessage(failure) });
    } finally {
      setBusy(null);
    }
  };

  const track = async (b) => {
    if (busy) return;
    setBusy(b.internship_id);
    setError(null);
    try {
      const created = await trackInternshipApplication(b.internship_id, "APPLIED");
      onChanged?.();
      navigate(`/applications/${created.application_id}`, { state: { created: true } });
    } catch (failure) {
      const err = normalizeError(failure);
      if (err.status === 409 && err.detail?.application_id) navigate(`/applications/${err.detail.application_id}`);
      else setError({ id: b.internship_id, message: err.message });
    } finally {
      setBusy(null);
    }
  };

  if ((list.status === "loading" || list.status === "idle") && !list.data) return <CardSkeleton label="your saved internships" lines={3} />;
  if (list.status === "error") return <CardError error={list.error} onRetry={list.reload} label="your saved internships" />;
  if (!list.data.items.length) {
    return (
      <CardEmpty
        title="No saved internships"
        message="Use “Save for later” on an internship to keep it here."
        action={<Link to="/internships" className="text-sm font-medium text-brand-700 hover:underline">Browse internships</Link>}
      />
    );
  }
  return (
    <>
      <ul className="flex flex-col gap-2" aria-label="Saved internships">
        {list.data.items.map((b) => {
          const i = b.internship;
          const closed = !i.is_active || i.deadline_passed;
          return (
            <li key={b.bookmark_id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <Link to={`/internships/${i.internship_id}`} className="font-medium text-slate-900 hover:underline">
                  {i.title}
                </Link>
                <p className="text-sm text-slate-600">{i.company}</p>
                <p className="text-xs text-slate-500">
                  {[i.location, i.work_mode, i.domain].filter(Boolean).join(" · ")}
                  {i.deadline ? ` · deadline ${formatDate(i.deadline)}` : ""} · saved {formatDate(b.created_at)}
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {!i.is_active && <Badge>No longer active</Badge>}
                  {i.is_active && i.deadline_passed && <Badge tone="warning">Deadline passed</Badge>}
                  {b.application_id && <Badge tone="info">Tracked</Badge>}
                </div>
                {error?.id === b.internship_id && (
                  <p role="alert" className="mt-1 text-sm text-red-700">
                    {error.message}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                {b.application_id ? (
                  <Link
                    to={`/applications/${b.application_id}`}
                    className="inline-flex items-center rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                  >
                    View application
                  </Link>
                ) : (
                  <Button variant="secondary" onClick={() => track(b)} loading={busy === b.internship_id} disabled={Boolean(busy) || closed} className="py-1.5" aria-label={`Mark ${i.title} at ${i.company} as applied`}>
                    Mark as applied
                  </Button>
                )}
                <Button variant="ghost" onClick={() => remove(b)} disabled={Boolean(busy)} className="py-1.5" aria-label={`Remove ${i.title} at ${i.company} from saved`}>
                  Remove
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
      <Pagination total={list.data.total} skip={list.data.skip} limit={list.data.limit} onChange={setSkip} />
    </>
  );
}
