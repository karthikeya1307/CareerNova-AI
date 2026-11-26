import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

// Reads a one-time `?token=` from the URL, keeps it in memory and removes it from the address bar
// (and browser history) straight away, so it is not left in history, bookmarks or Referer headers.
export default function useTokenFromUrl() {
  const location = useLocation();
  const navigate = useNavigate();
  const [token] = useState(() => new URLSearchParams(location.search).get("token") || "");

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (!params.has("token")) return;
    params.delete("token");
    const search = params.toString();
    navigate({ pathname: location.pathname, search: search ? `?${search}` : "" }, { replace: true });
  }, [location.pathname, location.search, navigate]);

  return token.trim();
}
