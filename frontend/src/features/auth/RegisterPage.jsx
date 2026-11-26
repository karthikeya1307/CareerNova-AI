import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { register } from "../../api/auth";
import Button from "../../components/ui/Button";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Input from "../../components/ui/Input";
import { safeRedirectPath } from "../../utils/redirect";
import AuthHeader, { linkClass } from "./components/AuthHeader";
import PasswordInput from "./components/PasswordInput";
import PasswordRequirements from "./components/PasswordRequirements";
import ResendVerification, { RESEND_COOLDOWN_SECONDS } from "./components/ResendVerification";
import StatusPanel from "./components/StatusPanel";
import useAuthForm from "./useAuthForm";
import {
  normalisePhone, validateConfirmation, validateEmail, validateName, validateNewPassword, validatePhone,
} from "./validation";

const EMPTY = { first_name: "", last_name: "", email: "", phone_number: "", password: "", confirm_password: "" };

function validate(v) {
  return {
    first_name: validateName(v.first_name, "first name"),
    last_name: validateName(v.last_name, "last name"),
    email: validateEmail(v.email),
    phone_number: validatePhone(v.phone_number),
    password: validateNewPassword(v.password),
    confirm_password: validateConfirmation(v.password, v.confirm_password),
  };
}

export default function RegisterPage() {
  const [params] = useSearchParams();
  const next = safeRedirectPath(params.get("next"));
  const signIn = `/login${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`;
  // null while filling the form; then { email, emailSent } once the account exists.
  const [created, setCreated] = useState(null);
  const form = useAuthForm(EMPTY, validate);

  const onSubmit = (event) =>
    form.submit(
      event,
      async (v) => {
        const email = v.email.trim().toLowerCase();
        await register({
          first_name: v.first_name.trim(),
          last_name: v.last_name.trim(),
          phone_number: normalisePhone(v.phone_number),
          email,
          password: v.password,
        });
        setCreated({ email, emailSent: true });
      },
      (error) => {
        if (error.status === 409) {
          form.setErrors({ email: "An account with this email already exists. Sign in or reset your password." });
          form.focusFirstInvalid();
          return true;
        }
        if (error.status === 503) {
          // The account was created but the verification email could not be sent.
          setCreated({ email: form.values.email.trim().toLowerCase(), emailSent: false });
          return true;
        }
        return false;
      },
    );

  if (created) {
    return (
      <StatusPanel
        tone={created.emailSent ? "info" : "warning"}
        title={created.emailSent ? "Check your email" : "Account created — email not sent"}
        actions={
          <>
            <ResendVerification initialEmail={created.email} lockEmail initialCooldown={RESEND_COOLDOWN_SECONDS} />
            <Link to={signIn} className={`text-center text-sm ${linkClass}`}>
              Back to sign in
            </Link>
          </>
        }
      >
        {created.emailSent ? (
          <p>
            We sent a verification link to <span className="font-medium text-slate-900">{created.email}</span>. Open it to
            activate your account, then sign in. The link is valid for 24 hours.
          </p>
        ) : (
          <p>
            Your account for <span className="font-medium text-slate-900">{created.email}</span> was created, but we couldn't
            send the verification email right now. Try resending it in a minute.
          </p>
        )}
        <p>Didn't get it? Check your spam folder, or send a new link below.</p>
      </StatusPanel>
    );
  }

  return (
    <>
      <AuthHeader title="Create your student account" description="Find internships that match your skills and track every application." />

      <form ref={form.formRef} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorAlert error={form.apiError} title="We couldn't create your account" />

        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="First name" autoComplete="given-name" autoFocus maxLength={100} {...form.field("first_name")} />
          <Input label="Last name" autoComplete="family-name" maxLength={100} {...form.field("last_name")} />
        </div>
        <Input label="Email address" type="email" autoComplete="email" inputMode="email" {...form.field("email")} />
        <Input
          label="Phone number"
          type="tel"
          autoComplete="tel"
          inputMode="tel"
          hint="Include your country code, for example +91 98765 43210."
          {...form.field("phone_number")}
        />
        <div className="flex flex-col gap-1">
          <PasswordInput label="Password" autoComplete="new-password" maxLength={128} describedBy="password-rules" {...form.field("password")} />
          <PasswordRequirements id="password-rules" password={form.values.password} />
        </div>
        <PasswordInput label="Confirm password" autoComplete="new-password" maxLength={128} {...form.field("confirm_password")} />

        <Button type="submit" loading={form.submitting} className="w-full py-2.5">
          {form.submitting ? "Creating account…" : "Create account"}
        </Button>
        <p className="text-xs text-slate-500">
          We'll email you a link to verify your address before your first sign-in.
        </p>
      </form>

      <p className="mt-6 text-center text-sm text-slate-600">
        Already have an account?{" "}
        <Link to={signIn} className={linkClass}>
          Sign in
        </Link>
      </p>
    </>
  );
}
