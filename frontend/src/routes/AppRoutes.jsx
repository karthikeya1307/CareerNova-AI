import { lazy, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import ForgotPasswordPage from "../features/auth/ForgotPasswordPage";
import LoginPage from "../features/auth/LoginPage";
import RegisterPage from "../features/auth/RegisterPage";
import ResetPasswordPage from "../features/auth/ResetPasswordPage";
import AcceptInvitationPage from "../features/auth/AcceptInvitationPage";
import VerifyEmailPage from "../features/auth/VerifyEmailPage";
import DashboardPage from "../features/dashboard/DashboardPage";
import ComingSoonPage from "../features/system/ComingSoonPage";
import HealthPage from "../features/system/HealthPage";
import NotFoundPage from "../features/system/NotFoundPage";
import AppLayout from "../layouts/AppLayout";
import AuthLayout from "../layouts/AuthLayout";
import GuestRoute from "./GuestRoute";
import { STUDENT_SECTIONS } from "./navigation";
import ProtectedRoute from "./ProtectedRoute";
import RoleRoute from "./RoleRoute";

// Feature pages load on demand (route-level code splitting). Sign-in pages, the layouts and the
// dashboard stay in the main bundle so the first screens appear without an extra download.
const loaders = {
  AdminIndexPage: () => import("../features/admin/AdminIndexPage"),
  AdminInternshipFormPage: () => import("../features/admin/AdminInternshipFormPage"),
  AdminInternshipsPage: () => import("../features/admin/AdminInternshipsPage"),
  AdminOverviewPage: () => import("../features/admin/AdminOverviewPage"),
  AdminUsersPage: () => import("../features/admin/AdminUsersPage"),
  AdminAuditPage: () => import("../features/admin/AdminAuditPage"),
  CareerTracksPage: () => import("../features/careerTracks/CareerTracksPage"),
  ApplicationDetailPage: () => import("../features/applications/ApplicationDetailPage"),
  ApplicationsPage: () => import("../features/applications/ApplicationsPage"),
  AssistantPage: () => import("../features/assistant/AssistantPage"),
  DocumentDetailPage: () => import("../features/documents/DocumentDetailPage"),
  DocumentsPage: () => import("../features/documents/DocumentsPage"),
  InternshipDetailPage: () => import("../features/internships/InternshipDetailPage"),
  InternshipsPage: () => import("../features/internships/InternshipsPage"),
  InterviewPrepPage: () => import("../features/interviews/InterviewPrepPage"),
  InterviewSessionPage: () => import("../features/interviews/InterviewSessionPage"),
  MatchesPage: () => import("../features/matches/MatchesPage"),
  ProfilePage: () => import("../features/profile/ProfilePage"),
  InternshipGapPage: () => import("../features/skillGaps/InternshipGapPage"),
  SkillGapsPage: () => import("../features/skillGaps/SkillGapsPage"),
  ResumesPage: () => import("../features/resumes/ResumesPage"),
  ResumeComparePage: () => import("../features/resumes/ResumeComparePage"),
};

// A lazily loaded page. If its module is already loaded (by an earlier visit or by preload()) when the
// page mounts, it renders directly without suspending. The choice is fixed for the lifetime of the
// mounted page, so a re-render never swaps the component type (which would remount it and lose state).
export function lazyPage(load) {
  let Loaded = null;
  const remember = (module) => {
    Loaded = module.default;
    return module;
  };
  const Lazy = lazy(() => load().then(remember));
  function Page(props) {
    const [Component] = useState(() => Loaded || Lazy);
    return <Component {...props} />;
  }
  Page.preload = () => load().then(remember);
  return Page;
}

const pages = Object.fromEntries(Object.entries(loaders).map(([name, load]) => [name, lazyPage(load)]));

// Loads every page module. Used by the test setup, so tests render pages without waiting on a
// per-worker dynamic import (the lazy/Suspense path is covered by PageBoundary.test.jsx).
export const preloadAllPages = () => Promise.all(Object.values(pages).map((page) => page.preload()));

const {
  AdminAuditPage, AdminIndexPage, CareerTracksPage, AdminInternshipFormPage, AdminInternshipsPage, AdminOverviewPage, AdminUsersPage, ApplicationDetailPage,
  ApplicationsPage, AssistantPage, DocumentDetailPage, DocumentsPage, InternshipDetailPage, InternshipsPage, InterviewPrepPage,
  InterviewSessionPage, MatchesPage, ProfilePage, InternshipGapPage, SkillGapsPage, ResumesPage, ResumeComparePage,
} = pages;

export default function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/health" element={<HealthPage />} />
      <Route element={<AuthLayout />}>
        {/* Signed-in users are sent on to ?next= (validated) or the dashboard. */}
        <Route element={<GuestRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Route>
        {/* Opened from email links, so reachable whether or not someone is signed in.
            /auth/verify-email matches the link the backend puts in the verification email. */}
        <Route path="/auth/verify-email" element={<VerifyEmailPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/accept-invitation" element={<AcceptInvitationPage />} />
      </Route>

      {/* Signed-in users */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="/resumes" element={<ResumesPage />} />
          <Route path="/resumes/compare" element={<ResumeComparePage />} />
          <Route path="/resumes/:resumeId" element={<ResumesPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/internships" element={<InternshipsPage />} />
          <Route path="/internships/:internshipId" element={<InternshipDetailPage />} />
          <Route path="/matches" element={<MatchesPage />} />
          <Route path="/skill-gaps" element={<SkillGapsPage />} />
          <Route path="/career-tracks" element={<CareerTracksPage />} />
          <Route path="/career-tracks/:slug" element={<CareerTracksPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
          <Route path="/skill-gaps/internships/:internshipId" element={<InternshipGapPage />} />
          <Route path="/assistant/:conversationId?" element={<AssistantPage kind="application" />} />
          <Route path="/interview-assistant/:conversationId?" element={<AssistantPage kind="interview" />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
          <Route path="/interview-prep" element={<InterviewPrepPage />} />
          <Route path="/interview-prep/sessions/:sessionId" element={<InterviewSessionPage />} />
          {/* Earlier placeholder address. */}
          <Route path="/interviews" element={<Navigate to="/interview-prep" replace />} />
          {STUDENT_SECTIONS.filter((section) => !section.implemented).map((section) => (
            <Route key={section.path} path={section.path} element={<ComingSoonPage title={section.label} phase={section.phase} />} />
          ))}
          {/* Administrators only */}
          <Route element={<RoleRoute roles={["admin", "super_admin"]} />}>
            <Route path="/admin" element={<AdminOverviewPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/internships" element={<AdminInternshipsPage />} />
            <Route path="/admin/internships/new" element={<AdminInternshipFormPage />} />
            <Route path="/admin/internships/:internshipId/edit" element={<AdminInternshipFormPage />} />
            <Route path="/admin/index" element={<AdminIndexPage />} />
            <Route path="/admin/audit" element={<AdminAuditPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
