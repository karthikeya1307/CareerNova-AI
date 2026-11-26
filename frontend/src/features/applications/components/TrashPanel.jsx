import { useState } from "react";
import { deletePermanently, listTrash, restoreApplication } from "../../../api/applications";
import { errorMessage } from "../../../api/errors";
import Badge from "../../../components/ui/Badge";
import Button from "../../../components/ui/Button";
import Pagination from "../../../components/ui/Pagination";
import { useConfirm } from "../../../context/ConfirmContext";
import { useToast } from "../../../context/ToastContext";
import useApiResource from "../../../hooks/useApiResource";
import { formatDateTime } from "../../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../../dashboard/components/DashboardCard";
import { applicationStatus } from "../applicationFormat";

// Applications in the trash (GET /applications/trash): restore, or delete permanently.
export default function TrashPanel({ onChanged }) {
  const confirm = useConfirm();
  const toast = useToast();
  const [skip, setSkip] = useState(0);
  const list = useApiResource(() => listTrash({ skip, limit: 20 }), `trash:${skip}`);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const run = async (id, task, message) => {
    if (busy) return;
    setBusy(id);
    setError(null);
    try {
      await task();
      toast.success(message);
      list.reload();
      onChanged?.();
    } catch (failure) {
      setError({ id, message: errorMessage(failure) });
    } finally {
      setBusy(null);
    }
  };
  const purge = async (a) => {
    const ok = await confirm({
      title: `Delete ${a.title} permanently?`,
      message: "This deletes the application with its status history, interview rounds and reminders. This cannot be undone.",
      confirmLabel: "Delete permanently",
      tone: "danger",
      requireText: "DELETE",
    });
    if (ok) await run(a.application_id, () => deletePermanently(a.application_id), "Application deleted permanently.");
  };

  if ((list.status === "loading" || list.status === "idle") && !list.data) return <CardSkeleton label="the trash" lines={3} />;
  if (list.status === "error") return <CardError error={list.error} onRetry={list.reload} label="the trash" />;
  if (!list.data.items.length) return <CardEmpty title="The trash is empty" message="Applications you move to the trash appear here until you restore or delete them." />;
  return (
    <>
      <ul className="flex flex-col gap-2" aria-label="Applications in the trash">
        {list.data.items.map((a) => {
          const st = applicationStatus(a.status);
          return (
            <li key={a.application_id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{a.title}</p>
                <p className="text-sm text-slate-600">{a.company_name}</p>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                  <Badge tone={st.tone}>{st.label}</Badge> Moved to the trash {formatDateTime(a.deleted_at)}
                </p>
                {error?.id === a.application_id && (
                  <p role="alert" className="mt-1 text-sm text-red-700">
                    {error.message}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  variant="secondary"
                  onClick={() => run(a.application_id, () => restoreApplication(a.application_id), "Application restored.")}
                  loading={busy === a.application_id}
                  disabled={Boolean(busy)}
                  className="py-1.5"
                  aria-label={`Restore ${a.title} at ${a.company_name}`}
                >
                  Restore
                </Button>
                <Button variant="danger" onClick={() => purge(a)} disabled={Boolean(busy)} className="py-1.5" aria-label={`Delete ${a.title} at ${a.company_name} permanently`}>
                  Delete permanently
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
