import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { login } from "../../api/auth";
import { ApiError } from "../../api/errors";
import Button from "../../components/ui/Button";
import Checkbox from "../../components/ui/Checkbox";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Input from "../../components/ui/Input";
import { useAuth } from "../../context/AuthContext";
import { safeRedirectPath } from "../../utils/redirect";
import AuthHeader, { linkClass } from "./components/AuthHeader";
import PasswordInput from "./components/PasswordInput";
import ResendVerification from "./components/ResendVerification";
import useAuthForm from "./useAuthForm";
import { validateEmail, validateLoginPassword } from "./validation";

export default function LoginPage() {
  const { startSession } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeRedirectPath(params.get("next"));
  const [unverifiedEmail, setUnverifiedEmail] = useState(null);

  const form = useAuthForm({ email: "", password: "", remember: false }, (v) => ({
    email: validateEmail(v.email),
    password: validateLoginPassword(v.password),
  }));

  const onSubmit = (event) =>
    form.submit(
      event,
      async ({ email, password, remember }) => {
        setUnverifiedEmail(null);
        const tokens = await login(email.trim(), password);
        await startSession(tokens, remember);
        navigate(next, { replace: true });
      },
      (error) => {
        form.setValue("password", "");
        if (error.status === 403 && /deactivated/i.test(String(error.message || ""))) {
          // Correct password, but an administrator has deactivated the account.
          form.setApiError(new ApiError({ status: 403, message: "This account has been deactivated. Contact an administrator to restore access." }));
          return true;
        }
        if (error.status === 403) {
          // Correct password, but the email address has not been verified yet.
          setUnverifiedEmail(form.values.email.trim());
          return true;
        }
        if (error.status === 401) {
          form.setApiError(new ApiError({ status: 401, message: "The email or password is incorrect. Check them and try again." }));
          return true;
        }
        return false;
      },
    );

  const register = `/register${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`;

  return (
    <>
      <AuthHeader title="Sign in" description="Welcome back. Sign in to continue your internship search." />

      {/* Outside the sign-in <form>: the resend control is a form of its own (forms must not nest). */}
      {unverifiedEmail && (
        <div role="alert" className="mb-4 flex flex-col gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p>
            <span className="font-medium">Verify your email to sign in.</span> We sent a verification link to{" "}
            <span className="font-medium">{unverifiedEmail}</span> when you registered.
          </p>
          <ResendVerification initialEmail={unverifiedEmail} lockEmail compact />
        </div>
      )}

      <form ref={form.formRef} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorAlert error={form.apiError} title="Sign-in failed" />

        <Input label="Email address" type="email" autoComplete="email" inputMode="email" autoFocus {...form.field("email")} />

        <div className="flex flex-col gap-1">
          <PasswordInput label="Password" autoComplete="current-password" maxLength={128} {...form.field("password")} />
          <Link to="/forgot-password" className={`self-end text-sm ${linkClass}`}>
            Forgot password?
          </Link>
        </div>

        <Checkbox
          label="Remember me"
          hint="Stay signed in on this device. Use only on a device you trust."
          name="remember"
          checked={form.values.remember}
          onChange={(event) => form.setValue("remember", event.target.checked)}
        />

        <Button type="submit" loading={form.submitting} className="w-full py-2.5">
          {form.submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-600">
        New to CareerNova AI?{" "}
        <Link to={register} className={linkClass}>
          Create a student account
        </Link>
      </p>
    </>
  );
}
