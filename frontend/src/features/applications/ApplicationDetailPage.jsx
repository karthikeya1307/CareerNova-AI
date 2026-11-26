import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { getApplication, getHistory, moveToTrash } from "../../api/applications";
import { errorMessage } from "../../api/errors";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Icon from "../../components/ui/Icon";
import { useConfirm } from "../../context/ConfirmContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDate, formatDateTime } from "../../utils/dates";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import { documentTypeLabel } from "../documents/documentFormat";
import { modeLabel, sessionStatus } from "../interviews/interviewFormat";
import ApplicationReminders from "./components/ApplicationReminders";
import DetailsEditor from "./components/DetailsEditor";
import HistoryTimeline from "./components/HistoryTimeline";
import InterviewRounds from "./components/InterviewRounds";
import StatusControl from "./components/StatusControl";
import { safeExternalUrl } from "../resumes/resumeData";
import { applicationStatus } from "./applicationFormat";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

function Field({ label, children }) {
  if (children == null || children === "") return null;
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="break-words text-sm text-slate-900">{children}</dd>
    </div>
  );
}

// Read-only links the backend returns in ApplicationOut.related (detail view only).
function Related({ application: a }) {
  const r = a.related || {};
  const hasAny = r.latest_match || r.documents?.length || r.practice_sessions?.length || a.internship_id;
  if (!hasAny) return null;
  return (
    <section aria-labelledby="related-title" className={`${panel} flex flex-col gap-3`}>
      <h2 id="related-title" className="text-base font-semibold text-slate-900">
        Related
      </h2>
      {r.latest_match && (
        <p className="text-sm text-slate-700">
          Latest match: <span className="font-medium">{Math.round(r.latest_match.score)}%</span> ({r.latest_match.label}) ·{" "}
          <Link to="/matches" className="text-brand-700 hover:underline">
            Matches
          </Link>
        </p>
      )}
      {r.documents?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">Documents linked to this application</p>
          <ul className="mt-1 flex flex-col gap-1 text-sm" aria-label="Linked documents">
            {r.documents.map((d) => (
              <li key={d.document_id}>
                <Link to={`/documents/${d.document_id}`} className="text-brand-700 hover:underline">
                  {d.title || documentTypeLabel(d.document_type)}
                </Link>{" "}
                <span className="text-xs text-slate-500">
                  ({documentTypeLabel(d.document_type)}, version {d.current_version})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.practice_sessions?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-slate-500">Interview practice for this internship</p>
          <ul className="mt-1 flex flex-col gap-1 text-sm" aria-label="Practice sessions">
            {r.practice_sessions.map((s) => (
              <li key={s.session_id}>
                <Link to={`/interview-prep/sessions/${s.session_id}`} className="text-brand-700 hover:underline">
                  {s.title || `${modeLabel(s.mode)} #${s.session_id}`}
                </Link>{" "}
                <span className="text-xs text-slate-500">
                  {sessionStatus(s.status).label}
                  {s.score != null ? ` · ${s.score}/100` : ""} · {formatDate(s.started_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {a.internship_id && (
        <div className="flex flex-wrap gap-3 text-sm">
          <Link to={`/interview-prep?internship=${a.internship_id}`} className="font-medium text-brand-700 hover:underline">
            Practise interview questions
          </Link>
          <Link to={`/documents?type=resume&internship=${a.internship_id}`} className="font-medium text-brand-700 hover:underline">
            Tailor my resume
          </Link>
        </div>
      )}
    </section>
  );
}

export default function ApplicationDetailPage() {
  const { applicationId } = useParams();
  const id = Number(applicationId);
  const navigate = useNavigate();
  const location = useLocation();
  const confirm = useConfirm();
  const toast = useToast();
  const valid = Number.isInteger(id) && id > 0;
  const app = useApiResource(() => getApplication(id), `application:${id}`, { enabled: valid });
  const history = useApiResource(() => getHistory(id), `application-history:${id}`, { enabled: valid });
  const [editing, setEditing] = useState(false);
  const [trashing, setTrashing] = useState(false);
  const [actionError, setActionError] = useState(null);

  const a = app.data;
  useEffect(() => {
    if (!a) return undefined;
    const previous = document.title;
    document.title = `${a.title} · Applications · CareerNova AI`;
    return () => {
      document.title = previous;
    };
  }, [a]);

  const refresh = () => {
    app.reload();
    history.reload();
  };

  const trash = async () => {
    const ok = await confirm({
      title: "Move this application to the trash?",
      message: "You can restore it from the Trash tab. To record that you stopped pursuing it, change the status to Withdrawn instead.",
      confirmLabel: "Move to trash",
      tone: "danger",
    });
    if (!ok || trashing) return;
    setTrashing(true);
    setActionError(null);
    try {
      await moveToTrash(id);
      toast.success("Moved to the trash.");
      navigate("/applications?tab=trash", { replace: true });
    } catch (failure) {
      setActionError(errorMessage(failure));
      setTrashing(false);
    }
  };

  const back = (
    <Link to="/applications" className="inline-flex w-fit items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
      <Icon name="arrowRight" className="h-4 w-4 rotate-180" />
      All applications
    </Link>
  );

  if (!valid || (app.status === "error" && app.error?.status === 404)) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {back}
        <div className={panel}>
          <CardEmpty title="Application not found" message="It doesn't exist, belongs to another account, or is in the trash (restore it from the Trash tab)." />
        </div>
      </div>
    );
  }
  if (!a) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {back}
        <div className={panel}>
          {app.status === "error" ? <CardError error={app.error} onRetry={app.reload} label="the application" /> : <CardSkeleton label="the application" lines={6} />}
        </div>
      </div>
    );
  }

  const st = applicationStatus(a.status);
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {back}
      <header className={`${panel} flex flex-col gap-3`}>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={st.tone}>{st.label}</Badge>
          <Badge>{a.source === "external" ? "Added manually" : "From the internship catalogue"}</Badge>
          {a.internship_active === false && <Badge>Internship no longer active</Badge>}
          {a.deadline_passed && <Badge>Deadline passed</Badge>}
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">{a.title}</h1>
          <p className="text-slate-600">{a.company_name}</p>
        </div>
        <p className="text-xs text-slate-500">
          {a.applied_at ? `Applied ${formatDateTime(a.applied_at)} · ` : ""}Status since {formatDateTime(a.status_changed_at)} · added {formatDate(a.created_at)}
        </p>
        {location.state?.created && (
          <p role="status" className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-800">
            Application added. Update its status as you hear back.
          </p>
        )}
        {a.possible_duplicates?.length > 0 && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
            You may already track this opening:{" "}
            {a.possible_duplicates.map((d, i) => (
              <span key={d}>
                {i ? ", " : ""}
                <Link to={`/applications/${d}`} className="font-medium underline">
                  application #{d}
                </Link>
              </span>
            ))}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {a.internship_id && (
            <Link
              to={`/internships/${a.internship_id}`}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
            >
              <Icon name="briefcase" className="h-4 w-4" />
              View internship
            </Link>
          )}
          <Button variant="danger" onClick={trash} loading={trashing}>
            Move to trash
          </Button>
        </div>
        {actionError && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            {actionError}
          </p>
        )}
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex min-w-0 flex-col gap-6">
          <div className={panel}>
            <StatusControl application={a} history={history.data} onChanged={(result) => { app.setData({ ...a, ...result.application, related: a.related }); refresh(); }} onConflict={refresh} />
          </div>
          <div className={panel}>
            <InterviewRounds application={a} onStatusChange={refresh} />
          </div>
          <div className={panel}>
            <section aria-labelledby="history-title">
              <h2 id="history-title" className="mb-3 text-base font-semibold text-slate-900">
                History
              </h2>
              <HistoryTimeline history={history} />
            </section>
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          <div className={panel}>
            <section aria-labelledby="details-title" className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2">
                <h2 id="details-title" className="text-base font-semibold text-slate-900">
                  Details
                </h2>
                {!editing && (
                  <Button variant="secondary" onClick={() => setEditing(true)} className="py-1.5">
                    Edit
                  </Button>
                )}
              </div>
              {editing ? (
                <DetailsEditor
                  application={a}
                  onCancel={() => setEditing(false)}
                  onSaved={(updated) => {
                    app.setData(updated);
                    setEditing(false);
                    toast.success("Details saved.");
                    history.reload();
                  }}
                />
              ) : (
                <dl className="flex flex-col gap-2">
                  <Field label="Location">{[a.location, a.work_mode].filter(Boolean).join(" · ")}</Field>
                  <Field label="Domain">{a.domain}</Field>
                  <Field label="Application link">
                    {safeExternalUrl(a.application_url) ? (
                      <a href={safeExternalUrl(a.application_url)} target="_blank" rel="noopener noreferrer" className="break-all text-brand-700 hover:underline">
                        {a.application_url}
                      </a>
                    ) : (
                      // Not an http(s) link: show the stored text, never a clickable link.
                      a.application_url || null
                    )}
                  </Field>
                  <Field label="Reference">{a.external_reference}</Field>
                  <Field label="Contact">{[a.contact_name, a.contact_email].filter(Boolean).join(" · ")}</Field>
                  <Field label="Notes">{a.notes ? <span className="whitespace-pre-line">{a.notes}</span> : null}</Field>
                  {!a.notes && !a.contact_name && !a.contact_email && <p className="text-sm text-slate-500">No notes or contact yet.</p>}
                </dl>
              )}
            </section>
          </div>
          <div className={panel}>
            <ApplicationReminders applicationId={a.application_id} onChanged={app.reload} />
          </div>
          <Related application={a} />
        </div>
      </div>
    </div>
  );
}
