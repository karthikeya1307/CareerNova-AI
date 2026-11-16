import { AuthProvider } from "./context/AuthContext";
import { ConfirmProvider } from "./context/ConfirmContext";
import { ToastProvider } from "./context/ToastContext";
import AppRoutes from "./routes/AppRoutes";

// Providers shared by the whole app. The router lives in main.jsx (and in tests).
export default function App({ authProps = {} }) {
  return (
    <ToastProvider>
      <ConfirmProvider>
        <AuthProvider {...authProps}>
          <AppRoutes />
        </AuthProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}
