// Small inline icon set (24x24 outline, currentColor). Decorative by default (aria-hidden).
const PATHS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0",
  document: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm7 0v5h5M9 13h6M9 17h6",
  briefcase: "M4 8h16v11H4zM9 8V5h6v3M4 13h16",
  target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H3",
  edit: "M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4",
  mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm6-3a6 6 0 0 1-12 0m6 6v3",
  clipboard: "M9 4h6v3H9zM7 5H5v16h14V5h-2M9 12l2 2 4-4",
  chat: "M4 5h16v11H9l-5 4z",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0m2-9a3 3 0 1 0 0-6m1 15a5 5 0 0 0-3-4.6",
  database: "M12 8c4.4 0 8-1.3 8-3s-3.6-3-8-3-8 1.3-8 3 3.6 3 8 3Zm-8-3v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5m-16 7c0 1.7 3.6 3 8 3s8-1.3 8-3",
  building: "M5 21V4h10v17M15 9h4v12M8 8h4M8 12h4M8 16h4M3 21h18",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "M6 6l12 12M18 6 6 18",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11",
  upload: "M12 16V4m-5 5 5-5 5 5M4 20h16",
  arrowRight: "M5 12h14m-6-6 6 6-6 6",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  check: "M5 12.5 9.5 17 19 7.5",
  alert: "M12 8v5m0 3.5v.5M10.3 4.3 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z",
  sparkles: "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
  calendar: "M4 6h16v15H4zM4 10h16M8 3v4m8-4v4",
  chevronDown: "M6 9l6 6 6-6",
};

export default function Icon({ name, className = "h-5 w-5", title }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : "true"}
      role={title ? "img" : undefined}
      focusable="false"
    >
      {title && <title>{title}</title>}
      <path d={PATHS[name] || ""} />
    </svg>
  );
}
