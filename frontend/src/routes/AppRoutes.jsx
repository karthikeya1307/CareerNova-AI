import { Route, Routes } from "react-router-dom";
import LoginPlaceholderPage from "../features/auth/LoginPlaceholderPage";
import ComingSoonPage from "../features/system/ComingSoonPage";
import HealthPage from "../features/system/HealthPage";
import NotFoundPage from "../features/system/NotFoundPage";
import AppLayout from "../layouts/AppLayout";
import AuthLayout from "../layouts/AuthLayout";
import { ADMIN_SECTIONS, STUDENT_SECTIONS } from "./navigation";
import ProtectedRoute from "./ProtectedRoute";
import RoleRoute from "./RoleRoute";

export default function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/health" element={<HealthPage />} />
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPlaceholderPage />} />
      </Route>

      {/* Signed-in users */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          {STUDENT_SECTIONS.map((section) => (
            <Route
              key={section.path}
              path={section.path === "/" ? undefined : section.path}
              index={section.path === "/" ? true : undefined}
              element={<ComingSoonPage title={section.label} phase={section.phase} />}
            />
          ))}
          {/* Administrators only */}
          <Route element={<RoleRoute roles={["admin"]} />}>
            {ADMIN_SECTIONS.map((section) => (
              <Route key={section.path} path={section.path} element={<ComingSoonPage title={section.label} phase={section.phase} />} />
            ))}
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
