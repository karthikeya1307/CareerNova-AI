// Promise-based confirmation for destructive actions:
//   const ok = await confirm({ title, message, confirmLabel, tone: "danger", requireText: "REBUILD" });
// `requireText` makes the user type a word before confirming (used for the index rebuild).

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import ConfirmDialog from "../components/ui/ConfirmDialog";

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null);
  const resolver = useRef(null);
  const nextId = useRef(1);

  const confirm = useCallback((options) => {
    return new Promise((resolve) => {
      // A dialog that is still open is answered "no" before it is replaced, so its caller is
      // never left waiting.
      resolver.current?.(false);
      resolver.current = resolve;
      // A new key gives the new dialog fresh state (e.g. an empty "Type X to confirm" box).
      setRequest({ ...options, id: nextId.current++ });
    });
  }, []);

  const close = useCallback((result) => {
    resolver.current?.(result);
    resolver.current = null;
    setRequest(null);
  }, []);

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {request && (
        <ConfirmDialog key={request.id} {...request} onConfirm={() => close(true)} onCancel={() => close(false)} />
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const context = useContext(ConfirmContext);
  if (!context) throw new Error("useConfirm must be used inside <ConfirmProvider>");
  return context.confirm;
}
