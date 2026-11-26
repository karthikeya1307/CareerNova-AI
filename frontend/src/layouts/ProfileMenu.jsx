import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Avatar from "../components/ui/Avatar";
import Icon from "../components/ui/Icon";
import { useAuth } from "../context/AuthContext";

export function initials(user) {
  const text = `${user?.first_name?.[0] || ""}${user?.last_name?.[0] || ""}`.toUpperCase();
  return text || "?";
}

// Account menu (menu-button pattern): Enter/Space/ArrowDown opens it and focuses the first item,
// Arrow keys move, Home/End jump, Escape or Tab closes it and returns focus to the button.
export default function ProfileMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const menuId = useId();
  const button = useRef(null);
  const menu = useRef(null);

  const items = () => Array.from(menu.current?.querySelectorAll('[role="menuitem"]') || []);
  const focusItem = (index) => {
    const list = items();
    if (list.length) list[(index + list.length) % list.length].focus();
  };

  useEffect(() => {
    if (!open) return undefined;
    focusItem(0);
    const onPointer = (event) => {
      if (!menu.current?.contains(event.target) && !button.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [open]);

  const close = (refocus = true) => {
    setOpen(false);
    if (refocus) button.current?.focus();
  };

  const onMenuKey = (event) => {
    const list = items();
    const index = list.indexOf(document.activeElement);
    if (event.key === "ArrowDown") { event.preventDefault(); focusItem(index + 1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); focusItem(index - 1); }
    else if (event.key === "Home") { event.preventDefault(); focusItem(0); }
    else if (event.key === "End") { event.preventDefault(); focusItem(list.length - 1); }
    else if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (event.key === "Tab") close(false);
  };

  const onButtonKey = (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
    }
  };

  // F0 behaviour: logout revokes the session and clears it; the protected route then sends the
  // user to /login (with ?next= back to this page).
  const signOut = async () => {
    setSigningOut(true);
    await logout();
  };

  return (
    <div className="relative">
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onButtonKey}
        className="flex items-center gap-2 rounded-full border border-transparent py-1 pl-1 pr-2 text-sm text-slate-700 transition hover:border-slate-200 hover:bg-white hover:shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
      >
        <Avatar user={user} size="sm" className="ring-2 ring-white" />
        {/* One copy of the name: visually hidden on phones, shown from the sm breakpoint. */}
        <span className="sr-only sm:not-sr-only sm:max-w-[10rem] sm:truncate sm:font-medium">
          {user?.first_name} {user?.last_name}
        </span>
        <span className="sr-only">, account menu</span>
        <Icon name="chevronDown" className="h-4 w-4 text-slate-400" />
      </button>

      {open && (
        <div
          ref={menu}
          id={menuId}
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKey}
          className="absolute right-0 z-30 mt-2 w-64 origin-top-right overflow-hidden rounded-2xl border border-slate-200/80 bg-white py-1 shadow-elevated motion-safe:animate-scale-in"
        >
          <div className="border-b border-slate-100 px-4 py-3" role="presentation">
            <p className="truncate text-sm font-medium text-slate-900">
              {user?.first_name} {user?.last_name}
            </p>
            <p className="truncate text-xs text-slate-500">{user?.email}</p>
            {user?.role && user.role !== "student" && (
              <p className="mt-2 inline-flex rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-brand-700">
                {user.role === "super_admin" ? "Super admin" : "Admin"}
              </p>
            )}
          </div>
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            onClick={() => {
              close(false);
              navigate("/profile");
            }}
            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 focus:bg-slate-100 focus:outline-none"
          >
            <Icon name="user" className="h-4 w-4 text-slate-500" />
            Profile
          </button>
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            onClick={signOut}
            disabled={signingOut}
            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-700 hover:bg-red-50 focus:bg-red-50 focus:outline-none disabled:opacity-60"
          >
            <Icon name="logout" className="h-4 w-4" />
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      )}
    </div>
  );
}
