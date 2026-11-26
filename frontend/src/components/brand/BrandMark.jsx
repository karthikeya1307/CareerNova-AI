import { useId } from "react";
import { APP_NAME } from "../../config/brand";

// CareerNova AI logo: a four-point "nova" star in the AI indigo→violet gradient with a mint
// progress dot, on a navy tile (or a translucent tile on dark backgrounds).
export function BrandLogo({ className = "h-9 w-9", inverted = false }) {
  const gradientId = useId();
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#918AE8" />
          <stop offset="1" stopColor="#A78BFA" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" className={inverted ? "fill-white/10" : "fill-navy-900"} />
      <path d="M20 7.5 L22.6 16.4 L31.5 19 L22.6 21.6 L20 30.5 L17.4 21.6 L8.5 19 L17.4 16.4 Z" fill={`url(#${gradientId})`} />
      <circle cx="29.5" cy="10.5" r="2.6" className="fill-mint-200" />
    </svg>
  );
}

export default function BrandMark({ inverted = false, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <BrandLogo inverted={inverted} />
      <span className={`font-display text-lg font-bold tracking-tight ${inverted ? "text-white" : "text-slate-900"}`}>
        {APP_NAME}
      </span>
    </span>
  );
}
