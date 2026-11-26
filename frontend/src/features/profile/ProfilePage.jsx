import { useEffect, useState } from "react";
import BioEditor from "./components/BioEditor";
import ProfilePhoto from "./components/ProfilePhoto";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/errors";
import { createProfile, getProfile, PROFILE_LIMITS, updateProfile } from "../../api/profile";
import { getResumeDetail, listResumes } from "../../api/resumes";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Icon from "../../components/ui/Icon";
import Input from "../../components/ui/Input";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import useApiResource from "../../hooks/useApiResource";
import { formatDate } from "../../utils/dates";
import useAuthForm from "../auth/useAuthForm";
import { CardEmpty, CardError, CardSkeleton } from "../dashboard/components/DashboardCard";
import ScoreRing from "../dashboard/components/ScoreRing";
import { entryLines, latestParsed } from "../resumes/resumeData";
import { changedFields, completeness, toApiValues, toFormValues, validateProfile } from "./profileForm";

const panel = "rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card sm:p-6";

function PanelTitle({ id, children, hint }) {
  return (
    <div className="mb-4">
      <h2 id={id} className="text-base font-semibold text-slate-900">
        {children}
      </h2>
      {hint && <p className="mt-0.5 text-sm text-slate-600">{hint}</p>}
    </div>
  );
}

