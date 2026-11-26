import { Component, Suspense } from "react";
import { useLocation } from "react-router-dom";
import Button from "../components/ui/Button";
import Spinner from "../components/ui/Spinner";

// A page that failed to load or render. Lazy pages that fail to download (for example after a new
// deployment replaced the old files, or a dropped connection) can only recover with a full reload,
// because React caches the failed import.
class PageErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  // Leaving the failed page clears the error. Healthy pages are never remounted, so a page that
  // changes its own URL (e.g. /assistant -> /assistant/7) keeps its state.
  componentDidUpdate(previous) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const chunk = /Loading chunk|dynamically imported module|Importing a module script failed|error loading dynamically/i.test(String(error?.message || error));
    return (
      <div role="alert" className="mx-auto mt-10 flex max-w-md flex-col items-center gap-3 rounded-2xl border border-slate-200/80 bg-white p-6 text-center shadow-card">
        <h1 className="text-lg font-semibold text-slate-900">{chunk ? "This page couldn't be loaded" : "Something went wrong on this page"}</h1>
        <p className="text-sm text-slate-600">
          {chunk
            ? "Part of the app didn't download. Check your connection and reload; if the app was just updated, reloading fetches the new version."
            : "Reload the page to try again. Your saved data is not affected."}
        </p>
        <Button onClick={() => window.location.reload()}>Reload page</Button>
      </div>
    );
  }
}

function PageLoading() {
  return (
    <div className="flex justify-center py-16">
      <Spinner label="Loading page" />
    </div>
  );
}

// Wraps the routed page: a loading state while a lazy page downloads, and an error state if it
// fails. Moving to another path clears an earlier error (without remounting a working page).
export default function PageBoundary({ children }) {
  const { pathname } = useLocation();
  return (
    <PageErrorBoundary resetKey={pathname}>
      <Suspense fallback={<PageLoading />}>{children}</Suspense>
    </PageErrorBoundary>
  );
}
