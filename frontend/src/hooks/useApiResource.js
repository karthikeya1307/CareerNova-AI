import { useCallback, useEffect, useRef, useState } from "react";
import { normalizeError } from "../api/errors";

// Loads one piece of server data and exposes { status, data, error, reload, setData }.
//   status: "idle" (disabled) | "loading" | "success" | "error"
// `key` identifies the request: when it changes the data is reloaded; responses for an older key
// are ignored, so a slow earlier request can never overwrite newer data.
// Session expiry is handled by the shared API client (refresh once, then sign out), so a 401 here
// only ever reaches a section after the session is already being cleared.
export default function useApiResource(fetcher, key, { enabled = true } = {}) {
  const [state, setState] = useState({ status: enabled ? "loading" : "idle", data: null, error: null });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const requestId = useRef(0);

  const load = useCallback(() => {
    const id = ++requestId.current;
    setState((current) => ({ status: "loading", data: current.data, error: null }));
    Promise.resolve()
      .then(() => fetcherRef.current())
      .then(
        (data) => id === requestId.current && setState({ status: "success", data, error: null }),
        (error) => id === requestId.current && setState({ status: "error", data: null, error: normalizeError(error) }),
      );
  }, []);

  useEffect(() => {
    if (!enabled) {
      requestId.current += 1; // drop any response still in flight
      setState({ status: "idle", data: null, error: null });
      return undefined;
    }
    load();
    return () => {
      requestId.current += 1;
    };
  }, [enabled, key, load]);

  const setData = useCallback((data) => {
    requestId.current += 1;
    setState({ status: "success", data, error: null });
  }, []);

  return { ...state, reload: load, setData };
}
