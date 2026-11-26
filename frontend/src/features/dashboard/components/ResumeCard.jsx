import { Link } from "react-router-dom";
import Badge from "../../../components/ui/Badge";
import { useToast } from "../../../context/ToastContext";
import { formatDateTime } from "../../../utils/dates";
import ResumeUploader from "../../resumes/components/ResumeUploader";
import { latestParsed } from "../../resumes/resumeData";
import { resumeStatus } from "../format";
import DashboardCard, { CardEmpty, ResourceState } from "./DashboardCard";

export { validateResumeFile } from "../../resumes/resumeFile";

// Latest resume + quick upload. Matching and skill gaps use the latest successfully parsed resume.
export default function ResumeCard({ resumes, onUploaded }) {
  const toast = useToast();
  const handleUploaded = (uploaded) => {
    toast.success(`${uploaded.filename} uploaded and parsed.`);
    onUploaded?.(uploaded);
  };

  return (
    <DashboardCard title="Resume" icon="document" link="/resumes" linkLabel="Manage">
      <ResourceState resource={resumes} label="your resume" lines={2}>
        {(list) => {
          const latest = list?.[0];
          if (!latest) {
            return (
              <div className="flex flex-col gap-3">
                <CardEmpty
                  title="No resume yet"
                  message="Upload your resume to unlock internship matches, skill-gap insights and interview practice."
                />
                <ResumeUploader compact label="Upload resume" onUploaded={handleUploaded} />
              </div>
            );
          }
          const status = resumeStatus(latest.status);
          const used = latestParsed(list);
          return (
            <div className="flex flex-1 flex-col gap-4">
              <Link
                to={`/resumes/${latest.resume_id}`}
                className="flex items-start gap-3 rounded-xl bg-slate-50 p-3 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white text-xs font-semibold uppercase text-brand-700 ring-1 ring-slate-200">
                  {latest.file_type}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-slate-900" title={latest.filename}>
                    {latest.filename}
                  </span>
                  <span className="block text-xs text-slate-500">Uploaded {formatDateTime(latest.uploaded_at)}</span>
                </span>
                <Badge tone={status.tone}>{status.label}</Badge>
              </Link>
              {used && used.resume_id !== latest.resume_id && (
                <p className="text-xs text-slate-600">
                  Matching and skill gaps use <span className="font-medium">{used.filename}</span>, your latest successfully parsed resume.
                </p>
              )}
              {!used && <p className="text-sm text-red-700">None of your resumes could be read. Upload a new PDF, DOCX or ODT version.</p>}
              <p className="text-xs text-slate-500">
                {list.length} resume{list.length === 1 ? "" : "s"} on file.
              </p>
              <div className="mt-auto">
                <ResumeUploader compact label="Upload new version" onUploaded={handleUploaded} />
              </div>
            </div>
          );
        }}
      </ResourceState>
    </DashboardCard>
  );
}
