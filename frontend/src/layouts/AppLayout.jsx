import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import BrandMark from "../components/brand/BrandMark";
import Icon from "../components/ui/Icon";
import { APP_NAME, APP_TAGLINE } from "../config/brand";
import { useAuth } from "../context/AuthContext";
import { AvatarProvider } from "../context/AvatarContext";
import { ADMIN_SECTIONS, NAV_GROUPS, STUDENT_SECTIONS } from "../routes/navigation";
import PageBoundary from "../routes/PageBoundary";
import ProfileMenu from "./ProfileMenu";

// "/admin/users/3" -> "/admin/users", "/assistant/12" -> "/assistant"
export function sectionKey(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  return `/${parts[0] === "admin" ? parts.slice(0, 2).join("/") : parts[0] || ""}`;
}

const focusRing ="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-300";

function NavItem({ item, onNavigate }) {
  return (
    <NavLink
      to={item.path}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        `group relative flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors duration-150 ${focusRing} ${
          isActive
            ? "bg-white/[0.08] font-semibold text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
            : "text-slate-300 hover:bg-white/[0.05] hover:text-white"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {/* Active indicator bar (decorative; aria-current carries the meaning). */}
          <span
            aria-hidden="true"
            className={`absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-brand-400 to-violet-400 transition-opacity ${
              isActive ? "opacity-100" : "opacity-0"
            }`}
          />
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
              isActive ? "bg-brand-500/25 text-brand-200" : "text-slate-400 group-hover:text-slate-200"
            }`}
          >
            <Icon name={item.icon} className="h-[18px] w-[18px]" />
          </span>
          {item.label}
        </>
      )}
    </NavLink>
  );
}

function GroupLabel({ children }) {
  return <p className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">{children}</p>;
}

// Admin links are rendered only for administrators (the backend enforces the same rule).
function Navigation({ isAdmin, onNavigate }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV_GROUPS.map((group) => {
        const items = STUDENT_SECTIONS.filter((item) => item.group === group.id);
        if (!items.length) return null;
        return (
          <div key={group.id} className="flex flex-col gap-0.5">
            {group.id !== "overview" && <GroupLabel>{group.label}</GroupLabel>}
            {items.map((item) => (
              <NavItem key={item.path} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        );
      })}
      {isAdmin && (
        <div className="mt-3 flex flex-col gap-0.5 border-t border-white/10 pt-1">
          <GroupLabel>Admin</GroupLabel>
          {ADMIN_SECTIONS.map((item) => (
            <NavItem key={item.path} item={item} onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </nav>
  );
}

// Small tagline card at the foot of the sidebar.
function SidebarFooter() {
  return (
    <div className="mt-auto rounded-2xl border border-white/10 bg-gradient-to-br from-brand-500/20 to-violet-500/10 p-4">
      <p className="flex items-center gap-2 text-xs font-semibold text-brand-200">
        <Icon name="sparkles" className="h-4 w-4" />
        {APP_NAME}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-slate-300">{APP_TAGLINE}</p>
    </div>
  );
}

const sidebarSurface = "bg-navy-900 bg-[radial-gradient(120%_60%_at_0%_0%,rgba(99,91,219,0.22),transparent_60%)]";

// Off-canvas navigation for phones and tablets: a modal dialog that traps Tab, closes on Escape,
// on the backdrop and after navigating, and returns focus to the menu button.
function MobileDrawer({ isAdmin, onClose }) {
  const panel = useRef(null);

  useEffect(() => {
    const previous = document.activeElement;
    panel.current?.querySelector("a, button")?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "Tab") {
        const focusable = Array.from(panel.current?.querySelectorAll("a, button") || []);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      if (previous && typeof previous.focus === "function") previous.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <div className="absolute inset-0 bg-navy-950/60 backdrop-blur-sm motion-safe:animate-fade-in" aria-hidden="true" onClick={onClose} />
      <div
        ref={panel}
        id="mobile-navigation"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        className={`absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col gap-4 overflow-y-auto px-3 py-5 shadow-elevated motion-safe:animate-slide-in-left ${sidebarSurface}`}
      >
        <div className="flex items-center justify-between px-2">
          <BrandMark inverted />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className={`rounded-lg p-2 text-slate-300 hover:bg-white/10 hover:text-white ${focusRing}`}
          >
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>
        <Navigation isAdmin={isAdmin} onNavigate={onClose} />
      </div>
    </div>
  );
}

export default function AppLayout() {
  const { isAdmin } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // Close the drawer whenever the route changes (including browser back/forward).
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  return (
    <AvatarProvider>
    <div className="min-h-screen bg-slate-50">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-white px-4 py-2 text-sm font-medium text-brand-700 shadow focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to main content
      </a>

      <aside className={`fixed inset-y-0 left-0 hidden w-64 flex-col gap-4 overflow-y-auto px-3 py-5 lg:flex ${sidebarSurface}`}>
        <Link to="/" className={`rounded-lg px-2 ${focusRing}`}>
          <BrandMark inverted />
        </Link>
        <Navigation isAdmin={isAdmin} />
        <SidebarFooter />
      </aside>

      {drawerOpen && <MobileDrawer isAdmin={isAdmin} onClose={() => setDrawerOpen(false)} />}

      <div className="flex min-h-screen flex-col lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-slate-200/70 bg-white/80 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              aria-expanded={drawerOpen}
              aria-controls="mobile-navigation"
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 lg:hidden"
            >
              <Icon name="menu" className="h-5 w-5" />
            </button>
            <Link to="/" className="rounded-md lg:hidden" aria-label={`${APP_NAME} home`}>
              <BrandMark className="[&>span:last-child]:hidden sm:[&>span:last-child]:inline" />
            </Link>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {!location.pathname.startsWith("/assistant") && !location.pathname.startsWith("/interview-assistant") && (
              <Link
                to="/assistant"
                className="hidden items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-3.5 py-1.5 text-sm font-semibold text-brand-700 transition hover:border-brand-200 hover:bg-brand-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 sm:inline-flex"
              >
                <Icon name="sparkles" className="h-4 w-4" />
                Ask the assistant
              </Link>
            )}
            <ProfileMenu />
          </div>
        </header>
        <main id="main-content" tabIndex={-1} className="flex-1 px-4 py-6 focus:outline-none sm:px-6 lg:px-8 lg:py-8">
          <PageBoundary>
            {/* Re-keyed per top-level section so switching sections fades in (disabled for reduced motion).
                Not keyed by the full path: pages such as the assistant change their own URL and must keep state. */}
            <div key={sectionKey(location.pathname)} className="motion-safe:animate-fade-in-up">
              <Outlet />
            </div>
          </PageBoundary>
        </main>
      </div>
    </div>
    </AvatarProvider>
  );
}
