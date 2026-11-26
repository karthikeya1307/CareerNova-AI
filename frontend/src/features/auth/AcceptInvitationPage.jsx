import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { acceptInvitation, checkInvitation } from "../../api/auth";
import Button from "../../components/ui/Button";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Spinner from "../../components/ui/Spinner";
import { useAuth } from "../../context/AuthContext";
import AuthHeader, { linkClass } from "./components/AuthHeader";
import PasswordInput from "./components/PasswordInput";
import PasswordRequirements from "./components/PasswordRequirements";
import StatusPanel from "./components/StatusPanel";
import useAuthForm from "./useAuthForm";
import useTokenFromUrl from "./useTokenFromUrl";
import { validateConfirmation, validateNewPassword } from "./validation";

// Messages for the backend's invitation error codes (backend/services/invitations.InvitationError).
export const INVITATION_PROBLEM = {
  invalid: { title: "This invitation link isn't valid", text: "Check that you opened the complete link from the email, or ask your administrator for a new invitation." },
  expired: { title: "This invitation has expired", text: "Invitation links work for 72 hours. Ask your administrator to send a new one." },
  used: { title: "This invitation was already used", text: "Your account is already active. Sign in with the password you chose." },
  revoked: { title: "This invitation was replaced", text: "A newer invitation was sent, or this one was cancelled. Use the link in the most recent email." },
  inactive: { title: "This account isn't available", text: "Contact your administrator." },
};

const problemCode = (error) => error?.detail?.code || (error?.status === 410 ? "expired" : "invalid");

function validate(v) {
  return { password: validateNewPassword(v.password), confirm_password: validateConfirmation(v.password, v.confirm_password) };
}

// Opened from the invitation email (/accept-invitation?token=...). The token is read once and
// removed from the address bar; the person chooses their own password, which activates the account.
export default function AcceptInvitationPage() {
  const token = useTokenFromUrl();
  const { isAuthenticated, logout } = useAuth();
  const [invite, setInvite] = useState(null);
  const [problem, setProblem] = useState(token ? null : "invalid");
  const [loadError, setLoadError] = useState(null);
  const [done, setDone] = useState(null);
  const form = useAuthForm({ password: "", confirm_password: "" }, validate);

  useEffect(() => {
    if (!token) return undefined;
    let active = true;
    checkInvitation(token)
      .then((data) => active && setInvite(data))
      .catch((error) => {
        if (!active) return;
        if (error.status === 400 || error.status === 410) setProblem(problemCode(error));
        else setLoadError(error);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const onSubmit = (event) =>
    form.submit(
      event,
      async (v) => {
        const result = await acceptInvitation(token, v.password);
        if (isAuthenticated) await logout();
        setDone(result.email || invite?.email || "");
      },
      (error) => {
        if (error.status === 400 || error.status === 410) {
          setProblem(problemCode(error));
          return true;
        }
        return false;
      },
    );

  if (done !== null) {
    return (
      <StatusPanel
        tone="success"
        title="Your account is active"
        actions={
          <Link
            to="/login"
            className="inline-flex w-full items-center justify-center rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
          >
            Sign in
          </Link>
        }
      >
        <p>Your password is set{done ? ` for ${done}` : ""}. Sign in to start using CareerNova AI.</p>
      </StatusPanel>
    );
  }

  if (problem) {
    const p = INVITATION_PROBLEM[problem] || INVITATION_PROBLEM.invalid;
    return (
      <StatusPanel
        tone="warning"
        title={p.title}
        actions={
          <Link to="/login" className={linkClass}>
            Go to sign in
          </Link>
        }
      >
        <p>{p.text}</p>
      </StatusPanel>
    );
  }

  if (loadError) {
    return (
      <>
        <AuthHeader title="Activate your account" />
        <ErrorAlert error={loadError} title="We couldn't check your invitation" />
      </>
    );
  }

  if (!invite) {
    return (
      <div className="flex items-center justify-center py-10">
        <Spinner label="Checking your invitation…" />
      </div>
    );
  }

  return (
    <>
      <AuthHeader
        title="Activate your account"
        description={`Welcome, ${invite.first_name}. Choose a password for ${invite.email} to finish setting up your CareerNova AI account.`}
      />
      <form ref={form.formRef} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorAlert error={form.apiError} title="We couldn't activate your account" />
        <div className="flex flex-col gap-1">
          <PasswordInput label="Password" autoComplete="new-password" maxLength={128} autoFocus describedBy="invite-password-rules" {...form.field("password")} />
          <PasswordRequirements id="invite-password-rules" password={form.values.password} />
        </div>
        <PasswordInput label="Confirm password" autoComplete="new-password" maxLength={128} {...form.field("confirm_password")} />
        <Button type="submit" loading={form.submitting} className="w-full py-2.5">
          {form.submitting ? "Activating…" : "Activate account"}
        </Button>
        <p className="text-xs text-slate-500">Only you know this password. Your administrator never sees it.</p>
      </form>
    </>
  );
}
