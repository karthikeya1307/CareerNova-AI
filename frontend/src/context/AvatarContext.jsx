import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { fetchAvatarBlob } from "../api/profile";

// The signed-in student's profile picture as an object URL (the picture itself is private: it is fetched
// with the student's own token and never exposed by a public URL). null = no picture -> show initials.
const AvatarContext = createContext({ url: null, refresh: () => {} });

export function AvatarProvider({ children }) {
  const [url, setUrl] = useState(null);
  const current = useRef(null);

  const replace = useCallback((next) => {
    if (current.current) URL.revokeObjectURL(current.current);
    current.current = next;
    setUrl(next);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const blob = await fetchAvatarBlob();
      replace(blob && typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob) : null);
    } catch {
      replace(null); // a failed picture load never blocks the page; initials are shown
    }
  }, [replace]);

  useEffect(() => {
    refresh();
    return () => {
      if (current.current) URL.revokeObjectURL(current.current);
    };
  }, [refresh]);

  return <AvatarContext.Provider value={{ url, refresh }}>{children}</AvatarContext.Provider>;
}

export function useAvatar() {
  return useContext(AvatarContext);
}
