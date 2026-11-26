import { Link } from "react-router-dom";
import EmptyState from "../../components/ui/EmptyState";

export default function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <EmptyState
        icon="target"
        title="Page not found"
        titleAs="h1"
        message="The page you are looking for does not exist."
        action={
          <Link to="/" className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600">
            Go home
          </Link>
        }
      />
    </div>
  );
}
