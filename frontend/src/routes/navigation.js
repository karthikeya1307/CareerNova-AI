// One place for the app's sections: used by the sidebar and the placeholder routes.
// `phase` says which frontend step implements the page (they are placeholders in F0).

export const STUDENT_SECTIONS = [
  { path: "/", label: "Dashboard", phase: "F12", end: true },
  { path: "/profile", label: "Profile", phase: "F2" },
  { path: "/resumes", label: "Resumes", phase: "F3" },
  { path: "/internships", label: "Internships", phase: "F4" },
  { path: "/matches", label: "Matches", phase: "F5" },
  { path: "/skill-gaps", label: "Skill gaps", phase: "F6" },
  { path: "/documents", label: "Documents", phase: "F7" },
  { path: "/interviews", label: "Interview practice", phase: "F8" },
  { path: "/applications", label: "Applications", phase: "F9" },
  { path: "/assistant", label: "Career assistant", phase: "F10" },
];

export const ADMIN_SECTIONS = [
  { path: "/admin/users", label: "Users", phase: "F11" },
  { path: "/admin/internships", label: "Manage internships", phase: "F11" },
  { path: "/admin/index", label: "Search index", phase: "F11" },
];
