import { normalizeError } from "../../api/errors";
import Icon from "./Icon";

// Shows an ApiError (or any error/string) without exposing technical details.
export default function ErrorAlert({ error, title = "Something went wrong" }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : normalizeError(error).message;
  return (
    <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p className="font-semibold">{title}</p>
        <p className="mt-0.5">{message}</p>
      </div>
    </div>
  );
}
