// One place for the app's sections: used by the sidebar and the placeholder routes.
// `implemented: true` sections have real pages; the rest render the ComingSoon placeholder.
// `icon` names come from components/ui/Icon.jsx. `group` organises the sidebar (NAV_GROUPS order).

export const NAV_GROUPS = [
  { id: "overview", label: "Overview" },
  { id: "profile", label: "Your profile" },
  { id: "opportunities", label: "Opportunities" },
  { id: "growth", label: "Grow your skills" },
  { id: "ai", label: "AI assistants" },
];

export const STUDENT_SECTIONS = [
  { path: "/", label: "Dashboard", icon: "home", end: true, implemented: true, group: "overview" },
  { path: "/profile", label: "Profile", icon: "user", implemented: true, group: "profile" },
  { path: "/resumes", label: "Resumes", icon: "document", implemented: true, group: "profile" },
  { path: "/documents", label: "Documents", icon: "edit", implemented: true, group: "profile" },
  { path: "/internships", label: "Internships", icon: "briefcase", implemented: true, group: "opportunities" },
  { path: "/matches", label: "Matches", icon: "target", implemented: true, group: "opportunities" },
  { path: "/applications", label: "Applications", icon: "clipboard", implemented: true, group: "opportunities" },
  { path: "/skill-gaps", label: "Skill gaps", icon: "chart", implemented: true, group: "growth" },
  { path: "/career-tracks", label: "Career tracks", icon: "sparkles", implemented: true, group: "growth" },
  { path: "/interview-prep", label: "Interview practice", icon: "mic", implemented: true, group: "growth" },
  { path: "/assistant", label: "Application Assistant", icon: "chat", implemented: true, group: "ai" },
  { path: "/interview-assistant", label: "Interview Prep Assistant", icon: "sparkles", implemented: true, group: "ai" },
];

export const ADMIN_SECTIONS = [
  { path: "/admin", label: "Admin overview", icon: "chart", end: true, implemented: true },
  { path: "/admin/users", label: "Users", icon: "users", implemented: true },
  { path: "/admin/internships", label: "Manage internships", icon: "building", implemented: true },
  { path: "/admin/index", label: "Search index", icon: "database", implemented: true },
  { path: "/admin/audit", label: "Audit log", icon: "clipboard", implemented: true },
];
