import { NavLink, Outlet } from "react-router-dom";
import Button from "../components/ui/Button";
import { useAuth } from "../context/AuthContext";
import { ADMIN_SECTIONS, STUDENT_SECTIONS } from "../routes/navigation";

function NavItem({ item }) {
  return (
    <NavLink
      to={item.path}
      end={item.end}
      className={({ isActive }) =>
        `block rounded-md px-3 py-2 text-sm ${isActive ? "bg-brand-50 font-medium text-brand-700" : "text-slate-700 hover:bg-slate-100"}`
      }
    >
      {item.label}
    </NavLink>
  );
}

export default function AppLayout() {
  const { user, isAdmin, logout } = useAuth();
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white px-3 py-4 md:block">
        <p className="px-3 pb-4 text-lg font-semibold text-brand-700">AI Career Companion</p>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {STUDENT_SECTIONS.map((item) => (
            <NavItem key={item.path} item={item} />
          ))}
          {isAdmin && (
            <>
              <p className="mt-4 px-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Admin</p>
              {ADMIN_SECTIONS.map((item) => (
                <NavItem key={item.path} item={item} />
              ))}
            </>
          )}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <p className="text-sm text-slate-600 md:hidden">AI Career Companion</p>
          <div className="ml-auto flex items-center gap-3">
            {user && (
              <span className="text-sm text-slate-700">
                {user.first_name} {user.last_name}
              </span>
            )}
            <Button variant="secondary" onClick={logout}>
              Sign out
            </Button>
          </div>
        </header>
        <main className="flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
