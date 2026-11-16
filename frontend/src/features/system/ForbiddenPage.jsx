import { Link } from "react-router-dom";
import EmptyState from "../../components/ui/EmptyState";

export default function ForbiddenPage() {
  return (
    <EmptyState
      title="You don't have access to this page"
      message="This area is only available to administrators."
      action={
        <Link to="/" className="text-sm text-brand-700 hover:underline">
          Back to the dashboard
        </Link>
      }
    />
  );
}
