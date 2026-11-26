import { useEffect, useState } from "react";
import { resendVerification } from "../../../api/auth";
import Button from "../../../components/ui/Button";
import ErrorAlert from "../../../components/ui/ErrorAlert";
import Input from "../../../components/ui/Input";
import useAuthForm from "../useAuthForm";
import { validateEmail } from "../validation";

// Matches RESEND_VERIFICATION_COOLDOWN_SECONDS in backend/routes/auth.py.
export const RESEND_COOLDOWN_SECONDS = 60;

const GENERIC = "If an unverified account exists for that email, we've sent a new verification link.";

// "Send me a new verification link". The backend answers the same way for unknown, verified and
// unverified emails, so this never reveals whether an account exists.
// `initialCooldown`: a link was issued moments ago (e.g. right after registering), and the backend
// silently ignores resends inside its cooldown, so the button starts disabled.
export default function ResendVerification({ initialEmail = "", lockEmail = false, compact = false, initialCooldown = 0 }) {
  const form = useAuthForm({ email: initialEmail }, (v) => ({ email: validateEmail(v.email) }));
  const [message, setMessage] = useState(null);
  const [cooldown, setCooldown] = useState(initialCooldown);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const onSubmit = (event) =>
    form.submit(event, async ({ email }) => {
      const result = await resendVerification(email.trim());
      setMessage(result?.message || GENERIC);
      setCooldown(RESEND_COOLDOWN_SECONDS);
    });

  return (
    <form ref={form.formRef} onSubmit={onSubmit} noValidate className={`flex flex-col gap-3 text-left ${compact ? "" : "rounded-xl border border-slate-200 bg-slate-50 p-4"}`}>
      {!lockEmail && (
        <Input label="Email address" type="email" autoComplete="email" inputMode="email" {...form.field("email")} />
      )}
      <ErrorAlert error={form.apiError} title="We couldn't send a new link" />
      {message && (
        <p role="status" className="rounded-md bg-mint-50 px-3 py-2 text-sm text-mint-800">
          {message}
        </p>
      )}
      <Button type="submit" variant="secondary" loading={form.submitting} disabled={cooldown > 0}>
        {cooldown > 0 ? `Resend available in ${cooldown}s` : "Resend verification email"}
      </Button>
    </form>
  );
}