function Completeness({ user, profile, parsed }) {
  const result = completeness({ user, profile, hasParsedResume: Boolean(parsed) });
  return (
    <section aria-labelledby="completeness-title" className={panel}>
      <PanelTitle id="completeness-title" hint={`Based on ${result.total} items from your account, profile and resumes.`}>
        Profile completeness
      </PanelTitle>
      <div className="flex flex-col items-start gap-5 sm:flex-row sm:items-center">
        <ScoreRing value={result.percent} label="profile complete" />
        <ul className="grid flex-1 grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2" aria-label="Completeness checklist">
          {result.items.map((item) => (
            <li key={item.id} className={`flex items-center gap-2 ${item.done ? "text-slate-800" : "text-slate-500"}`}>
              <span
                aria-hidden="true"
                className={`flex h-5 w-5 items-center justify-center rounded-full ${item.done ? "bg-mint-100 text-mint-700" : "bg-slate-100 text-slate-400"}`}
              >
                <Icon name={item.done ? "check" : "close"} className="h-3 w-3" />
              </span>
              {item.label}
              <span className="sr-only">{item.done ? " (complete)" : " (missing)"}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function AccountDetails({ user }) {
  const rows = [
    ["Name", `${user?.first_name || ""} ${user?.last_name || ""}`.trim() || "—"],
    ["Email", user?.email || "—"],
    ["Phone", user?.phone_number || "—"],
    ["Member since", user?.created_at ? formatDate(user.created_at) : "—"],
  ];
  return (
    <section aria-labelledby="account-title" className={panel}>
      <PanelTitle id="account-title" hint="From your account. These details can't be edited here yet.">
        Account details
      </PanelTitle>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="mt-0.5 flex flex-wrap items-center gap-2 break-words text-slate-900">
              {value}
              {label === "Email" && user?.is_verified && <Badge tone="success">Verified</Badge>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// Manually entered academic profile (POST /profiles/ when none exists, PATCH /profiles/me after).
function ProfileForm({ profile, onSaved, suggestion }) {
  const toast = useToast();
  const exists = Boolean(profile);
  const form = useAuthForm(toFormValues(profile), validateProfile);
  const changes = changedFields(form.values, profile);
  const dirty = Object.keys(changes).length > 0;

  // Apply an explicit "use this value" request from the extracted-information panel (not saved).
  useEffect(() => {
    if (suggestion) {
      form.setValue(suggestion.field, suggestion.value);
      requestAnimationFrame(() => document.getElementById(`profile-${suggestion.field}`)?.focus());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestion]);

  const onSubmit = (event) =>
    form.submit(
      event,
      async (values) => {
        if (exists && !dirty) return;
        const body = exists ? changes : toApiValues(values);
        if (!exists && Object.values(body).every((v) => v === null)) {
          form.setApiError(new ApiError({ status: 400, message: "Fill in at least one field to create your profile." }));
          return;
        }
        const saved = exists ? await updateProfile(body) : await createProfile(body);
        toast.success(exists ? "Profile updated." : "Profile created.");
        onSaved(saved);
      },
      (error) => {
        if (error.status === 409) {
          form.setApiError(new ApiError({ status: 409, message: "A profile already exists for your account. Reloading it…" }));
          onSaved(undefined); // ask the page to reload the saved profile
          return true;
        }
        return false;
      },
    );

  return (
    <form ref={form.formRef} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <ErrorAlert error={form.apiError} title={exists ? "We couldn't save your changes" : "We couldn't create your profile"} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Input id="profile-college" label="College or university" autoComplete="organization" maxLength={PROFILE_LIMITS.college} {...form.field("college")} />
        <Input id="profile-degree" label="Degree" placeholder="e.g. B.Tech Computer Science" maxLength={PROFILE_LIMITS.degree} {...form.field("degree")} />
        <Input
          id="profile-graduation_year"
          label="Graduation year"
          inputMode="numeric"
          placeholder="e.g. 2027"
          maxLength={4}
          hint={`Between ${PROFILE_LIMITS.yearMin} and ${PROFILE_LIMITS.yearMax}.`}
          {...form.field("graduation_year")}
        />
        <Input id="profile-location" label="Location" autoComplete="address-level2" placeholder="e.g. Bengaluru" maxLength={PROFILE_LIMITS.location} {...form.field("location")} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={form.submitting} disabled={exists && !dirty}>
          {form.submitting ? "Saving…" : exists ? "Save changes" : "Create profile"}
        </Button>
        {dirty && (
          <Button variant="ghost" onClick={() => Object.entries(toFormValues(profile)).forEach(([k, v]) => form.setValue(k, v))}>
            Discard changes
          </Button>
        )}
        <p className="text-xs text-slate-500" aria-live="polite">
          {exists ? (dirty ? "You have unsaved changes." : "All changes saved.") : "You haven't created a profile yet."}
        </p>
      </div>
    </form>
  );
}

// What the parser read from the latest parsed resume: read-only and never copied automatically.
function ExtractedPanel({ resumes, detail, parsed, user, profileLocation, onUse }) {
  let body;
  if (resumes.status === "loading" || resumes.status === "idle") body = <CardSkeleton label="your resume information" lines={3} />;
  else if (resumes.status === "error") body = <CardError error={resumes.error} onRetry={resumes.reload} label="your resumes" />;
  else if (!parsed) {
    body = (
      <CardEmpty
        title="No parsed resume yet"
        message="Upload a resume to see the information we extract from it."
        action={
          <Link to="/resumes" className="text-sm font-medium text-brand-700 hover:underline">
            Go to resumes
          </Link>
        }
      />
    );
  } else if (detail.status === "loading" || detail.status === "idle") body = <CardSkeleton label="your resume information" lines={3} />;
  else if (detail.status === "error") body = <CardError error={detail.error} onRetry={detail.reload} label="your resume information" />;
  else {
    const data = detail.data.extracted_data || {};
    const emailDiffers = data.email && user?.email && data.email.toLowerCase() !== user.email.toLowerCase();
    const education = (data.education || []).slice(0, 3);
    body = (
      <div className="flex flex-col gap-4 text-sm">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          {[
            ["Full name", data.full_name],
            ["Email", data.email],
            ["Phone", data.phone],
            ["Address", data.address],
          ].map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-xs text-slate-500">{label}</dt>
              <dd className="mt-0.5 break-words text-slate-900">{value || <span className="text-slate-400">Not found</span>}</dd>
            </div>
          ))}
        </dl>
        {emailDiffers && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
            The email on your resume differs from your account email. Your account email is not changed.
          </p>
        )}
        {data.address && data.address.trim() !== (profileLocation || "").trim() && (
          <div>
            <Button variant="secondary" className="py-1.5 text-xs" onClick={() => onUse("location", data.address.slice(0, PROFILE_LIMITS.location))}>
              Use resume address as location
            </Button>
            <p className="mt-1 text-xs text-slate-500">Fills the form only — nothing is saved until you choose Save.</p>
          </div>
        )}
        <div>
          <p className="text-xs font-medium text-slate-500">Education on your resume</p>
          {education.length ? (
            <ul className="mt-1.5 flex flex-col gap-2">
              {education.map((entry, i) => {
                const { heading, lines } = entryLines(entry);
                return (
                  <li key={i} className="rounded-lg bg-slate-50 px-3 py-2">
                    <p className="font-medium text-slate-900">{heading}</p>
                    {lines.slice(0, 2).map((line, j) => (
                      <p key={j} className="text-xs text-slate-600">
                        {line}
                      </p>
                    ))}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-1 text-slate-500">No education found in this resume.</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <section aria-labelledby="extracted-title" className={panel}>
      <PanelTitle
        id="extracted-title"
        hint={parsed ? `Read from ${parsed.filename}. Shown separately and never copied into your profile automatically.` : undefined}
      >
        Extracted from your resume
      </PanelTitle>
      {body}
    </section>
  );
}

export default function ProfilePage() {
  const { user } = useAuth();
  const profile = useApiResource(getProfile, "profile");
  const resumes = useApiResource(listResumes, "resumes");
  const parsed = resumes.status === "success" ? latestParsed(resumes.data) : null;
  const detail = useApiResource(() => getResumeDetail(parsed.resume_id), parsed?.resume_id ?? null, { enabled: Boolean(parsed) });
  const [suggestion, setSuggestion] = useState(null);

  useEffect(() => {
    const previous = document.title;
    document.title = "Profile · CareerNova AI";
    return () => {
      document.title = previous;
    };
  }, []);

  const onSaved = (saved) => {
    setSuggestion(null);
    if (saved === undefined) profile.reload();
    else profile.setData(saved);
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Profile</h1>
        <p className="mt-1 text-sm text-slate-600">Your picture, bio, account, academic details and what we read from your resume.</p>
      </header>

      {/* Only real, loaded data: completeness waits for both the profile and the resume list. */}
      {profile.status === "success" && resumes.status === "success" && (
        <Completeness user={user} profile={profile.data} parsed={parsed} />
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-6">
          <section aria-labelledby="photo-title" className={panel}>
            <PanelTitle id="photo-title" hint="Shown only to you, across CareerNova AI.">
              Profile picture
            </PanelTitle>
            <ProfilePhoto user={user} hasAvatar={Boolean(profile.data?.has_avatar)} onChanged={(saved) => (saved ? profile.setData(saved) : profile.reload())} />
          </section>
          <section aria-labelledby="bio-title" className={panel}>
            <PanelTitle id="bio-title" hint="A short professional introduction, up to 600 characters.">
              About me
            </PanelTitle>
            {profile.status === "success" ? (
              <BioEditor key={profile.data?.profile_id ?? "new"} profile={profile.data} onSaved={(saved) => profile.setData(saved)} />
            ) : profile.status === "error" ? (
              <CardError error={profile.error} onRetry={profile.reload} label="your bio" />
            ) : (
              <CardSkeleton label="your bio" lines={2} />
            )}
          </section>
          <AccountDetails user={user} />
          <section aria-labelledby="academic-title" className={panel}>
            <PanelTitle id="academic-title" hint="Entered by you. Used alongside your resume for matching.">
              Academic profile
            </PanelTitle>
            {profile.status === "loading" || profile.status === "idle" ? (
              <CardSkeleton label="your profile" lines={4} />
            ) : profile.status === "error" ? (
              <CardError error={profile.error} onRetry={profile.reload} label="your profile" />
            ) : (
              <ProfileForm key={profile.data?.profile_id ?? "new"} profile={profile.data} onSaved={onSaved} suggestion={suggestion} />
            )}
          </section>
        </div>
        <div className="min-w-0">
          <ExtractedPanel
            resumes={resumes}
            detail={detail}
            parsed={parsed}
            user={user}
            profileLocation={profile.data?.location}
            onUse={(field, value) => setSuggestion({ field, value, at: Date.now() })}
          />
        </div>
      </div>
    </div>
  );
}
