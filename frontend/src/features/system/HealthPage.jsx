import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth } from "../../api/system";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import ErrorAlert from "../../components/ui/ErrorAlert";
import Spinner from "../../components/ui/Spinner";

// Checks that the browser can reach FastAPI through the Vite /api proxy.
export default function HealthPage() {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  const check = useCallback(async () => {
    setState({ loading: true, data: null, error: null });
    try {
      setState({ loading: false, data: await getHealth(), error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  return (
    <div className="mx-auto max-w-xl px-4 py-10">
      <Card
        title="Backend connection"
        actions={
          <Button variant="secondary" onClick={check} disabled={state.loading}>
            Check again
          </Button>
        }
      >
        {state.loading && <Spinner label="Contacting the API" />}
        {state.error && <ErrorAlert title="The API could not be reached" error={state.error} />}
        {state.data && (
          <dl className="grid grid-cols-3 gap-y-2 text-sm">
            <dt className="text-slate-500">Status</dt>
            <dd className="col-span-2">
              <Badge tone={state.data.status === "Healthy" ? "success" : "danger"}>{state.data.status}</Badge>
            </dd>
            <dt className="text-slate-500">Message</dt>
            <dd className="col-span-2">{state.data.message}</dd>
          </dl>
        )}
      </Card>
      <p className="mt-4 text-center text-sm">
        <Link className="text-brand-700 hover:underline" to="/login">
          Go to sign in
        </Link>
      </p>
    </div>
  );
}
