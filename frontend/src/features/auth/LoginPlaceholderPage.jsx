import { Link, useSearchParams } from "react-router-dom";
import { safeRedirectPath } from "../../utils/redirect";

// F0 placeholder: the sign-in, registration and password screens arrive in F1.
export default function LoginPlaceholderPage() {
  const [params] = useSearchParams();
  const next = safeRedirectPath(params.get("next"));
  return (
    <div className="flex flex-col gap-3 text-sm text-slate-700">
      <h1 className="text-lg font-semibold text-slate-900">Sign in</h1>
      <p>Sign-in, registration and password screens are built in frontend step F1.</p>
      {next !== "/" && <p className="text-slate-500">After signing in you will return to {next}.</p>}
      <Link to="/health" className="text-brand-700 hover:underline">
        Check the backend connection
      </Link>
    </div>
  );
}
