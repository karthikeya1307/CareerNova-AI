import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { resetPassword } from "../../api/auth";
import Button from "../../components/ui/Button";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Input from "../../components/ui/Input";
import { useAuth } from "../../context/AuthContext";
import AuthHeader, { linkClass } from "./components/AuthHeader";
import PasswordInput from "./components/PasswordInput";
import PasswordRequirements from "./components/PasswordRequirements";
import StatusPanel from "./components/StatusPanel";
import useAuthForm from "./useAuthForm";
import useTokenFromUrl from "./useTokenFromUrl";
import { validateConfirmation, validateNewPassword, validateToken } from "./validation";

function validate(v) {
  return {
    token: validateToken(v.token),
    new_password: validateNewPassword(v.new_password),
    confirm_password: validateConfirmation(v.new_password, v.confirm_password),
  };
}

// The reset email contains a one-time code (decision D3: pasted token). A `?token=` link also works:
// it is read once and removed from the address bar.
export default function ResetPasswordPage() {
  const tokenFromUrl = useTokenFromUrl();
  const { isAuthenticated, logout } = useAuth();
  const [done, setDone] = useState(false);
  const [tokenProblem, setTokenProblem] = useState(null);
  const form = useAuthForm({ token: tokenFromUrl, new_password: "", confirm_password: "" }, validate);
  // A code from the link is used as-is; once it is malformed or rejected, the field appears (and
  // stays) so a fresh code from the email can be pasted on this page.
  const [editingToken, setEditingToken] = useState(!tokenFromUrl);
  const showTokenInput = editingToken || Boolean(form.errors.token);
  useEffect(() => {
    if (form.errors.token) setEditingToken(true);
  }, [form.errors.token]);

  const onSubmit = (event) =>
    form.submit(
      event,
      async (v) => {
        setTokenProblem(null);
        await resetPassword(v.token.trim(), v.new_password);
        // The backend signs out every session after a reset; drop this browser's copy too.
        if (isAuthenticated) await logout();
        setDone(true);
      },
      (error) => {
        if (error.status === 400) {
          const expired = String(error.message).toLowerCase().includes("expired");
          setTokenProblem(expired ? "expired" : "invalid");
          form.setErrors({ token: expired ? "This reset code has expired." : "This reset code is invalid or has already been used." });
          form.setValue("new_password", "");
          form.setValue("confirm_password", "");
          form.focusFirstInvalid();
          return true;
        }
        return false;
      },
    );

  if (done) {
    return (
      <StatusPanel
        tone="success"
        title="Password updated"
        actions={
          <Link
            to="/login"
            className="inline-flex w-full items-center justify-center rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
          >
            Sign in with your new password
          </Link>
        }
      >
        <p>Your password has been reset. For your security, you've been signed out on all devices.</p>
      </StatusPanel>
    );
  }

  return (
    <>
      <AuthHeader title="Choose a new password" description="Enter the reset code from your email and a new password." />
      <form ref={form.formRef} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorAlert error={form.apiError} title="We couldn't reset your password" />
        {tokenProblem && (
          <div role="alert" className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            {tokenProblem === "expired" ? "Reset codes expire after 30 minutes." : "Reset codes work once, and only the newest code is valid."}{" "}
            <Link to="/forgot-password" className={linkClass}>
              Request a new code
            </Link>
          </div>
        )}
        {showTokenInput ? (
          <Input
            label="Reset code"
            autoComplete="one-time-code"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus={!tokenFromUrl}
            hint="Copy the whole code from the email."
            {...form.field("token")}
          />
        ) : (
          <p className="rounded-md bg-brand-50 px-3 py-2 text-sm text-brand-800">Reset code received from your link.</p>
        )}
        <div className="flex flex-col gap-1">
          <PasswordInput
            label="New password"
            autoComplete="new-password"
            maxLength={128}
            autoFocus={!showTokenInput}
            describedBy="new-password-rules"
            {...form.field("new_password")}
          />
          <PasswordRequirements id="new-password-rules" password={form.values.new_password} />
        </div>
        <PasswordInput label="Confirm new password" autoComplete="new-password" maxLength={128} {...form.field("confirm_password")} />
        <Button type="submit" loading={form.submitting} className="w-full py-2.5">
          {form.submitting ? "Updating password…" : "Update password"}
        </Button>
      </form>
      <div className="mt-6 flex flex-col items-center gap-2 text-sm text-slate-600">
        <Link to="/forgot-password" className={linkClass}>
          Need a new reset code?
        </Link>
        <Link to="/login" className={linkClass}>
          Back to sign in
        </Link>
      </div>
    </>
  );
}
