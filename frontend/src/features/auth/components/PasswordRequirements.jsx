import { PASSWORD_RULES } from "../validation";

// Live checklist under new-password fields. `id` lets the password input reference it.
export default function PasswordRequirements({ id, password }) {
  const value = password || "";
  return (
    <ul id={id} className="mt-1 grid gap-1 text-xs sm:grid-cols-3" aria-label="Password requirements">
      {PASSWORD_RULES.map((rule) => {
        const met = rule.test(value);
        return (
          <li key={rule.id} className={`flex items-center gap-1.5 ${met ? "text-mint-700" : "text-slate-500"}`}>
            <span aria-hidden="true" className={`inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${met ? "bg-mint-100" : "bg-slate-100"}`}>
              {met ? "✓" : "•"}
            </span>
            <span>
              {rule.label}
              <span className="sr-only">{met ? " (met)" : " (not met yet)"}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
