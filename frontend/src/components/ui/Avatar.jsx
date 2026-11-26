import { useAvatar } from "../../context/AvatarContext";

const SIZES = { sm: "h-8 w-8 text-xs", md: "h-10 w-10 text-sm", lg: "h-14 w-14 text-base", xl: "h-24 w-24 text-2xl" };

export function initialsOf(user) {
  const text = `${user?.first_name?.[0] || ""}${user?.last_name?.[0] || ""}`.toUpperCase();
  return text || "?";
}

// The student's profile picture, or their initials when none is uploaded (or it could not be loaded).
export default function Avatar({ user, size = "sm", className = "", src }) {
  const { url } = useAvatar();
  const picture = src !== undefined ? src : url;
  const base = `inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full ${SIZES[size] || SIZES.sm} ${className}`;
  if (picture) {
    return <img src={picture} alt="" aria-hidden="true" className={`${base} object-cover`} />;
  }
  return (
    <span aria-hidden="true" className={`${base} bg-gradient-to-br from-brand-500 to-violet-500 font-semibold text-white`}>
      {initialsOf(user)}
    </span>
  );
}
