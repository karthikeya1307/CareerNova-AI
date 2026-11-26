import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { verifyEmail } from "../../api/auth";
import { normalizeError } from "../../api/errors";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import AuthHeader, { linkClass } from "./components/AuthHeader";
import ResendVerification from "./components/ResendVerification";
import StatusPanel from "./components/StatusPanel";
import useTokenFromUrl from "./useTokenFromUrl";
import { LIMITS } from "./validation";

// Verification tokens are single-use. React StrictMode mounts effects twice in development, so a
// request that is still in flight is shared: the backend sees one call per token per page load.
// The entry is dropped as soon as the request settles, so the token is not kept in memory.
const inFlight = new Map();

function verifyOnce(token) {
  if (!inFlight.has(token)) {
    const request = verifyEmail(token)
      .catch((error) => {
        throw normalizeError(error);
      })
      .finally(() => inFlight.delete(token));
    inFlight.set(token, request);
  }
  return inFlight.get(token);
}

export function classifyVerificationError(failure) {
  if (failure.status === 0 || failure.status >= 500) return "unavailable";
  const detail = String(failure.message || "").toLowerCase();
  if (detail.includes("expired")) return "expired";
  if (detail.includes("already been used")) return "used";
  return "invalid";
}

const looksValid = (token) => token.length >= LIMITS.tokenMin && token.length <= LIMITS.tokenMax;

export default function VerifyEmailPage() {
  const token = useTokenFromUrl();
  const [state, setState] = useState(() => (looksValid(token) ? { status: "verifying" } : { status: "invalid" }));

  const run = useCallback(() => {
    if (!looksValid(token)) return undefined;
    let active = true;
    setState({ status: "verifying" });
    verifyOnce(token)
      .then((result) => active && setState({ status: "verified", message: result?.message }))
      .catch((failure) => active && setState({ status: classifyVerificationError(failure), error: failure }));
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => run(), [run]);

  const signIn = (
    <Link to="/login" className="inline-flex w-full items-center justify-center rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600">
      Continue to sign in
    </Link>
  );

  switch (state.status) {
    case "verifying":
      return (
        <>
          <AuthHeader title="Verifying your email" />
          <div className="flex justify-center py-6">
            <Spinner label="Confirming your verification link…" />
          </div>
        </>
      );
    case "verified":
      return (
        <StatusPanel tone="success" title="Email verified" actions={signIn}>
          <p>Your email address is confirmed. You can now sign in to CareerNova AI.</p>
        </StatusPanel>
      );
    case "used":
      return (
        <StatusPanel tone="info" title="Link already used" actions={signIn}>
          <p>This verification link has already been used. If you verified your email, just sign in.</p>
        </StatusPanel>
      );
    case "expired":
      return (
        <StatusPanel tone="warning" title="Verification link expired" actions={<ResendVerification />}>
          <p>Verification links are valid for 24 hours. Enter your email address and we'll send you a new one.</p>
        </StatusPanel>
      );
    case "unavailable":
      return (
        <StatusPanel
          tone="error"
          title="We couldn't verify your email right now"
          actions={
            <Button onClick={run} className="w-full py-2.5">
              Try again
            </Button>
          }
        >
          <p>{state.error?.message}</p>
          <p>Your link is still valid — try again in a moment.</p>
        </StatusPanel>
      );
    default:
      return (
        <StatusPanel
          tone="error"
          title="Invalid verification link"
          actions={
            <>
              <ResendVerification />
              <Link to="/login" className={`text-center text-sm ${linkClass}`}>
                Back to sign in
              </Link>
            </>
          }
        >
          <p>This link is incomplete or not valid. Open the link from your most recent verification email, or request a new one.</p>
        </StatusPanel>
      );
  }
}
