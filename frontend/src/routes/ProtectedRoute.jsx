import { Navigate, Outlet, useLocation } from "react-router-dom";
import Button from "../components/ui/Button";
import ErrorAlert from "../components/ui/ErrorAlert";
import Spinner from "../components/ui/Spinner";
import { useAuth } from "../context/AuthContext";

// Requires a signed-in user; otherwise sends them to /login?next=<where they were going>.
// If the stored session could not be checked (server unreachable or failing), the user is NOT
// treated as signed out: the error is shown and they can try again.
export default function ProtectedRoute() {
  const { status, sessionError, retrySession } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Restoring your session" />
      </div>
    );
  }
  if (status === "unavailable") {
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4">
        <ErrorAlert title="Could not restore your session" error={sessionError} />
        <Button onClick={retrySession}>Try again</Button>
      </div>
    );
  }
  if (status !== "authenticated") {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <Outlet />;
}
