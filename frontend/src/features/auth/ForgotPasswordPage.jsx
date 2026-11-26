import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../../api/auth";
import Button from "../../components/ui/Button";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Input from "../../components/ui/Input";
import AuthHeader, { linkClass } from "./components/AuthHeader";
import StatusPanel from "./components/StatusPanel";
import useAuthForm from "./useAuthForm";
import { validateEmail } from "./validation";

export default function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState(null);
  const form = useAuthForm({ email: "" }, (v) => ({ email: validateEmail(v.email) }));

  const onSubmit = (event) =>
    form.submit(event, async ({ email }) => {
      await forgotPassword(email.trim());
      // Same screen whatever the backend found: it never says whether the account exists.
      setSentTo(email.trim());
    });

  if (sentTo) {
    return (
      <StatusPanel
        tone="info"
        title="Check your email"
        actions={
          <>
            <Link
              to="/reset-password"
              className="inline-flex w-full items-center justify-center rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
            >
              I have a reset code
            </Link>
            <Link to="/login" className={`text-center text-sm ${linkClass}`}>
              Back to sign in
            </Link>
          </>
        }
      >
        <p>
          If an account exists for <span className="font-medium text-slate-900">{sentTo}</span>, we've sent password reset
          instructions with a reset code. The code expires in 30 minutes and works once.
        </p>
        <p>Didn't get an email? Check your spam folder or try again in a few minutes.</p>
      </StatusPanel>
    );
  }

  return (
    <>
      <AuthHeader title="Reset your password" description="Enter the email you registered with and we'll send you a reset code." />
      <form ref={form.formRef} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorAlert error={form.apiError} title="We couldn't send reset instructions" />
        <Input label="Email address" type="email" autoComplete="email" inputMode="email" autoFocus {...form.field("email")} />
        <Button type="submit" loading={form.submitting} className="w-full py-2.5">
          {form.submitting ? "Sending…" : "Send reset instructions"}
        </Button>
      </form>
      <div className="mt-6 flex flex-col items-center gap-2 text-sm text-slate-600">
        <Link to="/reset-password" className={linkClass}>
          Already have a reset code?
        </Link>
        <span>
          Remembered it?{" "}
          <Link to="/login" className={linkClass}>
            Sign in
          </Link>
        </span>
      </div>
    </>
  );
}
