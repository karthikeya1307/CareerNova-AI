import { Navigate, Outlet, useSearchParams } from "react-router-dom";
import Spinner from "../components/ui/Spinner";
import { useAuth } from "../context/AuthContext";
import { safeRedirectPath } from "../utils/redirect";

// For sign-in, registration and forgot-password: a signed-in user is sent on to `?next=`
// (validated) or the dashboard instead of seeing the form again.
export default function GuestRoute() {
  const { status } = useAuth();
  const [params] = useSearchParams();

  if (status === "loading") {
    return (
      <div className="flex justify-center py-6">
        <Spinner label="Checking your session" />
      </div>
    );
  }
  if (status === "authenticated") {
    return <Navigate to={safeRedirectPath(params.get("next"))} replace />;
  }
  return <Outlet />;
}
