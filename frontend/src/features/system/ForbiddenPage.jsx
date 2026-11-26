import { Link } from "react-router-dom";
import EmptyState from "../../components/ui/EmptyState";

export default function ForbiddenPage() {
  return (
    <EmptyState
      icon="alert"
      title="You don't have access to this page"
      titleAs="h1"
      message="This area is only available to administrators."
      action={
        <Link to="/" className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600">
          Back to the dashboard
        </Link>
      }
    />
  );
}
