import { Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import ForbiddenPage from "../features/system/ForbiddenPage";

// Shows a 403 page unless the signed-in user has one of `roles`.
// (The backend enforces the same rule; this only keeps students out of admin screens.)
export default function RoleRoute({ roles = ["admin"] }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) return <ForbiddenPage />;
  return <Outlet />;
}
